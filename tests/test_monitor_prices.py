"""Tests for ``monitor_position`` USD price resolution.

Feeds are keyed by token address, so either token may be the priced one and
the lookup does not depend on token order inside the pool. A token is priced
at $1 only when it is explicitly listed as a stablecoin; the pool spot price is
never used instead of a missing feed.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

import monitor_position
from config import OracleFeed, load_config
from monitor_position import (
    STABLECOIN_PRICE_USD,
    price_for_token,
    resolve_native_price_usd,
    resolve_token_prices,
)

TOKEN0 = "0x00000000000000000000000000000000000000A0"
TOKEN1 = "0x00000000000000000000000000000000000000B1"
STABLE = "0x0000000000000000000000000000000000000055"
TOKEN0_FEED = "0x00000000000000000000000000000000000000AA"
TOKEN1_FEED = "0x00000000000000000000000000000000000000BB"
WETH = "0x4200000000000000000000000000000000000006"
WETH_FEED = "0x00000000000000000000000000000000000000CC"

FEED_MAX_AGE = 3600


def oracle_feed(token: str, feed: str, max_age: int = FEED_MAX_AGE) -> OracleFeed:
    return OracleFeed(
        token_address=token,
        feed_address=feed,
        max_age_seconds=max_age,
    )


def base_config():
    return replace(
        load_config(),
        oracle_feeds={
            TOKEN0.lower(): oracle_feed(TOKEN0, TOKEN0_FEED),
            TOKEN1.lower(): oracle_feed(TOKEN1, TOKEN1_FEED),
        },
        oracle_stablecoins=frozenset(),
    )


def test_prices_are_resolved_per_token_address(monkeypatch):
    config = base_config()
    prices = {TOKEN0_FEED: Decimal("1.0001"), TOKEN1_FEED: Decimal("2000")}
    calls = []

    def fake_price(w3, feed_address, max_age_seconds):
        calls.append((feed_address, max_age_seconds))
        return prices[feed_address]

    monkeypatch.setattr(monitor_position, "get_token_price_usd", fake_price)

    assert resolve_token_prices(object(), config, TOKEN0, TOKEN1) == (
        Decimal("1.0001"),
        Decimal("2000"),
    )
    assert calls == [(TOKEN0_FEED, FEED_MAX_AGE), (TOKEN1_FEED, FEED_MAX_AGE)]


def test_reversed_token_order_uses_the_same_feeds(monkeypatch):
    """A pool switch that reorders tokens (USDC/cbBTC) needs no oracle edits."""
    config = base_config()
    prices = {TOKEN0_FEED: Decimal("1.0001"), TOKEN1_FEED: Decimal("2000")}

    monkeypatch.setattr(
        monitor_position,
        "get_token_price_usd",
        lambda w3, feed_address, max_age_seconds: prices[feed_address],
    )

    assert resolve_token_prices(object(), config, TOKEN1, TOKEN0) == (
        Decimal("2000"),
        Decimal("1.0001"),
    )


def test_token_addresses_are_matched_case_insensitively(monkeypatch):
    config = base_config()

    monkeypatch.setattr(
        monitor_position,
        "get_token_price_usd",
        lambda w3, feed_address, max_age_seconds: Decimal("7"),
    )

    mixed_case = "0x" + TOKEN0[2:].upper()

    assert resolve_token_prices(
        object(),
        config,
        mixed_case,
        TOKEN1.lower(),
    ) == (Decimal("7"), Decimal("7"))


def test_each_feed_uses_its_own_staleness_window(monkeypatch):
    config = replace(
        base_config(),
        oracle_feeds={
            TOKEN0.lower(): oracle_feed(TOKEN0, TOKEN0_FEED, 172800),
            TOKEN1.lower(): oracle_feed(TOKEN1, TOKEN1_FEED),
        },
    )
    calls = []

    def fake_price(w3, feed_address, max_age_seconds):
        calls.append((feed_address, max_age_seconds))
        return Decimal("1")

    monkeypatch.setattr(monitor_position, "get_token_price_usd", fake_price)

    resolve_token_prices(object(), config, TOKEN0, TOKEN1)

    assert calls == [(TOKEN0_FEED, 172800), (TOKEN1_FEED, FEED_MAX_AGE)]


def test_stablecoin_without_a_feed_is_valued_at_one_dollar(monkeypatch):
    config = replace(
        base_config(),
        oracle_feeds={TOKEN0.lower(): oracle_feed(TOKEN0, TOKEN0_FEED)},
        oracle_stablecoins=frozenset({STABLE.lower()}),
    )
    calls = []

    def fake_price(w3, feed_address, max_age_seconds):
        calls.append(feed_address)
        return Decimal("2500")

    monkeypatch.setattr(monitor_position, "get_token_price_usd", fake_price)

    token0_price, stable_price = resolve_token_prices(
        object(),
        config,
        TOKEN0,
        STABLE,
    )

    assert token0_price == Decimal("2500")
    assert stable_price == STABLECOIN_PRICE_USD == Decimal("1")
    assert calls == [TOKEN0_FEED]


def test_missing_feed_is_an_error_that_names_the_token():
    config = replace(base_config(), oracle_stablecoins=frozenset())

    with pytest.raises(RuntimeError, match=STABLE):
        price_for_token(object(), config, STABLE)


def test_oracle_failure_names_the_failing_feed(monkeypatch):
    config = base_config()

    def boom(w3, feed_address, max_age_seconds):
        if feed_address == TOKEN1_FEED:
            raise ValueError("Chainlink price is stale")

        return Decimal("1")

    monkeypatch.setattr(monitor_position, "get_token_price_usd", boom)

    with pytest.raises(RuntimeError, match=TOKEN1_FEED):
        resolve_token_prices(object(), config, TOKEN0, TOKEN1)


def test_native_price_comes_from_the_weth_feed(monkeypatch):
    config = replace(
        load_config(),
        weth_address=WETH,
        oracle_feeds={WETH.lower(): oracle_feed(WETH, WETH_FEED, 1200)},
    )
    calls = []

    def fake_price(w3, feed_address, max_age_seconds):
        calls.append((feed_address, max_age_seconds))
        return Decimal("2400")

    monkeypatch.setattr(monitor_position, "get_token_price_usd", fake_price)

    assert resolve_native_price_usd(object(), config) == Decimal("2400")
    assert calls == [(WETH_FEED, 1200)]


def test_native_price_is_unknown_without_a_weth_feed():
    config = replace(
        load_config(),
        oracle_feeds={},
        oracle_stablecoins=frozenset(),
    )

    assert resolve_native_price_usd(object(), config) is None


def test_native_price_does_not_depend_on_the_pool_tokens(monkeypatch):
    """A BTC/USDC pool holds no WETH, yet gas is still priced in USD."""
    config = replace(
        load_config(),
        weth_address=WETH,
        oracle_feeds={
            WETH.lower(): oracle_feed(WETH, WETH_FEED),
            TOKEN0.lower(): oracle_feed(TOKEN0, TOKEN0_FEED),
            TOKEN1.lower(): oracle_feed(TOKEN1, TOKEN1_FEED),
        },
        oracle_stablecoins=frozenset(),
    )
    prices = {
        WETH_FEED: Decimal("2400"),
        TOKEN0_FEED: Decimal("1"),
        TOKEN1_FEED: Decimal("80000"),
    }

    monkeypatch.setattr(
        monitor_position,
        "get_token_price_usd",
        lambda w3, feed_address, max_age_seconds: prices[feed_address],
    )

    assert resolve_native_price_usd(object(), config) == Decimal("2400")
    assert resolve_token_prices(object(), config, TOKEN0, TOKEN1) == (
        Decimal("1"),
        Decimal("80000"),
    )

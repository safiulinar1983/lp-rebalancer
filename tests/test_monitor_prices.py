"""Tests for ``monitor_position.resolve_token_prices``.

An empty oracle feed is an explicit stablecoin assumption, not a fallback to
the pool spot price. Either token may be the stablecoin, but both feeds being
empty has to fail loudly.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

import monitor_position
from config import load_config
from monitor_position import STABLECOIN_PRICE_USD, resolve_token_prices

TOKEN0_FEED = "0x00000000000000000000000000000000000000AA"
TOKEN1_FEED = "0x00000000000000000000000000000000000000BB"


def base_config():
    return replace(load_config(), token1_usd_feed=TOKEN1_FEED)


def test_stablecoin_token0_is_valued_at_one_dollar(monkeypatch):
    config = replace(base_config(), token0_usd_feed="")
    calls = []

    def fake_price(w3, feed_address, max_age_seconds):
        calls.append((feed_address, max_age_seconds))
        return Decimal("2500")

    monkeypatch.setattr(monitor_position, "get_token_price_usd", fake_price)

    token0_price, token1_price = resolve_token_prices(object(), config)

    assert token0_price == STABLECOIN_PRICE_USD == Decimal("1")
    assert token1_price == Decimal("2500")
    assert calls == [(TOKEN1_FEED, config.oracle_max_age_seconds)]


def test_configured_token0_feed_is_used(monkeypatch):
    config = replace(base_config(), token0_usd_feed=TOKEN0_FEED)
    prices = {
        TOKEN0_FEED: Decimal("1.0001"),
        TOKEN1_FEED: Decimal("2000"),
    }

    monkeypatch.setattr(
        monitor_position,
        "get_token_price_usd",
        lambda w3, feed_address, max_age_seconds: prices[feed_address],
    )

    assert resolve_token_prices(object(), config) == (
        Decimal("1.0001"),
        Decimal("2000"),
    )


def test_stablecoin_token1_is_valued_at_one_dollar(monkeypatch):
    config = replace(
        base_config(),
        token0_usd_feed=TOKEN0_FEED,
        token1_usd_feed="",
    )
    calls = []

    def fake_price(w3, feed_address, max_age_seconds):
        calls.append((feed_address, max_age_seconds))
        return Decimal("2500")

    monkeypatch.setattr(monitor_position, "get_token_price_usd", fake_price)

    token0_price, token1_price = resolve_token_prices(object(), config)

    assert token0_price == Decimal("2500")
    assert token1_price == STABLECOIN_PRICE_USD == Decimal("1")
    assert calls == [(TOKEN0_FEED, config.oracle_max_age_seconds)]


def test_both_feeds_missing_is_an_error():
    config = replace(
        base_config(),
        token0_usd_feed="",
        token1_usd_feed="",
    )

    with pytest.raises(RuntimeError, match="At least one oracle feed"):
        resolve_token_prices(object(), config)


def test_oracle_failure_names_the_failing_feed(monkeypatch):
    config = base_config()

    def boom(w3, feed_address, max_age_seconds):
        raise ValueError("Chainlink price is stale")

    monkeypatch.setattr(monitor_position, "get_token_price_usd", boom)

    with pytest.raises(RuntimeError, match=TOKEN1_FEED):
        resolve_token_prices(object(), config)

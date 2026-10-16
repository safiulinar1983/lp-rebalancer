"""Tests for ``monitor_position.resolve_token_prices``.

The monitor must never fall back to the pool spot price as if it were a USD
price: a missing token1 feed has to fail loudly.
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


def test_missing_token1_feed_is_an_error(monkeypatch):
    config = replace(base_config(), token1_usd_feed="")

    with pytest.raises(RuntimeError, match="token1_usd_feed"):
        resolve_token_prices(object(), config)


def test_oracle_failure_names_the_failing_feed(monkeypatch):
    config = base_config()

    def boom(w3, feed_address, max_age_seconds):
        raise ValueError("Chainlink price is stale")

    monkeypatch.setattr(monitor_position, "get_token_price_usd", boom)

    with pytest.raises(RuntimeError, match=TOKEN1_FEED):
        resolve_token_prices(object(), config)

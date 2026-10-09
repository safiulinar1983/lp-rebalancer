from decimal import Decimal

import pytest
import blockchain.oracle as oracle


class FakeCall:
    def __init__(self, value):
        self.value = value

    def call(self):
        return self.value


class FakeFunctions:
    def __init__(self, answer=230_000_000_000, updated_at=9999):
        self.answer = answer
        self.updated_at = updated_at

    def decimals(self):
        return FakeCall(8)

    def latestRoundData(self):
        return FakeCall((1, self.answer, 1, self.updated_at, 1))


class FakeWeb3:
    def __init__(self, answer=230_000_000_000, updated_at=9999):
        functions = FakeFunctions(answer, updated_at)

        class Feed:
            pass

        feed = Feed()
        feed.functions = functions

        class Eth:
            def contract(self, **kwargs):
                return feed

        self.eth = Eth()


@pytest.fixture
def valid_address(monkeypatch):
    monkeypatch.setattr(oracle.Web3, "is_address", lambda _: True)
    monkeypatch.setattr(oracle.Web3, "to_checksum_address", lambda x: x)
    monkeypatch.setattr(oracle.time, "time", lambda: 10000)


def test_get_token_price_usd(valid_address):
    price = oracle.get_token_price_usd(FakeWeb3(), "0x1234")
    assert price == Decimal("2300")


def test_reject_invalid_feed_address():
    with pytest.raises(ValueError, match="Invalid Chainlink feed"):
        oracle.get_token_price_usd(FakeWeb3(), "invalid")


def test_reject_nonpositive_max_age():
    with pytest.raises(ValueError, match="max_age_seconds"):
        oracle.get_token_price_usd(FakeWeb3(), "invalid", 0)


def test_reject_nonpositive_price(valid_address):
    with pytest.raises(ValueError, match="invalid price"):
        oracle.get_token_price_usd(
            FakeWeb3(answer=0), "0x1234"
        )


def test_reject_stale_price(valid_address):
    with pytest.raises(ValueError, match="stale"):
        oracle.get_token_price_usd(
            FakeWeb3(updated_at=1), "0x1234"
        )


def test_reject_future_timestamp(valid_address):
    with pytest.raises(ValueError, match="invalid timestamp"):
        oracle.get_token_price_usd(
            FakeWeb3(updated_at=10001), "0x1234"
        )

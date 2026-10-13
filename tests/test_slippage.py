import pytest

from blockchain.slippage import minimum_amount_out


@pytest.mark.parametrize(
    ("quote", "slippage_bps", "expected"),
    [
        (1_000_000, 0, 1_000_000),
        (1_000_000, 50, 995_000),
        (1_000_000, 100, 990_000),
        (1_000_000, 500, 950_000),
        (999, 100, 989),
    ],
)
def test_minimum_output(quote, slippage_bps, expected):
    assert minimum_amount_out(quote, slippage_bps) == expected


@pytest.mark.parametrize("quote", [0, -1, True, 1.5, "1000"])
def test_rejects_invalid_quote(quote):
    with pytest.raises(ValueError, match="Quoted output"):
        minimum_amount_out(quote, 50)


@pytest.mark.parametrize(
    "slippage",
    [-1, 10_000, 10_001, True, 1.5, "50"],
)
def test_rejects_invalid_slippage(slippage):
    with pytest.raises(ValueError, match="slippage_bps"):
        minimum_amount_out(1_000_000, slippage)


def test_rejects_settings_that_round_minimum_output_to_zero():
    with pytest.raises(ValueError, match="zero minimum output"):
        minimum_amount_out(1, 9_999)

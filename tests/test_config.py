"""Tests for ``config.load_config``.

The configuration layer must hand ``Decimal`` values to the strategy and must
resolve ``config.yaml`` next to the module, not relative to the working
directory.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from config import DEFAULT_WETH_ADDRESS, load_config

BASE_CONFIG = """
network: base_sepolia

networks:
  base_sepolia:
    chain_id: 84532
    rpc_url: https://sepolia.base.org

dex: pancakeswap_v3

pool:
  address: "0x94bfc0574FF48E92cE43d495376C477B1d0EEeC0"

strategy:
  range_half_width: 0.01
  check_interval: 5
  fee_threshold_usd: 0.10

position_manager:
  address: "0x27F971cb582BF9E50F397e4d29a5C7A34f11faA2"
  token_id: 82740

wallet:
  address: "0x87e58e8B5983FC4fF8199d3E16264ad39182a96e"

oracle:
  token0_usd_feed: ""
  token1_usd_feed: "0x4aDC67696bA383F43DD60A9e78F2C97Fbbfc7cb1"
  max_age_seconds: 3600
"""


def write_config(tmp_path: Path, content: str = BASE_CONFIG) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def replaced_config(tmp_path: Path, old: str, new: str) -> Path:
    return write_config(tmp_path, BASE_CONFIG.replace(old, new))


def test_default_config_is_found_from_any_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.network == "base_sepolia"
    assert config.expected_chain_id == 84532


def test_strategy_numbers_are_decimals(tmp_path):
    config = load_config(write_config(tmp_path))

    assert config.range_half_width == Decimal("0.01")
    assert isinstance(config.range_half_width, Decimal)
    assert config.fee_threshold_usd == Decimal("0.10")
    assert isinstance(config.fee_threshold_usd, Decimal)
    assert config.check_interval == 5


def test_decimal_conversion_avoids_float_artifacts(tmp_path):
    path = replaced_config(tmp_path, "range_half_width: 0.01", "range_half_width: 0.07")

    assert load_config(path).range_half_width == Decimal("0.07")


def test_weth_defaults_to_the_base_predeploy_address(tmp_path):
    config = load_config(write_config(tmp_path))

    assert config.weth_address == DEFAULT_WETH_ADDRESS


def test_weth_can_be_overridden(tmp_path):
    path = write_config(
        tmp_path,
        BASE_CONFIG
        + """
weth:
  address: "0x0000000000000000000000000000000000000001"
""",
    )

    assert load_config(path).weth_address == (
        "0x0000000000000000000000000000000000000001"
    )


def test_empty_weth_address_is_rejected(tmp_path):
    path = write_config(tmp_path, BASE_CONFIG + '\nweth:\n  address: ""\n')

    with pytest.raises(ValueError, match="weth.address"):
        load_config(path)


def test_position_token_id_may_be_omitted(tmp_path):
    path = replaced_config(tmp_path, "  token_id: 82740\n", "")

    assert load_config(path).position_token_id is None


def test_boolean_token_id_is_rejected(tmp_path):
    path = replaced_config(tmp_path, "token_id: 82740", "token_id: true")

    with pytest.raises(ValueError, match="position_manager.token_id"):
        load_config(path)


def test_non_numeric_range_half_width_is_rejected(tmp_path):
    path = replaced_config(
        tmp_path,
        "range_half_width: 0.01",
        'range_half_width: "abc"',
    )

    with pytest.raises(ValueError, match="strategy.range_half_width"):
        load_config(path)


def test_zero_range_half_width_is_rejected(tmp_path):
    path = replaced_config(tmp_path, "range_half_width: 0.01", "range_half_width: 0")

    with pytest.raises(ValueError, match="must be positive"):
        load_config(path)


def test_negative_fee_threshold_is_rejected(tmp_path):
    path = replaced_config(
        tmp_path,
        "fee_threshold_usd: 0.10",
        "fee_threshold_usd: -1",
    )

    with pytest.raises(ValueError, match="must be non-negative"):
        load_config(path)


def test_fractional_check_interval_is_rejected(tmp_path):
    path = replaced_config(tmp_path, "check_interval: 5", "check_interval: 5.5")

    with pytest.raises(ValueError, match="strategy.check_interval"):
        load_config(path)


def test_unknown_network_is_rejected(tmp_path):
    path = replaced_config(tmp_path, "network: base_sepolia", "network: base_mainnet")

    with pytest.raises(ValueError, match="Unknown network"):
        load_config(path)

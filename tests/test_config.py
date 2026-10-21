"""Tests for ``config.load_config``.

The configuration layer must hand ``Decimal`` values to the strategy and must
resolve ``config.yaml`` next to the module, not relative to the working
directory.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from config import DEFAULT_WETH_ADDRESS, load_config

PANCAKE_POOL = "0xf9c882e4EBd0886BcC87A30CE47222157Be12832"
PANCAKE_POSITION_MANAGER = "0x46A15B0b27311cedF172AB29E4f4766fbE7F4364"
PANCAKE_ROUTER = "0x1b81D678ffb9C0263b24A97847620C99d213eB14"
PANCAKE_QUOTER = "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997"

UNISWAP_POOL = "0x94bfc0574FF48E92cE43d495376C477B1d0EEeC0"
UNISWAP_POSITION_MANAGER = "0x27F971cb582BF9E50F397e4d29a5C7A34f11faA2"
UNISWAP_ROUTER = "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4"
UNISWAP_QUOTER = "0xC5290058841028F1614F3A6F0F5816cAd0df5E27"

BASE_CONFIG = f"""
network: 84532

networks:
  84532:
    name: base_sepolia
    rpc_url: "${{BASE_RPC_URL:-https://sepolia.base.org}}"

    weth:
      address: "0x4200000000000000000000000000000000000006"

    oracle:
      token0_usd_feed: ""
      token1_usd_feed: "0x4aDC67696bA383F43DD60A9e78F2C97Fbbfc7cb1"
      max_age_seconds: 3600

    dexes:
      pancakeswap_v3:
        pool:
          address: "{PANCAKE_POOL}"
        position_manager:
          address: "{PANCAKE_POSITION_MANAGER}"
          token_id: 42
        swap_router:
          address: "{PANCAKE_ROUTER}"
        quoter:
          address: "{PANCAKE_QUOTER}"

      uniswap_v3:
        pool:
          address: "{UNISWAP_POOL}"
        position_manager:
          address: "{UNISWAP_POSITION_MANAGER}"
          token_id: 82740
        swap_router:
          address: "{UNISWAP_ROUTER}"
        quoter:
          address: "{UNISWAP_QUOTER}"

dex: pancakeswap_v3

strategy:
  range_half_width: 0.01
  check_interval: 5
  fee_threshold_usd: 0.10

wallet:
  address: "0x87e58e8B5983FC4fF8199d3E16264ad39182a96e"
"""


def write_config(tmp_path: Path, content: str = BASE_CONFIG) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def replaced_config(
    tmp_path: Path,
    old: str,
    new: str,
    *more: tuple[str, str],
) -> Path:
    content = BASE_CONFIG.replace(old, new)

    for extra_old, extra_new in more:
        content = content.replace(extra_old, extra_new)

    return write_config(tmp_path, content)


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
    path = replaced_config(
        tmp_path,
        "range_half_width: 0.01",
        "range_half_width: 0.07",
    )

    assert load_config(path).range_half_width == Decimal("0.07")


def test_weth_defaults_to_the_base_predeploy_address(tmp_path):
    config = load_config(write_config(tmp_path))

    assert config.weth_address == DEFAULT_WETH_ADDRESS


def test_weth_can_be_overridden(tmp_path):
    path = replaced_config(
        tmp_path,
        'address: "0x4200000000000000000000000000000000000006"',
        'address: "0x0000000000000000000000000000000000000001"',
    )

    assert load_config(path).weth_address == (
        "0x0000000000000000000000000000000000000001"
    )


def test_empty_weth_address_is_rejected(tmp_path):
    path = replaced_config(
        tmp_path,
        'address: "0x4200000000000000000000000000000000000006"',
        'address: ""',
    )

    with pytest.raises(ValueError, match="weth.address"):
        load_config(path)


def test_position_token_id_may_be_omitted(tmp_path):
    path = replaced_config(tmp_path, "          token_id: 42\n", "")

    assert load_config(path).position_token_id is None


def test_boolean_token_id_is_rejected(tmp_path):
    path = replaced_config(tmp_path, "token_id: 42", "token_id: true")

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
    path = replaced_config(
        tmp_path,
        "range_half_width: 0.01",
        "range_half_width: 0",
    )

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
    path = replaced_config(
        tmp_path,
        "check_interval: 5",
        "check_interval: 5.5",
    )

    with pytest.raises(ValueError, match="strategy.check_interval"):
        load_config(path)


def test_dex_is_normalized_to_lowercase(tmp_path):
    path = replaced_config(
        tmp_path,
        "dex: pancakeswap_v3",
        "dex: Uniswap_V3",
    )

    config = load_config(path)

    assert config.dex == "uniswap_v3"
    assert config.pool_address == UNISWAP_POOL


def test_unknown_dex_is_rejected(tmp_path):
    path = replaced_config(
        tmp_path,
        "dex: pancakeswap_v3",
        "dex: sushiswap_v3",
    )

    with pytest.raises(ValueError, match="dex must be one of"):
        load_config(path)


def test_selected_dex_profile_is_loaded(tmp_path):
    config = load_config(write_config(tmp_path))

    assert config.dex == "pancakeswap_v3"
    assert config.pool_address == PANCAKE_POOL
    assert config.position_manager_address == PANCAKE_POSITION_MANAGER
    assert config.position_token_id == 42
    assert config.swap_router_address == PANCAKE_ROUTER
    assert config.quoter_address == PANCAKE_QUOTER


def test_switching_dex_switches_every_address(tmp_path):
    path = replaced_config(
        tmp_path,
        "dex: pancakeswap_v3",
        "dex: uniswap_v3",
    )

    config = load_config(path)

    assert config.dex == "uniswap_v3"
    assert config.pool_address == UNISWAP_POOL
    assert config.position_manager_address == UNISWAP_POSITION_MANAGER
    assert config.position_token_id == 82740
    assert config.swap_router_address == UNISWAP_ROUTER
    assert config.quoter_address == UNISWAP_QUOTER


def test_missing_selected_dex_profile_is_rejected(tmp_path):
    path = replaced_config(
        tmp_path,
        "dex: pancakeswap_v3",
        "dex: uniswap_v3",
        ("  uniswap_v3:", "  unused_v3:"),
    )

    with pytest.raises(ValueError, match=r"dexes\.uniswap_v3 is missing"):
        load_config(path)


def test_dexes_must_be_a_mapping(tmp_path):
    block = BASE_CONFIG[
        BASE_CONFIG.index("dexes:") : BASE_CONFIG.index("strategy:")
    ]
    content = BASE_CONFIG.replace(block, "dexes: []\n\n")

    with pytest.raises(ValueError, match="dexes must map"):
        load_config(write_config(tmp_path, content))


def test_empty_pool_address_is_rejected(tmp_path):
    path = replaced_config(
        tmp_path,
        f'address: "{PANCAKE_POOL}"',
        'address: ""',
    )

    with pytest.raises(
        ValueError,
        match=r"dexes\.pancakeswap_v3\.pool\.address",
    ):
        load_config(path)


def test_malformed_pool_address_is_rejected(tmp_path):
    path = replaced_config(
        tmp_path,
        f'address: "{PANCAKE_POOL}"',
        'address: "0x123"',
    )

    with pytest.raises(
        ValueError,
        match=r"dexes\.pancakeswap_v3\.pool\.address",
    ):
        load_config(path)


def test_empty_position_manager_address_is_rejected(tmp_path):
    path = replaced_config(
        tmp_path,
        f'address: "{PANCAKE_POSITION_MANAGER}"',
        'address: ""',
    )

    with pytest.raises(
        ValueError,
        match=r"dexes\.pancakeswap_v3\.position_manager\.address",
    ):
        load_config(path)


def test_profile_sections_must_be_mappings(tmp_path):
    path = replaced_config(
        tmp_path,
        f"""        pool:
          address: "{PANCAKE_POOL}"
""",
        "        pool: []\n",
    )

    with pytest.raises(
        ValueError,
        match=r"dexes\.pancakeswap_v3\.pool must be a mapping",
    ):
        load_config(path)


def test_optional_router_and_quoter_may_be_empty(tmp_path):
    path = replaced_config(
        tmp_path,
        f'address: "{PANCAKE_ROUTER}"',
        'address: ""',
        (f'address: "{PANCAKE_QUOTER}"', 'address: ""'),
    )

    config = load_config(path)

    assert config.swap_router_address == ""
    assert config.quoter_address == ""


def test_unselected_profile_may_be_empty(tmp_path):
    content = f"""
network: 84532

networks:
  84532:
    name: base_sepolia
    rpc_url: https://sepolia.base.org
    dexes:
      pancakeswap_v3:
        pool:
          address: "{PANCAKE_POOL}"
        position_manager:
          address: "{PANCAKE_POSITION_MANAGER}"

      uniswap_v3: {{}}

dex: pancakeswap_v3

strategy:
  range_half_width: 0.01
  check_interval: 5
  fee_threshold_usd: 0.10

wallet:
  address: "0x87e58e8B5983FC4fF8199d3E16264ad39182a96e"
"""

    config = load_config(write_config(tmp_path, content))

    assert config.position_token_id is None
    assert config.swap_router_address == ""
    assert config.quoter_address == ""


def test_transaction_safety_defaults_are_backward_compatible(tmp_path):
    config = load_config(write_config(tmp_path))

    assert config.min_eth_balance_wei == 0
    assert config.tx_confirmations == 2
    assert config.tx_timeout_seconds == 180


def test_transaction_safety_settings_can_be_configured(tmp_path):
    path = replaced_config(
        tmp_path,
        "strategy:\n",
        """transaction:
  min_eth_balance: 0.0005
  confirmations: 3
  receipt_timeout_seconds: 42

strategy:
""",
    )

    config = load_config(path)

    assert config.min_eth_balance_wei == 500_000_000_000_000
    assert config.tx_confirmations == 3
    assert config.tx_timeout_seconds == 42


def test_negative_min_eth_balance_is_rejected(tmp_path):
    path = replaced_config(
        tmp_path,
        "strategy:\n",
        """transaction:
  min_eth_balance: -0.1

strategy:
""",
    )

    with pytest.raises(ValueError, match="transaction.min_eth_balance"):
        load_config(path)


def test_sub_wei_min_eth_balance_is_rejected(tmp_path):
    path = replaced_config(
        tmp_path,
        "strategy:\n",
        """transaction:
  min_eth_balance: 0.0000000000000000001

strategy:
""",
    )

    with pytest.raises(ValueError, match="at most 18 decimal places"):
        load_config(path)


def test_zero_transaction_confirmations_are_rejected(tmp_path):
    path = replaced_config(
        tmp_path,
        "strategy:\n",
        """transaction:
  confirmations: 0

strategy:
""",
    )

    with pytest.raises(ValueError, match="transaction.confirmations"):
        load_config(path)


def test_rpc_url_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_RPC_URL", "https://rpc.example/private")

    config = load_config(write_config(tmp_path))

    assert config.rpc_url == "https://rpc.example/private"


def test_rpc_url_falls_back_to_the_network_default(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("BASE_RPC_URL", raising=False)

    config = load_config(write_config(tmp_path))

    assert config.rpc_url == "https://sepolia.base.org"


def test_missing_rpc_url_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("BASE_RPC_URL", raising=False)
    path = replaced_config(
        tmp_path,
        'rpc_url: "${BASE_RPC_URL:-https://sepolia.base.org}"',
        'rpc_url: ""',
    )

    with pytest.raises(ValueError, match="RPC URL is empty"):
        load_config(path)


def test_networks_must_be_a_mapping(tmp_path):
    block = BASE_CONFIG[
        BASE_CONFIG.index("networks:") : BASE_CONFIG.index("dex:")
    ]
    content = BASE_CONFIG.replace(block, "networks: []\n\n")

    with pytest.raises(ValueError, match="networks must map"):
        load_config(write_config(tmp_path, content))


def test_network_must_be_a_chain_id(tmp_path):
    path = replaced_config(
        tmp_path,
        "network: 84532",
        "network: base_sepolia",
    )

    with pytest.raises(ValueError, match="network must be a chain id"):
        load_config(path)


def test_unknown_chain_id_is_rejected(tmp_path):
    path = replaced_config(
        tmp_path,
        "network: 84532",
        "network: 999999",
    )

    with pytest.raises(ValueError, match="Unknown chain_id"):
        load_config(path)


def test_unselected_network_profile_is_not_validated(tmp_path):
    content = BASE_CONFIG.replace(
        "\ndex: pancakeswap_v3",
        """
  8453:
    name: base
    rpc_url: https://mainnet.base.org
    dexes: {}

dex: pancakeswap_v3""",
    )

    config = load_config(write_config(tmp_path, content))

    assert config.expected_chain_id == 84532

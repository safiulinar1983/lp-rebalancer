"""Smoke tests for the manual CLI scripts in ``scripts/``.

Importing a script must not connect to an RPC endpoint, read config.yaml or
create the SQLite database: those side effects belong to ``main()``.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from blockchain.erc20 import MAX_UINT256
from scripts._common import check_wallet, dex_title
from scripts.approve_weth import parse_args as parse_approve_args

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

SCRIPTS = [
    "monitor_pool.py",
    "list_positions.py",
    "wrap_weth.py",
    "approve_weth.py",
    "mint_position.py",
    "check_wallet.py",
    "rebalance.py",
    "watch.py",
]

ARGPARSE_SCRIPTS = [
    "wrap_weth.py",
    "approve_weth.py",
    "mint_position.py",
    "watch.py",
]


def _script_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return env


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_import_has_no_side_effects(tmp_path, script):
    module_path = SCRIPTS_DIR / script

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runpy\n"
            f"runpy.run_path(r'{module_path}', run_name='lp_script_probe')\n",
        ],
        cwd=tmp_path,
        env=_script_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "data" / "lp_rebalancer.db").exists()


@pytest.mark.parametrize("script", ARGPARSE_SCRIPTS)
def test_script_help_does_not_touch_the_network(tmp_path, script):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script), "--help"],
        cwd=tmp_path,
        env=_script_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout.lower()


def test_approve_weth_defaults_to_unlimited_allowance():
    assert parse_approve_args([]).amount == MAX_UINT256


def test_approve_weth_accepts_an_exact_amount():
    assert parse_approve_args(["--amount", "123"]).amount == 123


def test_check_wallet_accepts_case_insensitive_match():
    check_wallet(
        "0x" + "a" * 40,
        "0x" + "A" * 40,
    )


def test_check_wallet_rejects_a_different_signer():
    with pytest.raises(RuntimeError, match="does not match wallet.address"):
        check_wallet("0x" + "a" * 40, "0x" + "b" * 40)


@pytest.mark.parametrize(
    ("dex", "title"),
    [
        ("uniswap_v3", "Uniswap V3"),
        ("PancakeSwap_v3", "PancakeSwap V3"),
        ("custom", "custom"),
    ],
)
def test_dex_title_is_human_readable(dex, title):
    assert dex_title(dex) == title


@pytest.mark.parametrize(
    "script",
    ["approve_weth.py", "mint_position.py", "rebalance.py", "wrap_weth.py"],
)
def test_signing_scripts_verify_the_configured_wallet(script):
    source = (SCRIPTS_DIR / script).read_text(encoding="utf-8")

    assert "check_wallet(config.wallet_address, account.address)" in source


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_supports_direct_execution(script):
    """`python scripts/<name>.py` must find the repository root imports."""
    source = (SCRIPTS_DIR / script).read_text(encoding="utf-8")

    assert 'if __package__ in (None, ""):' in source
    assert "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))" in source

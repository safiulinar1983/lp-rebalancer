"""Smoke tests for the manual CLI scripts in ``scripts/``.

Importing a script must not connect to an RPC endpoint, read config.yaml or
create the SQLite database: those side effects belong to ``main()``.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

SCRIPTS = [
    "monitor_pool.py",
    "list_positions.py",
    "wrap_weth.py",
    "approve_weth.py",
    "mint_position.py",
    "rebalance.py",
]

ARGPARSE_SCRIPTS = [
    "wrap_weth.py",
    "approve_weth.py",
    "mint_position.py",
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


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_supports_direct_execution(script):
    """`python scripts/<name>.py` must find the repository root imports."""
    source = (SCRIPTS_DIR / script).read_text(encoding="utf-8")

    assert 'if __package__ in (None, ""):' in source
    assert "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))" in source

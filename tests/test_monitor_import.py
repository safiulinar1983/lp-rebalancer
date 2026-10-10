import os
import subprocess
import sys
from pathlib import Path


def test_import_does_not_start_monitor_or_create_database(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)

    result = subprocess.run(
        [sys.executable, "-c", "import monitor_position"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "data" / "lp_rebalancer.db").exists()

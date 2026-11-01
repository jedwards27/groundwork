import subprocess
import sys

from groundwork.config import REPO_ROOT


def test_import_contracts_hold():
    exe = "lint-imports"
    result = subprocess.run(
        [sys.executable, "-m", "importlinter.cli"] if False else [exe],
        cwd=REPO_ROOT / "backend",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

"""The README's offline demo runs and checks its own steps against the paper FX account."""

import subprocess  # nosec B404 - runs this repo's own interpreter on a fixed script
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_paper_quick_demo_exercises_the_fx_account_and_passes():
    out = subprocess.run(  # nosec B603 - fixed argv, no shell
        [sys.executable, "-W", "ignore", str(ROOT / "examples" / "paper_quick_demo.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "every step checked out" in out.stdout and "FAIL" not in out.stdout
    assert "USDJPY" in out.stdout and "ETH" not in out.stdout

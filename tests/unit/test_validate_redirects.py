from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_validate_redirects_script_succeeds() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "validate_redirects.py"
    # Safe in test context: both executable and script path are resolved locally in this repository checkout.
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr

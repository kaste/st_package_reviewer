import os
import subprocess
from pathlib import Path


def test_action_script_imports_package_with_uv_project(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    action_py = repo_root / "gh_action" / "action.py"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(repo_root),
            "python",
            "-u",
            str(action_py),
            "--help",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Diff a channel/repository PR" in proc.stdout

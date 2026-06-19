import os
import subprocess
import sys
from pathlib import Path


def test_action_script_imports_from_checkout_without_cwd_on_path(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    action_py = repo_root / "gh_action" / "action.py"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, "-u", str(action_py), "--help"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Diff a channel/repository PR" in proc.stdout


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


def test_action_module_imports_with_package_context(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)

    proc = subprocess.run(
        [sys.executable, "-u", "-m", "gh_action.action", "--help"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Diff a channel/repository PR" in proc.stdout

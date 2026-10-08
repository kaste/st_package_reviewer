from contextlib import redirect_stdout
from pathlib import Path
import shlex
import shutil
import subprocess
from unittest.mock import Mock

import pytest

from gh_action import action
from gh_action._entry_checker import EntryReview
from st_package_reviewer import __main__ as cli
from st_package_reviewer.check.file.check_repo_tags import CheckRepoTags


@pytest.mark.parametrize("value, expected", [
    ("", []),
    ("CheckSettingsMenuEntry", ["CheckSettingsMenuEntry"]),
    (" CheckSettingsMenuEntry\n\n CheckLicense\tCheckOsSystemCalls ",
     ["CheckSettingsMenuEntry", "CheckLicense", "CheckOsSystemCalls"]),
    ("CheckSettingsMenuEntry\r\nCheckLicense\r\n", ["CheckSettingsMenuEntry", "CheckLicense"]),
])
def test_channel_action_reads_exclude_input(monkeypatch, value, expected):
    monkeypatch.setenv("INPUT_EXCLUDE", value)

    args = action.parse_args(["--pr", "https://github.com/example/channel/pull/1"])

    assert args.exclude == expected


@pytest.mark.parametrize("tags_mode", [False, True])
def test_channel_action_forwards_exclusions_to_reviewer(tmp_path, monkeypatch, tags_mode):
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("INPUT_EXCLUDE", "CheckSettingsMenuEntry\nCheckLicense\nCheckRepoTags")
    repo_url = "https://github.com/example/package"
    packages = ["Example", "Other"]
    for package in packages:
        package_dir = tmp_path / f"{package} package"
        package_dir.mkdir()
        (package_dir / f"{package}.sublime-settings").write_text("{}", encoding="utf-8")
        (package_dir / "plugin.py").write_text(
            "import os\nos.system('echo hello')\n", encoding="utf-8",
        )
    repo_check = Mock(side_effect=AssertionError("Excluded checker must not run"))
    monkeypatch.setattr(CheckRepoTags, "check", repo_check)
    stubs = {
        "command_exists": True,
        "fetch_pr_metadata": action.PrMeta("base", "head"),
        "setup_thecrawl": tmp_path,
        "describe_thecrawl_revision": "test revision",
        "generate_registry": action.RegistryGenerationResult(0, []),
        "load_registry_packages": {pkg: {} for pkg in packages},
        "diff_registry_packages": (packages, "Added Example, Other"),
        "run_sh": None,
        "load_package_entry_source": None,
        "review_package_entry": EntryReview(),
        "crawl_package": True,
        "check_pkg_crawl_mode": (tags_mode, repo_url, ["", "v"]),
        "write_tags_mode_registry": True,
        "parse_workspace_release": {"url": "https://example.com/package.zip", "version": "1.0.0"},
        "download_zip": True,
    }
    for name, result in stubs.items():
        monkeypatch.setattr(action, name, Mock(return_value=result))
    monkeypatch.setattr(action, "unzip_release",
                        lambda zipfile, workdir, pkg, ver, console: tmp_path / f"{pkg} package")
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        with redirect_stdout(kwargs["stdout"]):
            returncode = cli.main(list(args[args.index("st_package_reviewer") + 1:]))
        return subprocess.CompletedProcess(args, returncode)

    monkeypatch.setattr(action, "run", run)

    with pytest.raises(SystemExit) as exc:
        action.main([
            "--pr", "https://github.com/example/channel/pull/1",
            "--exclude", "CheckOsSystemCalls",
        ])

    assert exc.value.code == 0
    assert len(calls) == len(packages)
    repo_check.assert_not_called()
    for command in calls:
        assert command[command.index("--exclude"):-1] == (
            "--exclude", "CheckSettingsMenuEntry",
            "--exclude", "CheckLicense",
            "--exclude", "CheckRepoTags",
            "--exclude", "CheckOsSystemCalls",
        )
        if tags_mode:
            assert command[command.index("--repo"):command.index("--exclude")] == (
                "--repo", repo_url, "--tag-prefix", "", "--tag-prefix", "v",
            )
    review = (tmp_path / "review.md").read_text(encoding="utf-8")
    assert "missing 'Main.sublime-menu'" not in review
    assert "top-level LICENSE file" not in review
    assert "Consider replacing os.system" not in review


def test_channel_action_binds_exclude_input():
    action_path = Path(__file__).resolve().parents[1] / "gh_action" / "action.yml"
    source = action_path.read_text(encoding="utf-8")
    assert "  exclude:\n" in source.split("runs:", 1)[0]
    step = source.split("    - name: Run Package Reviewer\n", 1)[1].split("    - name:", 1)[0]
    assert "INPUT_EXCLUDE: ${{ inputs.exclude }}" in step


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required")
@pytest.mark.parametrize("other_options", [False, True])
@pytest.mark.parametrize("value, expected", [
    ("", []),
    ("CheckSettingsMenuEntry", ["--exclude", "CheckSettingsMenuEntry"]),
    ("CheckSettingsMenuEntry\r\nCheckLicense\r\n", [
        "--exclude", "CheckSettingsMenuEntry", "--exclude", "CheckLicense",
    ]),
    ("*", ["--exclude", "*"]),
    (" CheckSettingsMenuEntry\n\nCheckLicense\tCheckOsSystemCalls ", [
        "--exclude", "CheckSettingsMenuEntry",
        "--exclude", "CheckLicense",
        "--exclude", "CheckOsSystemCalls",
    ]),
])
def test_package_action_forwards_exclude_input(value, expected, other_options):
    action_path = Path(__file__).resolve().parents[1] / "gh_action_package" / "action.yml"
    source = action_path.read_text(encoding="utf-8")
    step = source.split("    - name: Run st_package_reviewer\n", 1)[1]
    assert "INPUT_EXCLUDE: ${{ inputs.exclude }}" in step
    script = step.split("      run: |\n", 1)[1]
    script = "\n".join(line[8:] for line in script.splitlines())
    script = script.replace("${{ github.action_path }}", "/action")
    # Capture uv's argument vector without building or reviewing a package.
    # The annotation pipeline is a passthrough here.
    script = (
        'uv() { printf "%s\\0" "$@"; }\n'
        'python() { while IFS= read -r -d "" arg; do printf "%s\\0" "$arg"; done; }\n'
        + script
    )
    inputs = {
        "INPUT_PATH": "package path",
        "INPUT_REPO": "",
        "INPUT_PACKAGE_NAME": "",
        "INPUT_ST_BUILD": "",
        "INPUT_EXCLUDE": value,
        "INPUT_FAIL_ON_WARNINGS": "false",
        "INPUT_COMPACT": "false",
    }
    if other_options:
        inputs.update({
            "INPUT_PACKAGE_NAME": "My Package",
            "INPUT_ST_BUILD": "4180",
            "INPUT_FAIL_ON_WARNINGS": "true",
            "INPUT_COMPACT": "true",
            "INPUT_REPO": "repo checkout",
        })
        expected = [
            "--package-name", "My Package", "--st-build", "4180", *expected,
            "--fail-on-warnings", "--compact", "--repo", "repo checkout",
        ]
    # Set inputs in the shell: Windows drops empty environment variables.
    assignments = "\n".join(f"{name}={shlex.quote(value)}" for name, value in inputs.items())
    script = "set +o igncr 2>/dev/null || true\n" + assignments + "\n" + script + "\n"

    proc = subprocess.run(["bash"], input=script.encode(), capture_output=True)

    assert proc.returncode == 0, proc.stderr.decode()
    assert proc.stdout.decode().split("\0")[:-1] == [
        "run", "--project", "/action/..", "st_package_reviewer", *expected, "package path",
    ], proc.stderr.decode()

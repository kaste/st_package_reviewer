from pathlib import Path
import shutil
import subprocess

import pytest

from st_package_reviewer.check.file.check_repo_tags import CheckRepoTags


pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is required")


def test_repo_tags_fails_when_no_tags(tmp_path):
    repo_path = _create_git_repo(tmp_path)

    checker = CheckRepoTags(repo_path, repo=str(repo_path))
    checker.perform_check()

    assert [failure.message for failure in checker.failures] == [
        "No semantic version tags found (no tags found at all)",
    ]
    assert not checker.warnings


def test_repo_tags_warns_for_only_prereleases(tmp_path):
    repo_path = _create_git_repo(tmp_path)
    _git(repo_path, "tag", "v1.0.0-beta.1")

    checker = CheckRepoTags(repo_path, repo=str(repo_path))
    checker.perform_check()

    assert not checker.failures
    assert [warning.message for warning in checker.warnings] == ["Only found pre-release tags."]
    assert any(
        notice.message.endswith("is tagged with 1.0.0-beta.1.")
        for notice in checker.notices
    )


def test_repo_tags_passes_with_final_semver(tmp_path):
    repo_path = _create_git_repo(tmp_path)
    _git(repo_path, "tag", "v1.0.0-beta.1")
    _git(repo_path, "tag", "v1.0.0")

    checker = CheckRepoTags(repo_path, repo=str(repo_path))
    checker.perform_check()

    assert not checker.failures
    assert not checker.warnings
    assert any(
        notice.message.endswith("is tagged with 1.0.0.")
        for notice in checker.notices
    )


def test_repo_tags_notices_when_tip_is_behind_latest_tag(tmp_path):
    repo_path = _create_git_repo(tmp_path)
    _git(repo_path, "tag", "v1.2.3")
    _commit_file(repo_path, "a.txt", "a\n")
    _commit_file(repo_path, "b.txt", "b\n")

    checker = CheckRepoTags(repo_path, repo=str(repo_path))
    checker.perform_check()

    assert not checker.failures
    assert not checker.warnings
    assert any(
        notice.message == "Latest version 1.2.3 is 2 commits behind tip of master."
        for notice in checker.notices
    )


def _create_git_repo(tmp_path):
    repo_path = Path(tmp_path, "repo")
    repo_path.mkdir()

    _git(repo_path, "init")
    _git(repo_path, "config", "user.name", "Test User")
    _git(repo_path, "config", "user.email", "test@example.com")

    readme_path = Path(repo_path, "README.md")
    readme_path.write_text("# test\n", encoding="utf-8")
    _git(repo_path, "add", "README.md")
    _git(repo_path, "commit", "-m", "init")

    return repo_path


def _commit_file(repo_path, name, content):
    file_path = Path(repo_path, name)
    file_path.write_text(content, encoding="utf-8")
    _git(repo_path, "add", name)
    _git(repo_path, "commit", "-m", "update {}".format(name))


def _git(repo_path, *args):
    subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )

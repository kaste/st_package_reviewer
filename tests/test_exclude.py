from unittest.mock import Mock

import pytest

from st_package_reviewer import __main__ as cli
from st_package_reviewer.check import file as file_c, repo as repo_c
from st_package_reviewer.check.file.check_repo_tags import CheckRepoTags


def test_cli_excludes_file_and_ast_checkers(tmp_path, capsys):
    (tmp_path / "Example.sublime-settings").write_text("{}", encoding="utf-8")
    (tmp_path / "plugin.py").write_text("import os\nos.system('echo hello')\n", encoding="utf-8")
    args = ["--compact", "--package-name", "Example", str(tmp_path)]

    assert cli.main(args) == 0
    baseline = capsys.readouterr().out
    assert "missing 'Main.sublime-menu'" in baseline
    assert "Consider replacing os.system" in baseline

    assert cli.main([
        "--exclude", "CheckSettingsMenuEntry",
        "--exclude", "CheckOsSystemCalls",
        *args,
    ]) == 0
    excluded = capsys.readouterr().out
    assert "missing 'Main.sublime-menu'" not in excluded
    assert "Consider replacing os.system" not in excluded
    assert "top-level LICENSE file" in excluded


@pytest.mark.parametrize("exclude", [(), ("UnknownChecker",), ("checklicense",)])
def test_cli_keeps_default_checks_for_unknown_or_mismatched_names(tmp_path, capsys, exclude):
    (tmp_path / "plugin.py").write_text("", encoding="utf-8")
    args = ["--fail-on-warnings", "--compact", str(tmp_path)]
    for name in exclude:
        args.extend(["--exclude", name])

    assert cli.main(args) == 1
    assert "top-level LICENSE file" in capsys.readouterr().out

    assert cli.main(["--exclude", "CheckLicense", *args]) == 0
    assert "top-level LICENSE file" not in capsys.readouterr().out


def test_cli_excludes_local_repository_checker(tmp_path, monkeypatch, capsys):
    (tmp_path / "plugin.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(CheckRepoTags, "check", lambda self: self.fail("Repository failure"))
    args = ["--compact", "--repo=.", str(tmp_path)]

    assert cli.main(args) == 1
    assert "Repository failure" in capsys.readouterr().out

    assert cli.main(["--exclude", "CheckRepoTags", *args]) == 0
    report = capsys.readouterr().out
    assert "Repository failure" not in report
    assert "top-level LICENSE file" in report


@pytest.mark.parametrize("repo_only", [False, True])
def test_cli_excludes_remote_repository_checker(tmp_path, monkeypatch, capsys, repo_only):
    (tmp_path / "plugin.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(cli.repo_tools, "download", Mock(return_value=tmp_path))
    repo = Mock(ratelimit_remaining=100)
    repo.tags.return_value = []
    repo.readme.return_value = None
    github = Mock()
    github.repository.return_value = repo
    monkeypatch.setattr(cli, "GitHub", lambda: github)
    args = ["https://github.com/example/package"]
    if repo_only:
        args.insert(0, "--repo-only")

    assert cli.main(args) == 2
    baseline = capsys.readouterr().out
    assert "Missing a README file" in baseline
    assert "No semantic version tags found" in baseline

    assert cli.main(["--exclude", "CheckReadme", *args]) == 2
    report = capsys.readouterr().out
    assert "Missing a README file" not in report
    assert "No semantic version tags found" in report

    assert cli.main([
        "--exclude", "CheckReadme", "--exclude", "CheckSemverTags",
        "--exclude", "CheckLicense", *args,
    ]) == 0
    assert "top-level LICENSE file" not in capsys.readouterr().out


@pytest.mark.parametrize("interactive", [False, True])
def test_cli_keeps_exclusions_for_every_package(tmp_path, monkeypatch, capsys, interactive):
    (tmp_path / "plugin.py").write_text("", encoding="utf-8")
    args = ["--compact", "--fail-on-warnings", "--exclude", "CheckLicense"]
    if interactive:
        monkeypatch.setattr("builtins.input",
                            Mock(side_effect=[str(tmp_path), str(tmp_path), EOFError]))
    else:
        args.extend([str(tmp_path), str(tmp_path)])

    assert cli.main(args) == 0
    report = capsys.readouterr().out
    assert report.count("No failures, no warnings.") == 2
    assert "top-level LICENSE file" not in report


def test_cli_requires_a_class_name():
    with pytest.raises(SystemExit) as exc:
        cli.main(["--exclude"])

    assert exc.value.code == 2


def test_file_discovery_preserves_ast_base_exclusion_and_cached_defaults():
    defaults = file_c.get_checkers()
    excluded_names = ("CheckSettingsMenuEntry", "CheckOsSystemCalls")
    filtered = file_c.get_checkers(exclude=excluded_names)

    assert filtered == tuple(cls for cls in defaults if cls.__name__ not in excluded_names)
    assert not any(cls.__name__ == "AstChecker" for cls in filtered)
    assert file_c.get_checkers() == defaults


def test_repository_discovery_excludes_named_classes():
    defaults = repo_c.get_checkers()
    filtered = repo_c.get_checkers(exclude=("CheckReadme",))

    assert filtered == tuple(cls for cls in defaults if cls.__name__ != "CheckReadme")
    assert repo_c.get_checkers() == defaults

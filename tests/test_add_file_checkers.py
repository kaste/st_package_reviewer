from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

from st_package_reviewer import __main__ as cli
from st_package_reviewer.check import file as file_c
from st_package_reviewer.runner import CheckRunner


@pytest.mark.parametrize("with_init", [False, True], ids=["namespace-package", "regular-package"])
def test_loads_package_with_relative_helpers_and_nested_modules(tmp_path, with_init):
    addon = tmp_path / "not a Python identifier"
    addon.mkdir()
    (addon / "_helpers.py").write_text('MESSAGE = "Hello from the addon"\n', encoding="utf-8")
    if with_init:
        (addon / "__init__.py").write_text("from ._helpers import MESSAGE\n", encoding="utf-8")
    nested = addon / "nested"
    nested.mkdir()
    if with_init:
        (nested / "__init__.py").write_text("", encoding="utf-8")
    helper_import = "from .. import MESSAGE\n" if with_init else "from .._helpers import MESSAGE\n"
    (nested / "check_extra.py").write_text(
        "from st_package_reviewer.check.file import FileChecker\n"
        + helper_import
        + "class ExtraHello(FileChecker):\n"
        "    def check(self):\n"
        "        self.notice(MESSAGE)\n", encoding="utf-8",
    )
    defaults = file_c.get_checkers()
    checkers = file_c.get_checkers(additional_paths=[addon])
    runner = CheckRunner([cls for cls in checkers if cls not in defaults])

    runner.run(tmp_path)

    assert checkers[:len(defaults)] == defaults
    assert [notice.message for notice in runner.notices] == ["Hello from the addon"]
    assert not runner.errors


@pytest.mark.parametrize("with_init", [False, True], ids=["namespace-package", "regular-package"])
def test_same_named_directories_do_not_shadow_packages_or_change_sys_path(tmp_path, with_init):
    first = tmp_path / "one" / "st_package_reviewer"
    second = tmp_path / "two" / "st_package_reviewer"
    for addon, message in [(first, "First addon"), (second, "Second addon")]:
        addon.mkdir(parents=True)
        if with_init:
            (addon / "__init__.py").write_text("", encoding="utf-8")
        (addon / "_helpers.py").write_text(f"MESSAGE = {message!r}\n", encoding="utf-8")
        (addon / "check_extra.py").write_text(
            "from st_package_reviewer.check.file import FileChecker\n"
            "from ._helpers import MESSAGE\n"
            "class DuplicateExtra(FileChecker):\n"
            "    def check(self):\n"
            "        self.fail(MESSAGE)\n", encoding="utf-8",
        )
    original_path = sys.path[:]
    reviewer = sys.modules["st_package_reviewer"]
    defaults = file_c.get_checkers()

    checkers = file_c.get_checkers(additional_paths=[first, second])
    extra = [cls for cls in checkers if cls not in defaults]
    runner = CheckRunner(extra)
    runner.run(tmp_path)

    assert len(extra) == 2
    assert extra[0].__name__ == extra[1].__name__ == "DuplicateExtra"
    assert extra[0].__module__ != extra[1].__module__
    assert [failure.message for failure in runner.failures] == ["First addon", "Second addon"]
    assert not runner.errors
    assert sys.path == original_path
    assert sys.modules["st_package_reviewer"] is reviewer
    assert file_c.get_checkers(additional_paths=[first, first / ".", second]) == checkers
    assert file_c.get_checkers(
        exclude=("DuplicateExtra",), additional_paths=[first, second],
    ) == defaults


def test_additional_file_and_ast_checkers_respect_exclusions(tmp_path):
    addon = _make_addon(tmp_path / "checks", "ExtraFile")
    (addon / "check_ast.py").write_text(
        "from st_package_reviewer.check.file.ast import AstChecker\n"
        "from st_package_reviewer.check.repo import RepoChecker\n"
        "class ExtraAst(AstChecker):\n"
        "    def visit_Call(self, node):\n"
        "        self.fail('Extra AST failure')\n"
        "class NotAFileChecker(RepoChecker):\n"
        "    def check(self):\n"
        "        self.fail('Must not run as a file checker')\n", encoding="utf-8",
    )
    defaults = file_c.get_checkers()
    checkers = file_c.get_checkers(additional_paths=[addon])
    extra = [cls for cls in checkers if cls not in defaults]
    assert {cls.__name__ for cls in extra} == {"ExtraFile", "ExtraAst"}
    assert not any(cls.__name__ == "AstChecker" for cls in checkers)
    package = tmp_path / "package"
    package.mkdir()
    (package / "plugin.py").write_text("print('hello')\n", encoding="utf-8")
    runner = CheckRunner(extra)

    runner.run(package)

    assert [failure.message for failure in runner.failures] == [
        "Extra AST failure", "ExtraFile failure",
    ]
    assert not runner.errors
    assert file_c.get_checkers(
        exclude=("ExtraFile", "ExtraAst"), additional_paths=[addon],
    ) == defaults
    assert file_c.get_checkers() == defaults


def test_import_error_has_addon_path_and_can_be_retried(tmp_path):
    addon = _make_addon(tmp_path / "checks", "RetryExtra")
    (addon / "broken.py").write_text("import nonexistent_addon_dependency\n", encoding="utf-8")

    with pytest.raises(ImportError) as exc:
        file_c.get_checkers(additional_paths=[addon])

    assert str(addon) in str(exc.value)
    assert "nonexistent_addon_dependency" in str(exc.value)
    (addon / "broken.py").write_text("# Fixed dependency import.\n", encoding="utf-8")
    assert "RetryExtra" in {
        cls.__name__ for cls in file_c.get_checkers(additional_paths=[addon])
    }


@pytest.mark.parametrize("kind", ["missing", "file", "broken_module", "broken_init"])
def test_cli_reports_bad_addons_before_any_review(tmp_path, monkeypatch, capsys, kind):
    addon = tmp_path / "checks"
    if kind == "file":
        addon.write_text("not a directory", encoding="utf-8")
    elif kind in ("broken_module", "broken_init"):
        addon.mkdir()
        target = "__init__.py" if kind == "broken_init" else "check_broken.py"
        (addon / target).write_text("raise RuntimeError('Addon cannot load')\n", encoding="utf-8")
    github = Mock()
    monkeypatch.setattr(cli, "GitHub", github)

    with pytest.raises(SystemExit) as exc:
        cli.main(["--add-file-checkers", str(addon), str(tmp_path)])

    assert exc.value.code == 2
    assert str(addon) in capsys.readouterr().err
    github.assert_not_called()


def test_cli_appends_repeated_relative_addons_and_passes_metadata(tmp_path, monkeypatch, capsys):
    first = _make_addon(tmp_path / "first checks", "FirstExtra")
    second = _make_addon(tmp_path / "second checks", "SecondExtra")
    (second / "check_metadata.py").write_text(
        "from st_package_reviewer.check.file import FileChecker\n"
        "class MetadataExtra(FileChecker):\n"
        "    def check(self):\n"
        "        self.notice(f'{self.package_name}: {self.st_build}, {self.platforms}')\n",
        encoding="utf-8",
    )
    package = tmp_path / "package"
    package.mkdir()
    (package / "plugin.py").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert cli.main([
        "--add-file-checkers", first.name,
        "--add-file-checkers", second.name,
        "--exclude", "SecondExtra", "--package-name", "Fun",
        "--st-build", "4169", "--platforms", "linux", str(package),
    ]) == 1
    report = capsys.readouterr().out
    assert "FirstExtra failure" in report
    assert "SecondExtra failure" not in report
    assert "Fun: 4169, ('linux',)" in report
    assert "top-level LICENSE file" in report


def test_addon_path_expands_home_directory(tmp_path, monkeypatch):
    _make_addon(tmp_path / "checks", "HomeExtra")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    checkers = file_c.get_checkers(additional_paths=[Path("~/checks")])

    assert "HomeExtra" in {cls.__name__ for cls in checkers}


def _make_addon(path, class_name):
    path.mkdir(parents=True)
    (path / "check_extra.py").write_text(
        "from st_package_reviewer.check.file import FileChecker\n"
        f"class {class_name}(FileChecker):\n"
        "    def check(self):\n"
        f"        self.fail('{class_name} failure')\n", encoding="utf-8",
    )
    return path

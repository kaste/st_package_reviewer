from collections import namedtuple
import logging
from pathlib import Path
import re
import sys

import pytest

from st_package_reviewer.runner import CheckRunner
from st_package_reviewer.check import file as file_c
from st_package_reviewer.check.file.ast.check_initialized_api import CheckInitializedApiUsage
from st_package_reviewer.check.file.check_redundant_files import CheckRootInitContents
from st_package_reviewer.check.file.check_resource_file_validity import CheckJsoncFiles
from st_package_reviewer.check.file.check_resource_files import (
    CheckHasResourceFiles,
    CheckMainMenuStructure,
    CheckPluginsInRoot,
)
from st_package_reviewer.check.file.ast.sublime_api_classes import (
    SUBLIME_API_CLASS_BUILDS,
)


def _collect_test_packages():
    this_dir = Path(__file__).with_name("packages")
    for package_path in this_dir.iterdir():
        if not package_path.is_dir():
            continue
        yield package_path


test_packages = list(_collect_test_packages())


@pytest.fixture(scope='function', params=test_packages, ids=[p.name for p in test_packages])
def package_path(request):
    """Path to a package to be tested."""
    return request.param


@pytest.fixture(scope='function')
def check_runner():
    """Return an initialized CheckRunner with all file checkers."""
    checkers = []
    checkers.extend(file_c.get_checkers())
    return CheckRunner(checkers)


def config_logging():
    # Ensure we see debug output if tests fail
    logger = logging.getLogger("st_package_reviewer")
    # pytest now tracks log calls separately
    # logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG)


config_logging()


##############################################################################


CheckAssert = namedtuple("CheckAssert", "message details")


def _find_check_file(base_path):
    """Determine file with the latest version suffix."""
    check_paths = sorted(base_path.parent.glob(base_path.stem + "*"))
    file_path = None
    for candidate in check_paths:
        if candidate.suffix and (match := re.match(r"^\.py(\d)(\d+)$", candidate.suffix)):
            major, minor = match.groups()
            if (int(major), int(minor)) > sys.version_info[:2]:
                continue
        file_path = candidate
    return file_path


def _read_check_asserts(base_path):
    """Read CheckAsserts from file."""
    asserts = set()
    file_path = _find_check_file(base_path)
    if file_path:
        # Ensure UTF-8 so Unicode assertions (e.g., 'Ü') read correctly across platforms,
        # and by that we mean ... well Windows.
        with file_path.open('r', encoding='utf-8') as f:
            message = None
            details = []
            line_iter = iter(f)

            line = next(line_iter)
            while line:
                assert line.startswith('- ')
                message = line[2:].strip()
                details = []

                in_fenced_block = False
                for line in line_iter:
                    if not line.startswith(' '):
                        break

                    stripped_line = line.strip()
                    if in_fenced_block or stripped_line.startswith("```"):
                        message += "\n" + line.rstrip("\r\n")
                        if stripped_line.startswith("```"):
                            in_fenced_block = not in_fenced_block
                    else:
                        details.append(stripped_line)
                else:
                    line = None

                asserts.add(CheckAssert(message, tuple(details)))

    return asserts


def test_reviewer_integration(package_path, check_runner):
    """Run checks over a package and check if specified failures or warnings were emitted.

    Test packages can specify the minimum required failures (or warnings)
    in files named "failures" and "warnings" respectively.
    If all failures or warnings should be compared,
    specify them in "all_failures" and "all_warnings".

    A package can optionally define metadata files. If present, their content is
    passed to file checkers.
    """
    check_kwargs = {}
    package_name_file = Path(package_path, "package_name")
    if package_name_file.is_file():
        check_kwargs["package_name"] = package_name_file.read_text(encoding='utf-8').strip()

    st_build_file = Path(package_path, "st_build")
    if st_build_file.is_file():
        check_kwargs["st_build"] = int(st_build_file.read_text(encoding='utf-8').strip())

    platforms_file = Path(package_path, "platforms")
    if platforms_file.is_file():
        check_kwargs["platforms"] = platforms_file.read_text(encoding='utf-8').strip()

    # Run checks first and report them to stdout,
    # so we have something to inspect when the test fails.
    check_runner.run(package_path, **check_kwargs)
    check_runner.report()

    failure_asserts = _read_check_asserts(Path(package_path, "failures"))
    all_failure_asserts = _read_check_asserts(Path(package_path, "all_failures"))
    assert not (failure_asserts and all_failure_asserts), \
        "Only one failures meta file is allowed"

    warning_asserts = _read_check_asserts(Path(package_path, "warnings"))
    all_warning_asserts = _read_check_asserts(Path(package_path, "all_warnings"))
    assert not (warning_asserts and all_warning_asserts), \
        "Only one warnings meta file is allowed"

    notice_asserts = _read_check_asserts(Path(package_path, "notices"))
    all_notice_asserts = _read_check_asserts(Path(package_path, "all_notices"))
    assert not (notice_asserts and all_notice_asserts), \
        "Only one notices meta file is allowed"

    assert_none = not (failure_asserts or all_failure_asserts
                       or warning_asserts or all_warning_asserts
                       or notice_asserts or all_notice_asserts)

    failures = {CheckAssert(failure.message, failure.details)
                for failure in check_runner.failures}
    assert len(failures) == len(check_runner.failures), "TODO: Revisit tests"
    warnings = {CheckAssert(warning.message, warning.details)
                for warning in check_runner.warnings}
    assert len(warnings) == len(check_runner.warnings), "TODO: Revisit tests"
    notices = {CheckAssert(notice.message, notice.details)
               for notice in check_runner.notices}
    assert len(notices) == len(check_runner.notices), "TODO: Revisit tests"

    if assert_none:
        assert not failures and not warnings and not notices
    else:
        if all_failure_asserts:
            assert failures == all_failure_asserts
        elif failure_asserts:
            assert failures >= failure_asserts

        if all_warning_asserts:
            assert warnings == all_warning_asserts
        elif warning_asserts:
            assert warnings >= warning_asserts

        if all_notice_asserts:
            assert notices == all_notice_asserts
        elif notice_asserts:
            assert notices >= notice_asserts

    if failures:
        assert not check_runner.result()


@pytest.mark.parametrize("relative_path", [
    "Example.sublime-file-icons",
    "icons/Example.sublime-file-icons",
])
def test_file_icons_count_as_resources_and_allow_jsonc(tmp_path, relative_path):
    icons_path = tmp_path / relative_path
    icons_path.parent.mkdir(parents=True, exist_ok=True)
    icons_path.write_text(
        '{\n// File icon mappings\n"icons": {"example.txt": "file_type_text",},\n}\n',
        encoding="utf-8",
    )

    check_runner = CheckRunner([CheckHasResourceFiles, CheckJsoncFiles])
    check_runner.run(tmp_path)

    assert not check_runner.failures
    assert not check_runner.warnings
    assert not check_runner.notices


@pytest.mark.parametrize("relative_path", [
    "Example.sublime-file-icons",
    "icons/Example.sublime-file-icons",
])
def test_file_icons_invalid_jsonc_is_reported(tmp_path, relative_path):
    icons_path = tmp_path / relative_path
    icons_path.parent.mkdir(parents=True, exist_ok=True)
    icons_path.write_text('{"icons":', encoding="utf-8")

    checker = CheckJsoncFiles(tmp_path)
    checker.perform_check()

    assert len(checker.failures) == 1
    failure = checker.failures[0]
    assert failure.message == "Invalid JSON (with comments)"
    assert failure.context == ("File: {}".format(relative_path),)


def test_nested_main_menu_structure_warning_includes_relative_path(tmp_path):
    menu_path = tmp_path / "resources" / "Main.sublime-menu"
    menu_path.parent.mkdir()
    menu_path.write_text(
        '[{"id": "preferences", "menu": '
        '[{"id": "package_settings", "menu": []}]}]\n',
        encoding="utf-8",
    )

    checker = CheckMainMenuStructure(tmp_path, package_name="Example")
    checker.perform_check()

    assert len(checker.warnings) == 2
    assert all(
        warning.context == ("File: resources/Main.sublime-menu",)
        for warning in checker.warnings
    )


def test_commented_commands_referenced_from_main_menu_are_silent(tmp_path):
    commands_path = tmp_path / "Example.sublime-commands"
    commands_path.write_text(
        '[\n// { "caption": "Example", "command": "example" }\n]\n',
        encoding="utf-8",
    )
    (tmp_path / "Main.sublime-menu").write_text(
        '[{"args": {"base_file": "${packages}/Example/Example.sublime-commands"}}]\n',
        encoding="utf-8",
    )

    checker = CheckJsoncFiles(tmp_path)
    checker.perform_check()

    assert not checker.failures
    assert not checker.warnings
    assert not checker.notices


@pytest.mark.parametrize(
    "contents",
    [
        b"",
        b"\n  \n# Kept for tooling.\n",
        "# Kept for tooling: \N{SNOWMAN}\n".encode(),
        b"# -*- coding: latin-1 -*-\n# \xe4\n",
    ],
)
def test_root_init_allows_empty_or_comment_only_files(tmp_path, contents):
    (tmp_path / "__init__.py").write_bytes(contents)

    checker = CheckRootInitContents(tmp_path)
    checker.perform_check()

    assert not checker.failures


@pytest.mark.parametrize(
    "contents",
    [
        b"VALUE = 1\n",
        b'"""Package docstring."""\n',
        b"pass\n",
        b"\\\n",
    ],
)
def test_root_init_rejects_python_code(tmp_path, contents):
    (tmp_path / "__init__.py").write_bytes(contents)

    checker = CheckRootInitContents(tmp_path)
    checker.perform_check()

    assert [failure.message for failure in checker.failures] == [
        "The root-level '__init__.py' must be empty or contain only comments. "
        "Package Control discards this file during installation to avoid "
        "Sublime Text reload errors, so it cannot be used as the entrypoint "
        "for your package. You may also want to remove it if it is not needed "
        "by your development tooling."
    ]


def test_root_init_does_not_count_as_an_installed_plugin(tmp_path):
    (tmp_path / "__init__.py").write_text("# Kept for tooling.\n", encoding="utf-8")
    module_path = tmp_path / "helper" / "module.py"
    module_path.parent.mkdir()
    module_path.write_text("VALUE = 1\n", encoding="utf-8")

    plugin_checker = CheckPluginsInRoot(tmp_path)
    plugin_checker.perform_check()
    resource_checker = CheckHasResourceFiles(tmp_path)
    resource_checker.perform_check()

    assert [failure.message for failure in plugin_checker.failures] == [
        "The package contains 1 Python file(s), but none of them are in the "
        "package root and no build system is specified"
    ]
    assert [failure.message for failure in resource_checker.failures] == [
        "The package does not define any file that interfaces with Sublime Text"
    ]


def test_ast_checkers_ignore_root_init(tmp_path):
    (tmp_path / "__init__.py").write_text(
        "import sublime\nsublime.load_settings('Example.sublime-settings')\n",
        encoding="utf-8",
    )

    checker = CheckInitializedApiUsage(tmp_path, st_build=4169)
    checker.perform_check()

    assert not checker.failures


def test_initialized_api_metadata_records_completion_item_build():
    assert SUBLIME_API_CLASS_BUILDS["CompletionItem"] == 4050


def test_initialized_api_suggestion_is_attached_to_failure():
    package_path = Path(__file__).with_name("packages") / "InitializedApiUsage"
    check_runner = CheckRunner([CheckInitializedApiUsage])

    check_runner.run(package_path, st_build=4169)

    assert not check_runner.notices
    assert check_runner.failures
    for failure in check_runner.failures:
        assert failure.message.endswith(
            CheckInitializedApiUsage.API_IMPORT_READY_SUGGESTION
        )

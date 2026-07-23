from subprocess import CompletedProcess

import pytest

from gh_action.action import (
    DEFAULT_REVIEW_ST_BUILD,
    describe_thecrawl_revision,
    extract_effective_tag_prefixes,
    parse_sublime_text_min,
    resolve_package_platforms,
    resolve_package_required_st_build,
)


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        (None, 0),
        ("", 4000),
        ("*", 4000),
        ("  *  ", 4000),
        ("<4090", 0),
        ("<=4090", 0),
        (">=4171", 4171),
        (">4171", 4172),
        ("3000-4100", 3000),
        ("4171", 4171),
        (">= 4171", 4171),
        ("nonsense", 0),
    ],
)
def test_parse_sublime_text_min(selector, expected):
    assert parse_sublime_text_min(selector) == expected


def test_describe_thecrawl_revision_reports_ref_and_worktree(monkeypatch, tmp_path):
    outputs = {
        "rev-parse": (0, "7416d45ed9f2\n"),
        "symbolic-ref": (0, "main\n"),
        "status": (0, " M package.py\n"),
    }

    def fake_run(*args, **kwargs):
        returncode, stdout = outputs[args[3]]
        return CompletedProcess(args, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr("gh_action.action.run", fake_run)

    assert describe_thecrawl_revision(tmp_path) == "7416d45ed9f2 (main, dirty)"


def test_describe_thecrawl_revision_handles_non_git_directory(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        return CompletedProcess(args, 128, stdout="", stderr="not a git repository")

    monkeypatch.setattr("gh_action.action.run", fake_run)

    assert describe_thecrawl_revision(tmp_path) == "unknown (not a Git checkout)"


def test_extract_effective_tag_prefixes_preserves_registry_semantics():
    package = {
        "releases": [
            {"tags": True},
            {"tags": "st4-v"},
            {"tags": "st4-v", "platforms": ["windows"]},
            {"branch": True},
        ],
    }

    assert extract_effective_tag_prefixes(package) == ("", "st4-v")


def test_extract_effective_tag_prefixes_ignores_invalid_releases():
    assert extract_effective_tag_prefixes({}) == ()
    assert extract_effective_tag_prefixes({"releases": [None, {"tags": False}]}) == ()


def test_resolve_package_required_st_build_uses_maximum():
    package_definition = {
        "releases": [
            {"sublime_text": "*"},
            {"sublime_text": ">=4107"},
            {"sublime_text": ">=4171"},
        ],
    }

    assert resolve_package_required_st_build(package_definition) == 4171


def test_resolve_package_required_st_build_respects_legacy_opt_in():
    package_definition = {
        "releases": [
            {"url": "https://example.com/pkg.zip"},
            {"sublime_text": "<=4000"},
        ],
    }

    assert resolve_package_required_st_build(package_definition) == 0


def test_resolve_package_required_st_build_defaults_when_unspecified():
    package_definition = {
        "releases": [
            {"url": "https://example.com/pkg.zip"},
        ],
    }

    assert resolve_package_required_st_build(package_definition) == DEFAULT_REVIEW_ST_BUILD


def test_resolve_package_platforms_defaults_to_all():
    package_definition = {
        "releases": [
            {"url": "https://example.com/pkg.zip"},
        ],
    }

    assert resolve_package_platforms(package_definition) == ("all",)


def test_resolve_package_platforms_normalizes_sub_platforms():
    package_definition = {
        "releases": [
            {"platforms": ["windows-x64", "linux"]},
            {"platforms": "linux-x64"},
        ],
    }

    assert resolve_package_platforms(package_definition) == ("windows", "linux")


def test_resolve_package_platforms_all_wins():
    package_definition = {
        "releases": [
            {"platforms": ["windows"]},
            {"platforms": ["*"]},
        ],
    }

    assert resolve_package_platforms(package_definition) == ("all",)

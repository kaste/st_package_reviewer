import pytest

from gh_action.action import (
    DEFAULT_REVIEW_ST_BUILD,
    parse_sublime_text_min,
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

import json

from gh_action.action import combine_entry_and_package_review
from gh_action._entry_checker import (
    EntryReview,
    extract_package_entries,
    load_package_entry_source,
    review_package_entry,
)


class DummyConsole:
    def write(self, message: str) -> None:
        pass


def test_entry_review_warns_about_redundant_details_fields():
    package_definition = {
        "name": "KeyBindingReport",
        "details": "https://github.com/vwheeler63/KeyBindingReport",
        "author": "vwheeler63",
        "issues": "https://github.com/vwheeler63/KeyBindingReport/issues",
        "releases": [{"sublime_text": "*", "tags": True}],
    }
    review = review_package_entry(
        "KeyBindingReport",
        package_definition,
        source_for(package_definition),
    )

    assert review.failures == []
    assert review.notices == []
    assert review.warnings == [
        "`author` is set to `vwheeler63`, which can be derived from "
        "`details`. Omit it unless it differs from the repository owner.",
        "`name` is set to `KeyBindingReport`, which can be derived from "
        "`details`. Omit it unless the display name differs from the "
        "repository name.",
        "`issues` is set to the standard issue tracker URL "
        "`https://github.com/vwheeler63/KeyBindingReport/issues`, which can "
        "be derived from `details`.",
    ]


def test_entry_review_allows_different_display_name_and_author():
    package_definition = {
        "name": "Key Binding Report",
        "details": "https://github.com/vwheeler63/KeyBindingReport",
        "author": "Victoria Wheeler",
        "issues": "https://example.com/issues",
        "releases": [{"sublime_text": "*", "tags": True}],
    }
    review = review_package_entry(
        "Key Binding Report",
        package_definition,
        source_for(package_definition),
    )

    assert review.empty


def test_entry_review_warns_about_redundant_single_author_array():
    package_definition = {
        "details": "https://github.com/vwheeler63/KeyBindingReport",
        "author": ["vwheeler63"],
        "releases": [{"sublime_text": "*", "tags": True}],
    }
    review = review_package_entry(
        "KeyBindingReport",
        package_definition,
        source_for(package_definition),
    )

    assert review.warnings == [
        "`author` is set to [`vwheeler63`], which can be derived from "
        "`details`. Omit it unless it differs from the repository owner; if "
        "you keep it, prefer a simple string unless there are multiple "
        "authors."
    ]


def test_entry_review_warns_about_single_author_array():
    package_definition = {
        "details": "https://github.com/vwheeler63/KeyBindingReport",
        "author": ["Victoria Wheeler"],
        "releases": [{"sublime_text": "*", "tags": True}],
    }
    review = review_package_entry(
        "KeyBindingReport",
        package_definition,
        source_for(package_definition),
    )

    assert review.warnings == [
        "`author` is set to a single-item array. Prefer a simple string "
        "unless there are multiple authors."
    ]


def test_entry_review_warns_about_standard_gitlab_issues_url():
    package_definition = {
        "details": "https://gitlab.com/example/Example",
        "issues": "https://gitlab.com/example/Example/-/issues/",
        "releases": [{"sublime_text": "*", "tags": True}],
    }
    review = review_package_entry(
        "Example",
        package_definition,
        source_for(package_definition),
    )

    assert review.warnings == [
        "`issues` is set to the standard issue tracker URL "
        "`https://gitlab.com/example/Example/-/issues/`, which can be "
        "derived from `details`."
    ]


def test_entry_review_allows_different_generated_name_without_source_entry():
    review = review_package_entry(
        "Display Name",
        {
            "name": "Display Name",
            "details": "https://github.com/example/Example",
            "releases": [{"sublime_text": "*", "tags": True}],
        },
    )

    assert review.empty


def test_entry_review_skips_redundant_name_check_without_source_entry():
    review = review_package_entry(
        "Example",
        {
            "name": "Example",
            "details": "https://github.com/example/Example",
            "author": "example",
            "issues": "https://github.com/example/Example/issues",
            "releases": [{"sublime_text": "*", "tags": True}],
        },
    )

    assert review.warnings == [
        "`author` is set to `example`, which can be derived from "
        "`details`. Omit it unless it differs from the repository owner.",
        "`issues` is set to the standard issue tracker URL "
        "`https://github.com/example/Example/issues`, which can be derived "
        "from `details`.",
    ]


def test_entry_review_notices_all_branch_based_releases():
    review = review_package_entry(
        "Example",
        {
            "details": "https://github.com/example/Example",
            "releases": [
                {"sublime_text": "*", "branch": "main"},
                {"sublime_text": "<4100", "branch": "st3"},
            ],
        },
    )

    assert review.notices == [
        "Tip: `Example` only defines branch-based releases. Consider adding at "
        "least one `tags: true` release so Package Control can install stable "
        "tagged versions."
    ]


def test_entry_review_checks_only_named_source_entry():
    source = (
        '{\n'
        '\t"schema_version": "3.0.0",\n'
        '\t"packages": [\n'
        '\t\t{\n'
        '\t\t\t"name": "Alpha",\n'
        '\t\t\t"details": "https://github.com/example/Alpha"\n'
        '\t\t},\n'
        '\t\t{\n'
        '    "name": "Zulu",\n'
        '\t\t\t"details": "https://github.com/example/Zulu"\n'
        '\t\t}\n'
        '\t]\n'
        '}\n'
    )

    review = review_package_entry(
        "Alpha",
        {"details": "https://github.com/example/Alpha"},
        source,
    )

    assert review.failures == []

    review = review_package_entry(
        "Zulu",
        {"details": "https://github.com/example/Zulu"},
        source,
    )

    assert review.failures == [
        "`Zulu` has invalid indentation on line 9: use tabs for indentation, "
        "not spaces"
    ]


def test_entry_review_reports_changed_package_sorting_against_neighbors():
    source = (
        '{\n'
        '\t"schema_version": "3.0.0",\n'
        '\t"packages": [\n'
        '\t\t{\n'
        '\t\t\t"name": "Charlie",\n'
        '\t\t\t"details": "https://github.com/example/Charlie"\n'
        '\t\t},\n'
        '\t\t{\n'
        '\t\t\t"name": "Bravo",\n'
        '\t\t\t"details": "https://github.com/example/Bravo"\n'
        '\t\t}\n'
        '\t]\n'
        '}\n'
    )

    review = review_package_entry(
        "Bravo",
        {"details": "https://github.com/example/Bravo"},
        source,
    )

    assert review.failures == [
        "`Bravo` is not sorted: move it before `Charlie`."
    ]


def test_entry_review_uses_source_entry_for_redundant_field_checks():
    source = (
        '{\n'
        '\t"schema_version": "3.0.0",\n'
        '\t"packages": [\n'
        '\t\t{\n'
        '\t\t\t"details": "https://github.com/example/NoName",\n'
        '\t\t\t"releases": [{"sublime_text": "*", "tags": true}]\n'
        '\t\t}\n'
        '\t]\n'
        '}\n'
    )

    review = review_package_entry(
        "NoName",
        {
            "name": "NoName",
            "details": "https://github.com/example/NoName",
            "releases": [{"sublime_text": "*", "tags": True}],
        },
        source,
    )

    assert review.empty


def test_load_package_entry_source_follows_includes(tmp_path):
    root = tmp_path / "repository.json"
    included = tmp_path / "repository" / "s.json"
    included.parent.mkdir()
    root.write_text(
        '{\n'
        '\t"schema_version": "3.0.0",\n'
        '\t"packages": [],\n'
        '\t"includes": ["./repository/s.json"]\n'
        '}\n',
        encoding="utf-8",
    )
    included.write_text(
        '{\n'
        '\t"schema_version": "3.0.0",\n'
        '\t"packages": [\n'
        '\t\t{\n'
        '\t\t\t"details": "https://github.com/example/StyleTokenHighlighter"\n'
        '\t\t}\n'
        '\t]\n'
        '}\n',
        encoding="utf-8",
    )

    source = load_package_entry_source(
        "StyleTokenHighlighter",
        {
            "name": "StyleTokenHighlighter",
            "details": "https://github.com/example/StyleTokenHighlighter",
            "source": str(root),
        },
        {},
        DummyConsole(),
    )

    assert source == included.read_text(encoding="utf-8")


def test_extract_package_entries_uses_details_when_name_is_missing():
    source = (
        '{\n'
        '\t"schema_version": "3.0.0",\n'
        '\t"packages": [\n'
        '\t\t{\n'
        '\t\t\t"details": "https://github.com/example/NoName"\n'
        '\t\t}\n'
        '\t]\n'
        '}\n'
    )

    entries = extract_package_entries(source)

    assert [entry.name for entry in entries] == ["NoName"]


def test_combined_review_omits_empty_entry_section():
    review = review_package_entry(
        "Example",
        {"details": "https://github.com/example/Other"},
    )

    assert combine_entry_and_package_review(review, "No failures.\n") == "No failures.\n"


def test_combined_review_formats_entry_findings():
    review = review_package_entry(
        "Example",
        {
            "details": "https://github.com/example/Example",
            "releases": [{"branch": "main", "sublime_text": "*"}],
        },
    )

    assert combine_entry_and_package_review(review, "No failures.\n") == (
        "No failures.\n\n"
        "About the entry here:\n\n"
        "- Tip: `Example` only defines branch-based releases. Consider adding at "
        "least one `tags: true` release so Package Control can install stable "
        "tagged versions.\n"
    )


def test_combined_review_keeps_package_notes_first():
    package_definition = {
        "name": "Example",
        "details": "https://github.com/example/Example",
        "releases": [{"sublime_text": "*", "tags": True}],
    }
    review = review_package_entry(
        "Example",
        package_definition,
        source_for(package_definition),
    )

    assert combine_entry_and_package_review(
        review,
        "- Repository is at https://github.com/example/Example\n\n"
        "1 failure:\n"
        "- Broken package file\n\n"
        "No warnings\n\n",
    ) == (
        "- Repository is at https://github.com/example/Example\n\n"
        "1 failure:\n"
        "- Broken package file\n\n"
        "No warnings\n\n"
        "About the entry here:\n\n"
        "- `name` is set to `Example`, which can be derived from `details`. "
        "Omit it unless the display name differs from the repository name.\n"
    )


def test_combined_review_groups_entry_findings_when_severities_mix():
    review = EntryReview()
    review.failures.append("Entry failure")
    review.warnings.append("Entry warning")
    review.notices.append("Entry notice")

    assert combine_entry_and_package_review(review, "No failures.\n") == (
        "No failures.\n\n"
        "About the entry here:\n\n"
        "1 failure:\n"
        "- Entry failure\n\n"
        "1 warning:\n"
        "- Entry warning\n\n"
        "1 notice:\n"
        "- Entry notice\n"
    )


def source_for(package_definition):
    return json.dumps(
        {
            "schema_version": "3.0.0",
            "packages": [package_definition],
        },
        indent="\t",
    )

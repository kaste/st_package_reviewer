from gh_action.action import combine_entry_and_package_review
from gh_action._entry_checker import extract_package_entries, review_package_entry


def test_entry_review_warns_about_redundant_details_fields():
    review = review_package_entry(
        "KeyBindingReport",
        {
            "name": "KeyBindingReport",
            "details": "https://github.com/vwheeler63/KeyBindingReport",
            "author": "vwheeler63",
            "issues": "https://github.com/vwheeler63/KeyBindingReport/issues",
            "releases": [{"sublime_text": "*", "tags": True}],
        },
    )

    assert review.failures == []
    assert review.notices == []
    assert review.warnings == [
        "`KeyBindingReport` sets `author` to `vwheeler63`, which is already "
        "derived from `details`. Omit it unless it differs from the repository "
        "owner.",
        "`KeyBindingReport` sets `name` to `KeyBindingReport`, which is already "
        "derived from `details`. Omit it unless the display name differs from "
        "the repository name.",
        "`KeyBindingReport` sets `issues` to the standard issue tracker URL "
        "`https://github.com/vwheeler63/KeyBindingReport/issues`, which is "
        "already derived from `details`.",
    ]


def test_entry_review_allows_different_display_name_and_author():
    review = review_package_entry(
        "Key Binding Report",
        {
            "name": "Key Binding Report",
            "details": "https://github.com/vwheeler63/KeyBindingReport",
            "author": "Victoria Wheeler",
            "issues": "https://example.com/issues",
            "releases": [{"sublime_text": "*", "tags": True}],
        },
    )

    assert review.empty


def test_entry_review_warns_about_redundant_single_author_array():
    review = review_package_entry(
        "KeyBindingReport",
        {
            "details": "https://github.com/vwheeler63/KeyBindingReport",
            "author": ["vwheeler63"],
            "releases": [{"sublime_text": "*", "tags": True}],
        },
    )

    assert review.warnings == [
        "`KeyBindingReport` sets `author` to [`vwheeler63`], which is already "
        "derived from `details`. Omit it unless it differs from the repository "
        "owner; if you keep it, prefer a simple string unless there are "
        "multiple authors."
    ]


def test_entry_review_warns_about_single_author_array():
    review = review_package_entry(
        "KeyBindingReport",
        {
            "details": "https://github.com/vwheeler63/KeyBindingReport",
            "author": ["Victoria Wheeler"],
            "releases": [{"sublime_text": "*", "tags": True}],
        },
    )

    assert review.warnings == [
        "`KeyBindingReport` sets `author` to a single-item array. Prefer a "
        "simple string unless there are multiple authors."
    ]


def test_entry_review_warns_about_standard_gitlab_issues_url():
    review = review_package_entry(
        "Example",
        {
            "details": "https://gitlab.com/example/Example",
            "issues": "https://gitlab.com/example/Example/-/issues/",
            "releases": [{"sublime_text": "*", "tags": True}],
        },
    )

    assert review.warnings == [
        "`Example` sets `issues` to the standard issue tracker URL "
        "`https://gitlab.com/example/Example/-/issues/`, which is already "
        "derived from `details`."
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
        "Entry checks:\n\n"
        "1 notice:\n"
        "- Tip: `Example` only defines branch-based releases. Consider adding at "
        "least one `tags: true` release so Package Control can install stable "
        "tagged versions.\n\n"
        "No failures.\n"
    )

from gh_action.action import (
    append_package_review,
    append_package_review_failure,
    init_review_md,
    no_release_failure_details,
)


def test_init_review_md_starts_with_no_title(tmp_path):
    review = tmp_path / "review.md"

    init_review_md(review)

    assert review.read_text(encoding="utf-8") == ""


def test_append_package_review_failure(tmp_path):
    review = tmp_path / "review.md"
    review.write_text("This PR adds Example.\n\n", encoding="utf-8")

    append_package_review_failure(
        review,
        "Example",
        "Review could not be completed.",
        ["No releases found for Example.", "Check that the release branch exists."],
    )

    assert review.read_text(encoding="utf-8") == (
        "This PR adds Example.\n\n"
        "## Review for Example\n\n"
        "Review could not be completed.\n\n"
        "- No releases found for Example.\n"
        "- Check that the release branch exists.\n\n"
    )


def test_no_release_failure_details_reports_wrong_branch():
    details = no_release_failure_details(
        "Harpoon",
        {
            "details": "https://github.com/huyhoang8398/Harpoon",
            "releases": [{"sublime_text": "*", "branch": "master"}],
        },
        tags_mode=False,
        branch_exists=lambda _repo, _branch: False,
    )

    assert details == [
        "No releases found for Harpoon.",
        "The release definition references branch `master` at "
        "https://github.com/huyhoang8398/Harpoon, but such a branch does not exist.",
        "Check that the release branch exists and matches the registry entry. "
        "Better yet, switch to tags mode by setting `tags: true`.",
    ]


def test_append_package_review_formats_markdown(tmp_path):
    review = tmp_path / "review.md"
    review.write_text("This PR adds Example.\n\n", encoding="utf-8")

    append_package_review(
        review,
        "Example",
        "main-abc123-2026.05.04.02.53.13",
        "- Repository is at https://github.com/example/package\n"
        "- Tip of main is tagged with 1.0.1. ✅\n"
        "- 'Main.sublime-menu' has a 'Key Bindings' entry with 'args.base_file' "
        "set to ${packages}/Example/Default ($platform).sublime-keymap, "
        "but this package will be installed under ${packages}/Example/. Use "
        "the exact package name after ${packages}/.\n\n"
        "No failures, no warnings. 👍\n\n",
    )

    assert review.read_text(encoding="utf-8") == (
        "This PR adds Example.\n\n"
        "## Review for Example main-abc123-2026.05.04.02.53.13\n\n"
        "- Repository is at https://github.com/example/package\n"
        "- Tip of main is tagged with 1.0.1. ✅\n"
        "- 'Main.sublime-menu' has a 'Key Bindings' entry with 'args.base_file' "
        "set to ${packages}/Example/Default (<span>$</span>platform).sublime-keymap, "
        "but this package will be installed under ${packages}/Example/. Use "
        "the exact package name after ${packages}/.\n\n"
        "No failures, no warnings. 👍\n\n"
    )

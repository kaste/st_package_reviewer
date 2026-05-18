from gh_action.action import append_package_review, init_review_md


def test_init_review_md_starts_with_no_title(tmp_path):
    review = tmp_path / "review.md"

    init_review_md(review)

    assert review.read_text(encoding="utf-8") == ""


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

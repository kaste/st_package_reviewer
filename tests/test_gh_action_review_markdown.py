from gh_action.action import append_package_review, init_review_md


def test_init_review_md_starts_with_no_title(tmp_path):
    review = tmp_path / "review.md"

    init_review_md(review)

    assert review.read_text(encoding="utf-8") == ""


def test_append_package_review_places_repo_after_code_block(tmp_path):
    review = tmp_path / "review.md"
    review.write_text("This PR adds Example.\n\n", encoding="utf-8")

    append_package_review(
        review,
        "Example",
        "main-abc123-2026.05.04.02.53.13",
        "- Tip of main is tagged with 1.0.1. ✅\n\nNo failures, no warnings\n",
        "https://github.com/example/package",
    )

    assert review.read_text(encoding="utf-8") == (
        "This PR adds Example.\n\n"
        "## Review for Example main-abc123-2026.05.04.02.53.13\n\n"
        "```\n"
        "- Tip of main is tagged with 1.0.1. ✅\n\n"
        "No failures, no warnings\n"
        "```\n"
        "Repository: https://github.com/example/package\n\n"
    )

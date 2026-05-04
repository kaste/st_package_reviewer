from gh_action.action import format_channel_changes


def test_channel_summary_omits_empty_categories():
    assert format_channel_changes([], [], ["LSP-addon-breadcrumb"]) == (
        "This PR adds LSP-addon-breadcrumb."
    )


def test_channel_summary_uses_sentence_for_small_mixed_changes():
    assert format_channel_changes(["foobar"], [], ["zoofish"]) == (
        "This PR removes foobar and adds zoofish."
    )


def test_channel_summary_uses_oxford_list_in_sentence_mode():
    assert format_channel_changes([], [], ["fish", "ships", "friends"]) == (
        "This PR adds fish, ships, and friends."
    )


def test_channel_summary_uses_sections_for_medium_single_category():
    assert format_channel_changes(
        [],
        [],
        ["monkeys", "donkeys", "giraffes", "elephants"],
    ) == "Adds: monkeys, donkeys, giraffes, and elephants."


def test_channel_summary_uses_sections_for_medium_mixed_changes():
    assert format_channel_changes(
        ["foobar"],
        [],
        ["monkeys", "donkeys", "giraffes", "elephants"],
    ) == (
        "Removes foobar.\n\n"
        "Adds: monkeys, donkeys, giraffes, and elephants."
    )


def test_channel_summary_uses_bulk_mode_for_large_changes():
    assert format_channel_changes(
        ["foo", "zoo"],
        [
            "monkeys",
            "donkeys",
            "giraffes",
            "elephants",
            "fish",
            "ships",
            "friends",
            "zoofish",
            "birds",
        ],
        [],
    ) == (
        "Channel changes: 11 packages affected.\n\n"
        "- Removed: 2\n"
        "- Changed: 9\n\n"
        "<details>\n"
        "<summary>Package list</summary>\n\n"
        "Removed:\n"
        "- foo\n"
        "- zoo\n\n"
        "Changed:\n"
        "- monkeys\n"
        "- donkeys\n"
        "- giraffes\n"
        "- elephants\n"
        "- fish\n"
        "- ships\n"
        "- friends\n"
        "- zoofish\n"
        "- birds\n\n"
        "</details>"
    )

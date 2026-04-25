from gh_action.action import Console, emit_review_annotations


class CapturingConsole(Console):
    def __init__(self):
        self.stdout = []
        self.stderr = []

    def write(self, message):
        self.stderr.append(message)

    def write_stdout(self, message):
        self.stdout.append(message)


def test_emit_review_annotations_handles_singular_sections(tmp_path):
    review = tmp_path / "review.txt"
    review.write_text(
        "1 failure:\n"
        "- Broken\n"
        "    File: plugin.py\n"
        "\n"
        "1 warning:\n"
        "- Risky\n"
        "    File: Main.sublime-menu\n",
        encoding="utf-8",
    )
    console = CapturingConsole()

    emit_review_annotations(review, console)

    assert "::error title=CHECK ::Broken" in console.stdout
    assert "::warning title=CHECK ::Risky" in console.stdout


def test_emit_review_annotations_does_not_need_notice_header(tmp_path):
    review = tmp_path / "review.txt"
    review.write_text(
        "- A plain notice\n"
        "    File: Main.sublime-menu\n"
        "\n"
        "No failures, no warnings\n",
        encoding="utf-8",
    )
    console = CapturingConsole()

    emit_review_annotations(review, console)

    assert "::notice title=CHECK ::A plain notice" not in console.stdout
    assert "- A plain notice" in console.stdout

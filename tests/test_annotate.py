from io import StringIO

from gh_action_package.annotate import annotate_output


def render_annotations(text):
    out = StringIO()
    annotate_output(StringIO(text), out)
    return out.getvalue()


def test_annotate_output_emits_file_line_column_annotations():
    text = (
        "Reporting 1 failure:\n"
        "- Calling unsafe method\n"
        "    File: plugin.py\n"
        "    Line: 5, Column: 1\n"
        "\n"
    )

    output = render_annotations(text)

    assert text in output
    assert (
        "::error title=CHECK,file=plugin.py,line=5,col=1::"
        "Calling unsafe method\n"
    ) in output


def test_annotate_output_emits_file_only_warning_annotations():
    output = render_annotations(
        "Reporting 1 warning:\n"
        "- Missing menu entry\n"
        "    File: Main.sublime-menu\n"
        "\n"
    )

    assert "::warning title=CHECK,file=Main.sublime-menu::Missing menu entry\n" in output


def test_annotate_output_escapes_workflow_command_values():
    output = render_annotations(
        "Reporting 1 failure:\n"
        "- Bad value: 100%, comma\n"
        "    File: dir/weird:file,name.py\n"
        "\n"
    )

    assert (
        "::error title=CHECK,file=dir/weird%3Afile%2Cname.py::"
        "Bad value: 100%25, comma\n"
    ) in output


def test_annotate_output_ignores_notice_style_entries():
    text = (
        "- A plain notice\n"
        "    File: Main.sublime-menu\n"
        "\n"
        "No failures, no warnings. 👍\n"
    )

    output = render_annotations(text)

    assert output == text
    assert "::notice" not in output


def test_annotate_output_accepts_compact_headers():
    output = render_annotations(
        "1 warning:\n"
        "- Compact warning\n"
        "    File: plugin.py\n"
        "    Line: 7\n"
        "\n"
    )

    assert "::warning title=CHECK,file=plugin.py,line=7::Compact warning\n" in output


def test_annotate_output_accepts_plural_headers():
    output = render_annotations(
        "Reporting 2 failures:\n"
        "- First failure\n"
        "    File: first.py\n"
        "- Second failure\n"
        "    File: second.py\n"
        "\n"
    )

    assert "::error title=CHECK,file=first.py::First failure\n" in output
    assert "::error title=CHECK,file=second.py::Second failure\n" in output

from io import StringIO

from st_package_reviewer.check.report import Report
from st_package_reviewer.runner import CheckRunner


def test_report_uses_singular_failure_and_warning_headers():
    runner = CheckRunner([])
    runner._checked = True
    runner.failures = [Report("A failure", (), None, None)]
    runner.warnings = [Report("A warning", (), None, None)]

    out = StringIO()
    runner.report(file=out, compact=True)

    assert "1 failure:" in out.getvalue()
    assert "1 failures:" not in out.getvalue()
    assert "1 warning:" in out.getvalue()
    assert "1 warnings:" not in out.getvalue()


def test_report_omits_notice_count_header():
    runner = CheckRunner([])
    runner._checked = True
    runner.notices = [
        Report("First notice", (), None, None),
        Report("Second notice", (), None, None),
    ]

    out = StringIO()
    runner.report(file=out, compact=True)

    assert out.getvalue().startswith("- First notice\n- Second notice\n")
    assert "2 notices:" not in out.getvalue()


def test_report_combines_empty_failure_and_warning_groups():
    runner = CheckRunner([])
    runner._checked = True

    out = StringIO()
    runner.report(file=out, compact=True)

    assert out.getvalue() == "No failures, no warnings\n\n"


def test_report_omits_empty_notice_group():
    runner = CheckRunner([])
    runner._checked = True

    out = StringIO()
    runner.report(file=out, compact=True)

    assert "No notices" not in out.getvalue()

import logging
import sys

l = logging.getLogger(__name__)


class CheckRunner:

    def __init__(self, checkers, fail_on_warnings=False):
        self.checkers = checkers
        self.fail_on_warnings = fail_on_warnings
        self.failures = []
        self.warnings = []
        self.notices = []
        self._checked = False

    def run(self, *args, **kwargs):
        l.debug("\nRunning checkers...")
        objs = []
        for checker in self.checkers:
            checker_obj = checker(*args, **kwargs)
            objs.append(checker_obj)

            checker_obj.perform_check()
            self.failures.extend(checker_obj.failures)
            self.warnings.extend(checker_obj.warnings)
            self.notices.extend(checker_obj.notices)
            l.debug("Checker '%s' result: %s",
                    checker_obj.__class__.__name__,
                    checker_obj.result())

        self._checked = True

    def result(self):
        """Return whether checks ran without issues (`True`) or there were failures (`False`)."""
        if not self._checked:
            raise RuntimeError("Check has not been performed yet")
        success = not bool(self.failures)
        if self.fail_on_warnings:
            success &= not bool(self.warnings)
        return success

    def report(self, file=None, compact=False):
        if not self._checked:
            raise RuntimeError("Check has not been performed yet")
        if file is None:
            file = sys.stdout

        prefix = "" if compact else "Reporting "

        if self.notices:
            for notice in self._ordered_notices(self.notices):
                notice.report(file=file)
            print(file=file)  # new line

        if self.failures or self.warnings:
            self._report_group("failure", self.failures, file, prefix)

            print(file=file)  # new line

            self._report_group("warning", self.warnings, file, prefix)
        else:
            print("No failures, no warnings", file=file)

        print(file=file)  # new line

    def _report_group(self, name, reports, file, prefix):
        if reports:
            print("{}{} {}:".format(prefix, len(reports), _pluralize(name, len(reports))),
                  file=file)
        else:
            print("No {}".format(_pluralize(name, 0)), file=file)

        for report in reports:
            report.report(file=file)

    def _ordered_notices(self, notices):
        return sorted(notices, key=self._notice_sort_key)

    def _notice_sort_key(self, notice):
        return (self._is_repository_report(notice),)

    def _is_repository_report(self, report):
        return any(str(ctx).startswith("Repository:") for ctx in report.context)


def _pluralize(name, count):
    if count == 1:
        return name
    return name + "s"

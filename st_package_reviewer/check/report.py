from collections import namedtuple
import html
import sys
import traceback


class Report(namedtuple("_Report", "message context exception exc_info")):
    __slots__ = ()

    _indent = " " * 4

    def report(self, file=None):
        if file is None:
            file = sys.stdout
        print("- {}".format(self.message), file=file)
        for elem in self._report_details():
            print("{}{}".format(self._indent, elem), file=file)
        if self.exc_info:
            self._report_traceback(file)

    def _report_traceback(self, file):
        traceback_text = "".join(traceback.format_exception(*self.exc_info)).rstrip()
        print(file=file)
        print("<details>", file=file)
        print("<summary>Traceback</summary>", file=file)
        print(file=file)
        print("<pre>{}</pre>".format(html.escape(traceback_text)), file=file)
        print("</details>", file=file)
        print(file=file)

    @property
    def details(self):
        details = []
        for cont in self.context:
            details.append("{}".format(cont))
        if self.exception:
            details.append("Exception: {}".format(self.exception))
        return tuple(details)

    def _report_details(self):
        return tuple(
            detail for detail in self.details
            if not _is_redundant_file_detail(self.message, detail)
        )


def _is_redundant_file_detail(message, detail):
    prefix = "File: "
    if not detail.startswith(prefix):
        return False

    file_path = detail[len(prefix):]
    if "/" in file_path or "\\" in file_path:
        return False

    return message.startswith("'{}'".format(file_path))

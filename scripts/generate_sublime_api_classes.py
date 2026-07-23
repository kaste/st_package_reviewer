"""Generate metadata for classes documented in Sublime Text's API reference."""

from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.request import urlopen

API_REFERENCE_URL = "https://www.sublimetext.com/docs/api_reference.html"
OUTPUT_PATH = (
    Path(__file__).parents[1]
    / "st_package_reviewer"
    / "check"
    / "file"
    / "ast"
    / "sublime_api_classes.py"
)
BUILD_CLASS_RE = re.compile(r"build-(\d+)")
API_CLASS_ID_RE = re.compile(r"sublime\.([A-Za-z_]\w*)\Z")


def main():
    with urlopen(API_REFERENCE_URL) as response:
        document = response.read().decode("utf-8")

    classes = parse_api_classes(document)
    OUTPUT_PATH.write_text(format_api_classes(classes), encoding="utf-8")


def parse_api_classes(document):
    parser = ApiReferenceParser()
    parser.feed(document)
    return parser.classes


def format_api_classes(classes):
    entries = []
    for name, build in sorted(classes.items()):
        build_literal = "None" if build is None else str(build)
        entries.append('    {!r}: {},'.format(name, build_literal))

    return "\n".join([
        '"""Generated Sublime API class metadata; do not edit manually.',
        "",
        "Run scripts/generate_sublime_api_classes.py to update this file.",
        '"""',
        "",
        "# Source: {}".format(API_REFERENCE_URL),
        "# Values are the introducing Sublime Text build. None denotes classes",
        "# which predate the build annotations in the API reference.",
        "SUBLIME_API_CLASS_BUILDS = {",
        *entries,
        "}",
        "",
    ])


class ApiReferenceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.classes = {}
        self._div_builds = []
        self._class_builds = []
        self._dl_is_class = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        css_classes = attrs.get("class", "").split()

        if tag == "div":
            self._div_builds.append(self._find_build(css_classes))
        elif tag == "dl":
            is_class = "py" in css_classes and "class" in css_classes
            self._dl_is_class.append(is_class)
            if is_class:
                self._class_builds.append(self._current_build())
        elif tag == "dt" and self._class_builds:
            self._record_class(attrs.get("id"))

    def handle_endtag(self, tag):
        if tag == "div":
            self._div_builds.pop()
        elif tag == "dl":
            if self._dl_is_class.pop():
                self._class_builds.pop()

    def _record_class(self, element_id):
        match = API_CLASS_ID_RE.fullmatch(element_id or "")
        if match:
            self.classes[match.group(1)] = self._class_builds[-1]

    def _current_build(self):
        for build in reversed(self._div_builds):
            if build is not None:
                return build
        return None

    @staticmethod
    def _find_build(css_classes):
        for css_class in css_classes:
            match = BUILD_CLASS_RE.fullmatch(css_class)
            if match:
                return int(match.group(1))
        return None


if __name__ == "__main__":
    main()

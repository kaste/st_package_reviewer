import plistlib
import re
import xml.etree.ElementTree as ET
from xml.parsers.expat import ExpatError

from . import FileChecker
from ...lib import jsonc


class CheckJsoncFiles(FileChecker):

    def check(self):
        # All these files allow comments and trailing commas,
        # which is why we'll call them "jsonc" (JSON with Comments)
        jsonc_file_globs = {
            "**/*.sublime-build",
            "**/*.sublime-color-scheme",
            "**/*.hidden-color-scheme",
            "**/*.sublime-commands",
            "**/*.sublime-completions",
            "**/*.sublime-keymap",
            "**/*.sublime-macro",
            "**/*.sublime-menu",
            "**/*.sublime-mousemap",
            "**/*.sublime-settings",
            "**/*.sublime-theme",
        }

        for file_path in self.globs(*jsonc_file_globs):
            with self.file_context(file_path):
                with file_path.open(encoding='utf-8') as f:
                    source = f.read()
                    try:
                        data = jsonc.loads(source)
                    except ValueError as e:
                        self.fail("Invalid JSON (with comments)", exception=e)
                        continue

                self._verify_jsonc_collection_shape(file_path, data, source)

    def _verify_jsonc_collection_shape(self, file_path, data, source):
        if file_path.suffix not in {".sublime-menu", ".sublime-keymap", ".sublime-commands"}:
            return

        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            self.fail("'.sublime-menu', '.sublime-keymap', and '.sublime-commands' "
                      "must be a list of dicts")
            return

        if data:
            return

        if _contains_commented_example(file_path.suffix, source):
            self.notice(_example_file_notice(file_path.suffix))
            return

        self.fail("Remove this file, it doesn't define anything")


def _contains_commented_example(suffix, source):
    comment_fragments = re.findall(r"//.*?$|/\*.*?\*/", source, flags=re.MULTILINE | re.DOTALL)
    if not comment_fragments:
        return False

    text = "\n".join(comment_fragments).lower()
    if "{" in text and "}" in text:
        return True

    hints_by_suffix = {
        ".sublime-keymap": {"keys", "command"},
        ".sublime-commands": {"caption", "command"},
        ".sublime-menu": {"caption", "command"},
    }
    hints = hints_by_suffix.get(suffix, set())
    return any(hint in text for hint in hints)


def _example_file_notice(suffix):
    if suffix == ".sublime-keymap":
        return (
            "This file only contains commented examples. Consider defining "
            "'Example.sublime-keymap' and linking it from "
            "'Main.sublime-menu'."
        )

    return "This file only contains commented examples."


class CheckPlistFiles(FileChecker):

    def check(self):
        plist_file_globs = {
            "**/*.tmLanguage",
            "**/*.tmPreferences",
            "**/*.tmSnippet",
            "**/*.tmTheme",
            "**/*.hidden-tmTheme",
        }

        for file_path in self.globs(*plist_file_globs):
            with self.file_context(file_path):
                with file_path.open('rb') as f:
                    try:
                        plistlib.load(f)
                    except (ValueError, ExpatError) as e:
                        self.fail("Invalid Plist", exception=e)


class CheckXmlFiles(FileChecker):

    def check(self):
        for file_path in self.glob("**/*.sublime-snippet"):
            with self.file_context(file_path):
                try:
                    ET.parse(str(file_path))
                except ET.ParseError as e:
                    self.fail("Invalid XML", exception=e)

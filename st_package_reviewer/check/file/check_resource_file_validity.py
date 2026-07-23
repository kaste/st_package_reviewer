import json
import plistlib
import re
import xml.etree.ElementTree as ET
from xml.parsers.expat import ExpatError

from . import FileChecker
from ...lib import jsonc


class CheckJsoncFiles(FileChecker):

    def check(self):
        commented_standard_keymaps = []

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

                if self._verify_jsonc_collection_shape(file_path, data, source):
                    commented_standard_keymaps.append(file_path)

        if commented_standard_keymaps:
            self.notice(_standard_keymap_examples_notice(
                self,
                sorted(commented_standard_keymaps),
            ))

    def _verify_jsonc_collection_shape(self, file_path, data, source):
        if file_path.suffix not in {".sublime-menu", ".sublime-keymap", ".sublime-commands"}:
            return False

        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            self.fail("'.sublime-menu', '.sublime-keymap', and '.sublime-commands' "
                      "must be a list of dicts")
            return False

        if data:
            return False

        if _contains_commented_example(file_path.suffix, source):
            if file_path.suffix == ".sublime-keymap" and _is_standard_keymap_name(file_path.name):
                return True

            if file_path.suffix == ".sublime-commands":
                if _example_file_is_referenced(self, file_path):
                    return False
                self.notice(_undocumented_commands_example_notice(self, file_path), context=())
                return False

            context = None
            if file_path.suffix == ".sublime-keymap" and file_path.parent == self.base_path:
                context = ()
            self.notice(_example_file_notice(file_path), context=context)
            return False

        self.fail("Remove this file, it doesn't define anything")
        return False


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


def _standard_keymap_examples_notice(file_checker, file_paths):
    names = [_quoted_rel_path(file_checker, path) for path in file_paths]
    if len(names) == 1:
        intro = "{} only contains commented examples.".format(names[0])
    else:
        intro = "These keymaps only contain commented examples: {}.".format(
            _format_name_list(names)
        )

    message = (
        "{} Consider moving the examples to 'Example.sublime-keymap'. "
        "Sublime Text will not load key bindings from that file, so the "
        "examples can be left uncommented for easier copy/paste."
        .format(intro)
    )
    if _has_key_bindings_menu_entry(file_checker):
        message += (
            " Adjust the 'Key Bindings' entry in 'Main.sublime-menu' to:\n{}"
            .format(_example_key_bindings_menu_entry(file_checker.package_name))
        )
    return message


def _quoted_rel_path(file_checker, path):
    return repr(file_checker.rel_path(path).as_posix())


def _format_name_list(names):
    if len(names) == 2:
        return " and ".join(names)
    return "{}, and {}".format(", ".join(names[:-1]), names[-1])


def _has_key_bindings_menu_entry(file_checker):
    if not file_checker.package_name:
        return False

    from .check_resource_files import (
        _find_main_menu_path,
        _find_menu_entries,
        _find_package_settings_node,
        _load_menu_file,
    )

    menu_path = _find_main_menu_path(file_checker)
    if menu_path is None:
        return False

    menu_data = _load_menu_file(menu_path)
    package_node = _find_package_settings_node(menu_data, file_checker.package_name)
    if package_node is None:
        return False

    return bool(_find_menu_entries(package_node, caption="Key Bindings", loose=True))


def _example_key_bindings_menu_entry(package_name):
    entry = {
        "caption": "Example Key Bindings",
        "command": "edit_settings",
        "args": {
            "base_file": "${{packages}}/{}/Example.sublime-keymap".format(package_name),
            "user_file": "${packages}/User/Default (${platform}).sublime-keymap",
        },
    }
    code = json.dumps(entry, indent=2, ensure_ascii=False)
    lines = ["  ```json"]
    lines.extend("  {}".format(line) for line in code.splitlines())
    lines.append("  ```")
    return "\n".join(lines)


def _example_file_is_referenced(file_checker, example_path):
    reference_paths = set(file_checker.glob("**/Main.sublime-menu"))
    reference_paths.update(file_checker.glob("**/*.md"))
    reference_paths.update(file_checker.glob("**/*.markdown"))
    reference_paths.update(file_checker.glob("**/*.rst"))
    reference_paths.update(file_checker.glob("**/*.txt"))
    reference_paths.update(
        path for path in file_checker.glob("**/README*")
        if path.is_file()
    )

    names = {
        example_path.name.casefold(),
        file_checker.rel_path(example_path).as_posix().casefold(),
    }
    for path in reference_paths:
        if path == example_path or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").casefold()
        if any(name in text for name in names):
            return True
    return False


def _undocumented_commands_example_notice(file_checker, file_path):
    name = _quoted_rel_path(file_checker, file_path)
    return (
        "{} contains only commented examples but does not appear to be "
        "referenced from 'Main.sublime-menu' or package documentation. "
        "Consider adding a menu entry or documenting the examples so users "
        "can find them."
        .format(name)
    )


def _example_file_notice(file_path):
    if file_path.suffix == ".sublime-keymap":
        return (
            "'{0}' only contains commented examples. You can leave the "
            "bindings uncommented for easier copy/paste because Sublime "
            "Text will not load key bindings from files with "
            "non-standard filenames."
            .format(file_path.name)
        )

    return "This file only contains commented examples."


def _is_standard_keymap_name(name):
    if name == "Default.sublime-keymap":
        return True

    return re.match(
        r"^Default \((?:Linux|OSX|Windows)\)\.sublime-keymap$",
        name,
    ) is not None


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

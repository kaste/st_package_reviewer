import logging

from . import FileChecker
from ...lib import jsonc


l = logging.getLogger(__name__)


class CheckPluginsInRoot(FileChecker):

    def check(self):
        if self.glob("*.py"):
            return

        python_files_in_package = self.glob("*/**/*.py")
        if python_files_in_package:
            l.debug("Non-plugin Python files: %s", python_files_in_package)
            if not self.glob("**/*.sublime-build"):
                self.fail("The package contains {} Python file(s), "
                          "but none of them are in the package root "
                          "and no build system is specified"
                          .format(len(python_files_in_package)))


class CheckHasResourceFiles(FileChecker):

    def check(self):
        # Files with a hidden extension are excluded,
        # as they serve no purpose without another file using them
        # (e.g. a plugin).
        resource_file_globs = {
            "*.py",
            "**/*.sublime-build",
            "**/*.sublime-color-scheme",
            # "**/*.hidden-color-scheme",
            "**/*.sublime-commands",
            "**/*.sublime-completions",
            "**/*.sublime-keymap",
            "**/*.sublime-macro",  # almost useless without other files
            "**/*.sublime-menu",
            "**/*.sublime-mousemap",
            "**/*.sublime-settings",
            "**/*.sublime-snippet",
            "**/*.sublime-syntax",
            "**/*.sublime-theme",
            "**/*.tmLanguage",
            "**/*.tmPreferences",
            "**/*.tmSnippet",
            "**/*.tmTheme",
            # "**/*.hidden-tmTheme",
            # hunspell dictionaries
            "**/*.aff",
            "**/*.dic",
        }

        has_resource_files = any(self.glob(ptrn) for ptrn in resource_file_globs)
        if not has_resource_files:
            self.fail("The package does not define any file that interfaces with Sublime Text")


class CheckSettingsFileName(FileChecker):

    def check(self):
        if not self.package_name:
            return

        settings_files = sorted(self.glob("**/*.sublime-settings"))
        if not settings_files:
            return

        expected_name = "{}.sublime-settings".format(self.package_name)
        if any(path.name == expected_name for path in settings_files):
            return

        found_names = ", ".join(path.name for path in settings_files)
        with self.context("Expected file: {}".format(expected_name)):
            self.warn("No standard settings file matches the package name {!r}. Found: {}"
                      .format(self.package_name, found_names))


class CheckSettingsMenuEntry(FileChecker):

    def check(self):
        settings_files = sorted(self.glob("**/*.sublime-settings"))
        if not settings_files:
            return

        menu_path = self.sub_path("Main.sublime-menu")
        if not menu_path.is_file():
            self.warn("Package defines '.sublime-settings' files but is missing "
                      "'Main.sublime-menu'")
            return

        with self.file_context(menu_path):
            menu_data = _load_menu_file(menu_path)
            if menu_data is None or not self.package_name:
                return

            package_node = _find_package_settings_node(menu_data, self.package_name)
            if package_node is None:
                self.warn("'Main.sublime-menu' has no 'Package Settings' entry for {!r}"
                          .format(self.package_name))
                return

            expected_base_file = "${{packages}}/{0}/{0}.sublime-settings".format(self.package_name)
            settings_entries = _find_edit_settings_entries(package_node, caption="Settings")
            if not settings_entries:
                self.warn("'Main.sublime-menu' has no 'Settings' menu entry for {!r}"
                          .format(self.package_name))
                return

            valid_entries, missing_command_count, custom_commands = _analyze_settings_commands(
                settings_entries)
            if missing_command_count:
                self.fail("'Main.sublime-menu' has a 'Settings' entry for {!r} without a "
                          "'command' key"
                          .format(self.package_name))

            for command in custom_commands:
                self.notice("The command referenced for editing settings is `{}`."
                            .format(command))

            if not valid_entries:
                return

            matching_entries = [
                entry for entry in valid_entries
                if entry.get('args', {}).get('base_file') == expected_base_file
            ]
            if not matching_entries:
                found_base_files = sorted({
                    entry.get('args', {}).get('base_file', '<missing>')
                    for entry in settings_entries
                })
                self.warn("'Main.sublime-menu' has no 'Settings' entry with "
                          "'args.base_file' set to {!r}. Found: {}"
                          .format(expected_base_file, ", ".join(found_base_files)))
                return

            if all(not entry.get('args', {}).get('default') for entry in matching_entries):
                self.notice("Tip: add 'args.default' to the 'Settings' menu entry. "
                            "A minimal default is \"{}\".")


class CheckKeymapMenuEntry(FileChecker):

    def check(self):
        keymap_files = sorted(self.glob("**/*.sublime-keymap"))
        if not keymap_files:
            return

        menu_path = self.sub_path("Main.sublime-menu")
        if not menu_path.is_file():
            self.warn("Package defines '.sublime-keymap' files but is missing "
                      "'Main.sublime-menu'")
            return

        with self.file_context(menu_path):
            menu_data = _load_menu_file(menu_path)
            if menu_data is None or not self.package_name:
                return

            package_node = _find_package_settings_node(menu_data, self.package_name)
            if package_node is None:
                self.warn("'Main.sublime-menu' has no 'Package Settings' entry for key "
                          "bindings of {!r}".format(self.package_name))
                return

            key_binding_entries = _find_edit_settings_entries(package_node,
                                                              caption="Key Bindings")
            if not key_binding_entries:
                self.warn("'Main.sublime-menu' has no 'Key Bindings' menu entry for {!r}"
                          .format(self.package_name))
                return

            valid_entries, missing_command_count, custom_commands = _analyze_settings_commands(
                key_binding_entries)
            if missing_command_count:
                self.fail("'Main.sublime-menu' has a 'Key Bindings' entry for {!r} without "
                          "a 'command' key"
                          .format(self.package_name))

            for command in custom_commands:
                self.notice("The command referenced for editing key bindings is `{}`."
                            .format(command))

            if not valid_entries:
                return

            expected_base_files = _expected_keymap_base_files(self.package_name, keymap_files,
                                                              self.rel_path)
            matching_entries = [
                entry for entry in valid_entries
                if entry.get('args', {}).get('base_file') in expected_base_files
            ]
            if matching_entries:
                return

            found_base_files = sorted({
                entry.get('args', {}).get('base_file', '<missing>')
                for entry in valid_entries
            })
            self.warn("'Main.sublime-menu' has no 'Key Bindings' entry with 'args.base_file' "
                      "set to one of {}. Found: {}"
                      .format(", ".join(repr(path) for path in expected_base_files),
                              ", ".join(found_base_files)))


def _find_package_settings_node(menu_data, package_name):
    package_settings_nodes = [
        node for node in _iter_menu_nodes(menu_data)
        if isinstance(node, dict)
        and (node.get('id') == 'package-settings' or node.get('caption') == 'Package Settings')
    ]

    for package_settings_node in package_settings_nodes:
        for node in _iter_menu_nodes(package_settings_node.get('children', ())):
            if isinstance(node, dict) and node.get('caption') == package_name:
                return node
    return None


def _find_edit_settings_entries(package_node, caption):
    entries = []
    for node in _iter_menu_nodes(package_node.get('children', ())):
        if not isinstance(node, dict):
            continue
        if node.get('caption') == caption:
            entries.append(node)
    return entries


def _analyze_settings_commands(entries):
    valid_entries = []
    custom_commands = set()
    missing_command_count = 0

    for entry in entries:
        command = entry.get('command')
        if not command:
            missing_command_count += 1
            continue

        valid_entries.append(entry)
        if command != 'edit_settings':
            custom_commands.add(command)

    return valid_entries, missing_command_count, sorted(custom_commands)


def _expected_keymap_base_files(package_name, keymap_files, rel_path_func):
    platform_variants = {
        "Default (Linux).sublime-keymap",
        "Default (OSX).sublime-keymap",
        "Default (Windows).sublime-keymap",
    }

    expected = set()
    for keymap_file in keymap_files:
        rel_path = rel_path_func(keymap_file)
        rel_path = rel_path.as_posix()

        for variant in platform_variants:
            if rel_path.endswith(variant):
                rel_path = rel_path[:-len(variant)] + "Default (${platform}).sublime-keymap"
                break

        expected.add("${{packages}}/{}/{}".format(package_name, rel_path))

    return sorted(expected)


def _iter_menu_nodes(value):
    if isinstance(value, dict):
        yield value
        children = value.get('children')
        if isinstance(children, list):
            for child in children:
                yield from _iter_menu_nodes(child)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_menu_nodes(item)


def _load_menu_file(path):
    with path.open(encoding='utf-8') as f:
        try:
            return jsonc.loads(f.read())
        except ValueError as e:
            l.debug("Unable to parse menu file %s: %s", path, e)
            return None

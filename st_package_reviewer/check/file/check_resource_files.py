import logging
from pathlib import PurePosixPath
import re

from . import FileChecker
from ...lib import jsonc


l = logging.getLogger(__name__)


PLATFORM_KEYMAP_NAME = "Default (${platform}).sublime-keymap"
PLATFORM_KEYMAP_FILENAMES = (
    "Default (Linux).sublime-keymap",
    "Default (OSX).sublime-keymap",
    "Default (Windows).sublime-keymap",
)
SPECIFIC_PLATFORM_KEYMAP_RE = re.compile(
    r"^Default \((?:Linux|OSX|Windows)\)\.sublime-keymap$"
)
USER_PLATFORM_KEYMAP = "${packages}/User/Default (${platform}).sublime-keymap"


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
        unexpected_settings = [
            path for path in settings_files
            if path.name != expected_name and not _is_syntax_settings_file(path)
        ]
        if not unexpected_settings:
            return

        for path in unexpected_settings:
            with self.file_context(path):
                self.warn("You define {!r} but {!r} is neither your package "
                          "name nor the name of a syntax you ship."
                          .format(path.name, path.stem))


class CheckSettingsMenuEntry(FileChecker):

    def check(self):
        if not self.package_name:
            return

        settings_files = _find_package_settings_files(
            sorted(self.glob("**/*.sublime-settings")),
            self.package_name,
        )
        if not settings_files:
            return

        menu_path = _find_main_menu_path(self)
        if menu_path is None:
            self.warn("Package defines '.sublime-settings' files but is missing "
                      "'Main.sublime-menu' to add menu entries to edit them.")
            return

        with self.file_context(menu_path):
            menu_data = _load_menu_file(menu_path)
            if menu_data is None:
                return

            expected_base_file = "${{packages}}/{0}/{0}.sublime-settings".format(self.package_name)
            package_node = _find_package_settings_node(menu_data, self.package_name)
            if package_node is None:
                self.warn(_missing_settings_package_entry_warning(
                    menu_data,
                    self.package_name,
                    settings_files,
                    expected_base_file,
                ))
                package_node = _find_package_settings_resource_node(
                    menu_data,
                    self.package_name,
                )
                if package_node is None:
                    return

            settings_entries = _find_menu_entries(package_node, caption="Settings")
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
                self.warn(_missing_base_file_warning(
                    "Settings",
                    [expected_base_file],
                    settings_entries,
                ))
                return

            if all(not entry.get('args', {}).get('default') for entry in matching_entries):
                self.notice("Tip: add 'args.default' to the 'Settings' menu entry. "
                            "A minimal default is \"{}\".")


class CheckCommandPaletteEditSettingsCaption(FileChecker):

    def check(self):
        if not self.package_name:
            return

        for commands_path in self.glob("**/*.sublime-commands"):
            with self.file_context(commands_path):
                commands = _load_menu_file(commands_path)
                if not isinstance(commands, list):
                    continue

                for entry in commands:
                    self._check_entry(entry)

    def _check_entry(self, entry):
        if not isinstance(entry, dict) or entry.get('command') != 'edit_settings':
            return

        caption = entry.get('caption')
        if not isinstance(caption, str):
            return

        entry_kind = _edit_settings_entry_kind(entry)
        if entry_kind is None:
            return

        required_text = "Key Bindings" if entry_kind == "key bindings" else "Settings"
        required_prefix = "Preferences: {}".format(self.package_name)
        if not caption.startswith(required_prefix):
            self.warn(
                "Command palette entry for editing {} should start with {!r}. "
                "Found: {}".format(entry_kind, required_prefix, caption)
            )

        if required_text not in caption:
            self.warn(
                "Command palette entry for editing {} should contain {!r}. "
                "Found: {}".format(entry_kind, required_text, caption)
            )


class CheckCommandPaletteSettingsEntry(FileChecker):

    def check(self):
        if not self.package_name:
            return

        settings_files = _find_package_settings_files(
            sorted(self.glob("**/*.sublime-settings")),
            self.package_name,
        )
        if not settings_files:
            return

        commands_path = self.sub_path("Default.sublime-commands")
        if not commands_path.is_file():
            self.warn("Package defines '.sublime-settings' files but is missing "
                      "'Default.sublime-commands' to add a Command Palette entry "
                      "to edit them.")
            return

        with self.file_context(commands_path):
            commands = _load_menu_file(commands_path)
            if not isinstance(commands, list):
                return

            expected_base_file = "${{packages}}/{0}/{0}.sublime-settings".format(
                self.package_name)
            settings_entries = _find_command_palette_edit_settings_entries(commands)
            if not settings_entries:
                self.warn("'Default.sublime-commands' has no settings entry using "
                          "edit_settings for {!r}. Add an entry with caption "
                          "'Preferences: {} Settings' and 'args.base_file' set "
                          "to {!r}."
                          .format(self.package_name, self.package_name, expected_base_file))
                return

            matching_entries = [
                entry for entry in settings_entries
                if entry.get('args', {}).get('base_file') == expected_base_file
            ]
            if not matching_entries:
                self.warn(_missing_command_palette_base_file_warning(
                    expected_base_file,
                    settings_entries,
                ))
                return

            if all(not entry.get('args', {}).get('default') for entry in matching_entries):
                self.notice("Tip: add 'args.default' to the 'Default.sublime-commands' "
                            "settings entry. A minimal default is \"{}\".")


class CheckSyntaxSettingsEntries(FileChecker):

    NOTICE = (
        "Package defines syntax settings. Consider adding an entry in "
        "'Main.sublime-menu' and 'Default.sublime-commands' to help users "
        "find or customize them."
    )

    def check(self):
        syntax_settings_files = _find_syntax_settings_files(
            sorted(self.glob("**/*.sublime-settings")),
        )
        if not syntax_settings_files:
            return

        if (
            self._has_main_menu_entry(syntax_settings_files)
            and self._has_command_palette_entry(syntax_settings_files)
        ):
            return

        self.notice(self.NOTICE)

    def _has_main_menu_entry(self, syntax_settings_files):
        menu_path = _find_main_menu_path(self)
        if menu_path is None:
            return False

        menu_data = _load_menu_file(menu_path)
        return _has_edit_settings_entry_for_files(self, menu_data, syntax_settings_files)

    def _has_command_palette_entry(self, syntax_settings_files):
        commands_path = self.sub_path("Default.sublime-commands")
        if not commands_path.is_file():
            return False

        commands = _load_menu_file(commands_path)
        return _has_edit_settings_entry_for_files(self, commands, syntax_settings_files)


class CheckKeymapMenuEntry(FileChecker):

    def check(self):
        keymap_files = sorted(self.glob("**/*.sublime-keymap"))
        if not keymap_files:
            return

        menu_path = _find_main_menu_path(self)
        if menu_path is None:
            self.notice("Package defines key bindings but has no 'Main.sublime-menu' "
                        "entry to help users find or customize them.")
            return

        with self.file_context(menu_path):
            menu_data = _load_menu_file(menu_path)
            if menu_data is None or not self.package_name:
                return

            package_node = _find_package_settings_node(menu_data, self.package_name)
            if package_node is None:
                self.warn(_missing_package_settings_entry_warning(
                    menu_data,
                    self.package_name,
                ))
                package_node = _find_package_settings_resource_node(
                    menu_data,
                    self.package_name,
                )
                if package_node is None:
                    return

            key_binding_entries = _find_menu_entries(package_node,
                                                     caption="Key Bindings",
                                                     loose=True)

            if not key_binding_entries:
                return

            valid_entries, missing_command_count, custom_commands = _analyze_settings_commands(
                key_binding_entries)
            edit_settings_entries = [
                entry for entry in valid_entries
                if entry.get('command') == 'edit_settings'
            ]
            if missing_command_count:
                self.fail("'Main.sublime-menu' has a 'Key Bindings' entry for {!r} without "
                          "a 'command' key"
                          .format(self.package_name))

            for command in custom_commands:
                self.notice("The command referenced for editing key bindings is `{}`."
                            .format(command))

            if not edit_settings_entries:
                return

            base_file_entries = [
                entry for entry in edit_settings_entries
                if entry.get('args', {}).get('base_file')
            ]
            if not base_file_entries:
                self.warn("'Main.sublime-menu' has a 'Key Bindings' entry "
                          "without required 'args.base_file'.")
                return

            for entry in base_file_entries:
                self._check_base_file_entry(entry)

    def _check_base_file_entry(self, entry):
        base_file = entry.get('args', {}).get('base_file')
        rel_path = _package_resource_path(base_file, self.package_name)
        if rel_path is None:
            self.fail("'Main.sublime-menu' has a 'Key Bindings' entry whose "
                      "'args.base_file' does not reference this package: {}"
                      .format(base_file))
            return

        if _is_platform_keymap(rel_path):
            self._check_platform_keymap_base_file(base_file, rel_path)
            return

        if not self.sub_path(rel_path).is_file():
            self.fail("'Main.sublime-menu' has a 'Key Bindings' entry whose "
                      "'args.base_file' does not exist: {}".format(base_file))
            return

        if _is_specific_platform_keymap(rel_path):
            self.warn("'Main.sublime-menu' has a 'Key Bindings' entry with "
                      "'args.base_file' set to a platform-specific keymap. "
                      "Use {!r} instead."
                      .format(_platform_keymap_resource(base_file)))

        if _requires_user_keymap(rel_path) and entry.get('command') == 'edit_settings':
            self._check_keymap_user_file(entry, rel_path)

    def _check_platform_keymap_base_file(self, base_file, rel_path):
        platform_keymap_paths = _platform_keymap_paths(rel_path)
        existing_paths = [path for path in platform_keymap_paths if self.sub_path(path).is_file()]
        missing_paths = [path for path in platform_keymap_paths if path not in existing_paths]

        if not existing_paths:
            self.fail("'Main.sublime-menu' has a 'Key Bindings' entry whose "
                      "'args.base_file' does not match any platform keymap files: {}"
                      .format(base_file))
            return

        if missing_paths:
            self.warn("'Main.sublime-menu' has a 'Key Bindings' entry with "
                      "'args.base_file' set to {}, but these platform keymap "
                      "files are missing: {}"
                      .format(base_file, _format_rel_paths(missing_paths)))

    def _check_keymap_user_file(self, entry, rel_path):
        user_file = entry.get('args', {}).get('user_file')
        if user_file == USER_PLATFORM_KEYMAP:
            return

        if _is_default_keymap(rel_path):
            message = ("'Main.sublime-menu' has a 'Key Bindings' entry for "
                       "Default.sublime-keymap without 'args.user_file' set to "
                       "{!r}.".format(USER_PLATFORM_KEYMAP))
        else:
            message = ("'Main.sublime-menu' has a 'Key Bindings' entry for "
                       "{!r} without 'args.user_file' set. For non-standard "
                       "keymap names this is required because edit_settings "
                       "will otherwise create that filename in User, but "
                       "Sublime Text will not load it. Set 'args.user_file' "
                       "to {!r}."
                       .format(rel_path.name, USER_PLATFORM_KEYMAP))
        if user_file:
            message += " Found: {}".format(user_file)
        self.fail(message)


def _edit_settings_entry_kind(entry):
    args = entry.get('args')
    if not isinstance(args, dict):
        return None

    resource = "{}\n{}".format(args.get('base_file', ''), args.get('user_file', ''))
    if ".sublime-keymap" in resource:
        return "key bindings"
    if ".sublime-settings" in resource:
        return "settings"
    return None


def _missing_base_file_warning(caption, expected_base_files, entries):
    found_base_files, missing_count = _find_base_file_values(entries)
    if not found_base_files:
        return ("'Main.sublime-menu' has no '{}' entry with 'args.base_file' set."
                .format(caption))

    expected = _format_expected_base_files(expected_base_files)
    message = ("'Main.sublime-menu' has no '{}' entry with 'args.base_file' {}. "
               "Found: {}".format(caption, expected, ", ".join(found_base_files)))
    if missing_count:
        message += " (and {} without 'args.base_file')".format(missing_count)
    return message


def _find_base_file_values(entries):
    found_base_files = set()
    missing_count = 0
    for entry in entries:
        base_file = entry.get('args', {}).get('base_file')
        if base_file:
            found_base_files.add(base_file)
        else:
            missing_count += 1
    return sorted(found_base_files), missing_count


def _find_package_settings_files(settings_files, package_name):
    expected_name = "{}.sublime-settings".format(package_name)
    return [path for path in settings_files if path.name == expected_name]


def _find_syntax_settings_files(settings_files):
    return [path for path in settings_files if _is_syntax_settings_file(path)]


def _is_syntax_settings_file(path):
    return any(
        path.with_suffix(suffix).is_file()
        for suffix in (".sublime-syntax", ".tmLanguage")
    )


def _has_edit_settings_entry_for_files(file_checker, data, settings_files):
    expected_base_files = _resource_paths_for_files(file_checker, settings_files)
    for node in _iter_menu_nodes(data):
        if not isinstance(node, dict) or node.get('command') != 'edit_settings':
            continue

        args = node.get('args')
        if isinstance(args, dict) and args.get('base_file') in expected_base_files:
            return True

    return False


def _resource_paths_for_files(file_checker, paths):
    if not file_checker.package_name:
        return set()

    prefix = "${{packages}}/{}/".format(file_checker.package_name)
    return {
        prefix + file_checker.rel_path(path).as_posix()
        for path in paths
    }


def _find_command_palette_edit_settings_entries(commands):
    return [
        entry for entry in commands
        if isinstance(entry, dict)
        and entry.get('command') == 'edit_settings'
        and _edit_settings_entry_kind(entry) == "settings"
    ]


def _missing_command_palette_base_file_warning(expected_base_file, entries):
    found_base_files, missing_count = _find_base_file_values(entries)
    if not found_base_files:
        return ("'Default.sublime-commands' has no settings entry with "
                "'args.base_file' set.")

    message = ("'Default.sublime-commands' has no settings entry with "
               "'args.base_file' set to {!r}. Found: {}"
               .format(expected_base_file, ", ".join(found_base_files)))
    if missing_count:
        message += " (and {} without 'args.base_file')".format(missing_count)
    return message


def _format_expected_base_files(expected_base_files):
    if len(expected_base_files) == 1:
        return "set to {!r}".format(expected_base_files[0])
    return "set to one of {}".format(", ".join(repr(path) for path in expected_base_files))


def _missing_settings_package_entry_warning(menu_data, package_name, settings_files,
                                            expected_base_file):
    caption = _find_package_settings_resource_caption(menu_data, package_name)
    if caption:
        return _mismatched_package_settings_entry_warning(caption, package_name)

    settings_file = _find_standard_settings_file_name(settings_files, package_name)
    if settings_file is None:
        settings_file = ".sublime-settings files"

    return (
        "'Main.sublime-menu' has no settings entry under "
        "'Preferences > Package Settings > {}' to edit {!r}. Add a "
        "'Settings' entry using edit_settings with 'args.base_file' set "
        "to {!r}."
        .format(package_name, settings_file, expected_base_file)
    )


def _missing_package_settings_entry_warning(menu_data, package_name):
    caption = _find_package_settings_resource_caption(menu_data, package_name)
    if caption:
        return _mismatched_package_settings_entry_warning(caption, package_name)

    return "'Main.sublime-menu' has no 'Package Settings' entry for {!r}".format(
        package_name)


def _mismatched_package_settings_entry_warning(caption, package_name):
    return (
        "'Main.sublime-menu' adds menu entries under "
        "'Package Settings > {}'. We expect this to match the actual "
        "package name, e.g. 'Package Settings > {}'."
        .format(caption, package_name)
    )


def _find_standard_settings_file_name(settings_files, package_name):
    expected_name = "{}.sublime-settings".format(package_name)
    for path in settings_files:
        if path.name == expected_name:
            return path.name
    return None


def _find_package_settings_node(menu_data, package_name):
    for package_settings_node in _iter_package_settings_nodes(menu_data):
        for node in _iter_menu_nodes(package_settings_node.get('children', ())):
            if isinstance(node, dict) and node.get('caption') == package_name:
                return node
    return None


def _find_package_settings_resource_caption(menu_data, package_name):
    node = _find_package_settings_resource_node(menu_data, package_name)
    if node is None:
        return None

    return node.get('caption')


def _find_package_settings_resource_node(menu_data, package_name):
    for package_settings_node in _iter_package_settings_nodes(menu_data):
        children = package_settings_node.get('children')
        if not isinstance(children, list):
            continue

        for node in children:
            if not isinstance(node, dict):
                continue

            caption = node.get('caption')
            if not isinstance(caption, str) or caption == package_name:
                continue

            if _node_references_package_resource(node, package_name):
                return node
    return None


def _iter_package_settings_nodes(menu_data):
    return (
        node for node in _iter_menu_nodes(menu_data)
        if isinstance(node, dict)
        and (node.get('id') == 'package-settings' or node.get('caption') == 'Package Settings')
    )


def _node_references_package_resource(value, package_name):
    for node in _iter_menu_nodes(value):
        if not isinstance(node, dict):
            continue

        args = node.get('args')
        if not isinstance(args, dict):
            continue

        for key in ('base_file', 'user_file'):
            if _package_resource_path(args.get(key), package_name) is not None:
                return True
    return False


def _find_menu_entries(package_node, caption, loose=False):
    entries = []
    target = caption.casefold()

    for node in _iter_menu_nodes(package_node.get('children', ())):
        if not isinstance(node, dict):
            continue

        node_caption = node.get('caption')
        if not isinstance(node_caption, str):
            continue

        if loose:
            if target in node_caption.casefold():
                entries.append(node)
        else:
            if node_caption == caption:
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


def _find_main_menu_path(file_checker):
    root_menu_path = file_checker.sub_path("Main.sublime-menu")
    menu_paths = sorted(
        file_checker.glob("**/Main.sublime-menu"),
        key=lambda path: (path != root_menu_path, str(path)),
    )
    if menu_paths:
        return menu_paths[0]

    return None


def _package_resource_path(resource, package_name):
    if not isinstance(resource, str):
        return None

    prefix = "${{packages}}/{}/".format(package_name)
    if not resource.startswith(prefix):
        return None

    rel_path = resource[len(prefix):]
    if not rel_path:
        return None

    return PurePosixPath(rel_path)


def _is_platform_keymap(rel_path):
    return rel_path.name == PLATFORM_KEYMAP_NAME


def _is_specific_platform_keymap(rel_path):
    return bool(SPECIFIC_PLATFORM_KEYMAP_RE.match(rel_path.name))


def _requires_user_keymap(rel_path):
    if _is_default_keymap(rel_path):
        return True

    return not _is_specific_platform_keymap(rel_path)


def _is_default_keymap(rel_path):
    return rel_path.name == "Default.sublime-keymap"


def _platform_keymap_paths(rel_path):
    return [rel_path.with_name(filename) for filename in PLATFORM_KEYMAP_FILENAMES]


def _platform_keymap_resource(resource):
    return PurePosixPath(resource).with_name(PLATFORM_KEYMAP_NAME).as_posix()


def _format_rel_paths(paths):
    return ", ".join(path.as_posix() for path in paths)


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

from st_package_reviewer.check.file.ast.check_command_names import CheckCommandNames


def check_names(tmp_path, source):
    (tmp_path / "plugin.py").write_text(source, encoding="utf-8")
    checker = CheckCommandNames(tmp_path)
    checker.check()
    return [report.message for report in checker.warnings], [
        report.message for report in checker.notices
    ]


def test_name_overrides_supply_actual_command_prefix(tmp_path):
    warnings, notices = check_names(tmp_path, '''\
import sublime_plugin

class CloseWalkedFilesCommand(sublime_plugin.TextCommand):
    def name(self):
        """Name used by key bindings."""
        return "walker_close_files"

class KeepOneWalkedFileCommand(sublime_plugin.WindowCommand):
    def name(self):
        return "walker_keep_one_file"

class OpenWalkerWindowCommand(sublime_plugin.ApplicationCommand):
    def name(self):
        return "walker_open_window"

class WalkMatchesCommand(sublime_plugin.TextCommand):
    def name(self):
        return "walker_walk_matches"
''')
    assert warnings == []
    assert notices == ["Common used command prefix is: walker."]


def test_unknown_name_override_does_not_use_class_name(tmp_path):
    warnings, notices = check_names(tmp_path, '''\
import sublime_plugin

class CloseFilesCommand(sublime_plugin.TextCommand):
    def name(self):
        return get_command_name()

class OpenWindowCommand(sublime_plugin.WindowCommand):
    def name(self):
        if use_other_name():
            return "other_open"
        return "walker_open"

class WalkerKeepCommand(sublime_plugin.ApplicationCommand):
    pass
''')
    assert warnings == []
    assert notices == []


def test_literal_override_can_expose_real_prefix_mismatch(tmp_path):
    warnings, notices = check_names(tmp_path, '''\
import sublime_plugin

class FooCommand(sublime_plugin.TextCommand):
    def name(self):
        return "bar_foo"

class BazCommand(sublime_plugin.WindowCommand):
    pass
''')
    assert warnings == [
        "Found multiple command prefixes: bar, baz. Consider using one single prefix"
        " so as to not clutter the command namespace."
    ]
    assert notices == []

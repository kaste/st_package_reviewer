from . import AstChecker
import re
import ast


# TODO: This only checks immediate base classes; need more traversing for deeper-derived base
# classes.
def _is_derived_from_command(node):
    interesting = ("TextCommand", "WindowCommand", "ApplicationCommand", "ExecCommand")
    for base in node.bases:
        if isinstance(base, ast.Attribute):
            # something of the form module_name.BaseClassName
            if isinstance(base.value, ast.Attribute):
                if base.value.value.id == "Default":
                    # Something derived from a class in Default... Must be ExecCommand
                    return True
            elif isinstance(base.value, ast.Name):
                if base.value.id == "sublime_plugin" and base.attr in interesting:
                    return True
        elif isinstance(base, ast.Name):
            # something of the form BaseClassName
            if base.id in interesting:
                return True
    return False


class CheckCommandNames(AstChecker):
    """Finds all sublime commands and checks package-level command prefix consistency."""

    def check(self):
        self.command_names = []
        super().check()
        self._check_prefix_consistency()

    def visit_ClassDef(self, node):
        if node.name.startswith("_"):
            return

        if not _is_derived_from_command(node):
            return

        with self.node_context(node):
            command_name = self._class_name_to_command_name(node.name)
            if command_name is None:
                self.warn("Unable to infer command name from class {!r}".format(node.name))
                return
            self.command_names.append(command_name)

    def _check_prefix_consistency(self):
        if len(self.command_names) < 2:
            return

        prefixes = {self._extract_prefix(name) for name in self.command_names}
        if len(prefixes) > 1:
            self.warn("Found multiple command prefixes: {}."
                      " Consider using one single prefix"
                      " so as to not clutter the command namespace."
                      .format(", ".join(sorted(prefixes))))

    @staticmethod
    def _class_name_to_command_name(class_name):
        stem = class_name[:-7] if class_name.endswith("Command") else class_name
        stem = stem.strip("_")
        if not stem:
            return None

        command_name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", stem)
        command_name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", command_name)
        command_name = re.sub(r"_+", "_", command_name).strip("_").lower()
        return command_name or None

    @staticmethod
    def _extract_prefix(command_name):
        return command_name.split("_", 1)[0]

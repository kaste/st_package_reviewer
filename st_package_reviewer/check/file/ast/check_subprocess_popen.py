import ast

from ....platforms import platforms_include
from . import AstChecker


class CheckSubprocessPopenStartupinfo(AstChecker):
    """Check subprocess.Popen calls that can flash console windows on Windows."""

    WARNING = (
        "subprocess.Popen is used in a Windows-supported package without "
        "hidden-window handling. Pass startupinfo with STARTF_USESHOWWINDOW/"
        "SW_HIDE, or use CREATE_NO_WINDOW, to avoid flashing console windows."
    )

    def check(self):
        if not platforms_include(self.platforms, "windows"):
            return
        super().check()

    def visit_all_pyfiles(self):
        for path in self.glob("**/*.py"):
            with self.file_context(path):
                root = self._get_ast(path)
                if root:
                    self._collect_subprocess_imports(root)
                    self.visit(root)

    def visit_Call(self, node):
        if self._is_popen_call(node) and not self._has_hidden_window_handling(node):
            with self.node_context(node):
                self.warn(self.WARNING)
        self.generic_visit(node)

    def _collect_subprocess_imports(self, root):
        self._subprocess_module_names = {"subprocess"}
        self._popen_names = set()
        self._create_no_window_names = set()

        for node in ast.walk(root):
            if isinstance(node, ast.Import):
                self._collect_subprocess_module_imports(node)
            elif isinstance(node, ast.ImportFrom):
                self._collect_subprocess_from_imports(node)

    def _collect_subprocess_module_imports(self, node):
        for alias in node.names:
            if alias.name == "subprocess":
                self._subprocess_module_names.add(alias.asname or alias.name)

    def _collect_subprocess_from_imports(self, node):
        if node.module != "subprocess":
            return

        for alias in node.names:
            if alias.name == "*":
                self._popen_names.add("Popen")
                self._create_no_window_names.add("CREATE_NO_WINDOW")
                continue

            name = alias.asname or alias.name
            if alias.name == "Popen":
                self._popen_names.add(name)
            elif alias.name == "CREATE_NO_WINDOW":
                self._create_no_window_names.add(name)

    def _is_popen_call(self, node):
        func = node.func
        if isinstance(func, ast.Attribute):
            return (
                func.attr == "Popen"
                and isinstance(func.value, ast.Name)
                and func.value.id in self._subprocess_module_names
            )
        return isinstance(func, ast.Name) and func.id in self._popen_names

    def _has_hidden_window_handling(self, node):
        for keyword in node.keywords:
            if keyword.arg == "startupinfo":
                return not _is_none(keyword.value)
            if keyword.arg == "creationflags":
                return self._contains_create_no_window(keyword.value)
        return False

    def _contains_create_no_window(self, node):
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute):
                if (
                    child.attr == "CREATE_NO_WINDOW"
                    and isinstance(child.value, ast.Name)
                    and child.value.id in self._subprocess_module_names
                ):
                    return True
            elif isinstance(child, ast.Name):
                if child.id in self._create_no_window_names:
                    return True
        return False


def _is_none(node):
    return isinstance(node, ast.Constant) and node.value is None

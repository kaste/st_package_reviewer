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
        for path in self.installed_python_files():
            with self.file_context(path):
                root = self._get_ast(path)
                if root:
                    self._collect_subprocess_imports(root)
                    self._has_file_hidden_window_evidence = (
                        self._contains_subprocess_symbol(
                            root,
                            "STARTF_USESHOWWINDOW",
                            self._startf_use_show_window_names,
                        )
                        or self._contains_subprocess_symbol(
                            root,
                            "CREATE_NO_WINDOW",
                            self._create_no_window_names,
                        )
                    )
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
        self._startf_use_show_window_names = set()

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
                self._startf_use_show_window_names.add("STARTF_USESHOWWINDOW")
                continue

            name = alias.asname or alias.name
            if alias.name == "Popen":
                self._popen_names.add(name)
            elif alias.name == "CREATE_NO_WINDOW":
                self._create_no_window_names.add(name)
            elif alias.name == "STARTF_USESHOWWINDOW":
                self._startf_use_show_window_names.add(name)

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
        has_kwargs_expansion = False
        for keyword in node.keywords:
            if keyword.arg is None:
                has_kwargs_expansion = True
            elif keyword.arg == "startupinfo" and not _is_none(keyword.value):
                return True
            elif keyword.arg == "creationflags" and self._contains_subprocess_symbol(
                keyword.value,
                "CREATE_NO_WINDOW",
                self._create_no_window_names,
            ):
                return True

        return has_kwargs_expansion and self._has_file_hidden_window_evidence

    def _contains_subprocess_symbol(self, node, symbol, imported_names):
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute):
                if (
                    child.attr == symbol
                    and isinstance(child.value, ast.Name)
                    and child.value.id in self._subprocess_module_names
                ):
                    return True
            elif isinstance(child, ast.Name) and child.id in imported_names:
                return True
        return False


def _is_none(node):
    return isinstance(node, ast.Constant) and node.value is None

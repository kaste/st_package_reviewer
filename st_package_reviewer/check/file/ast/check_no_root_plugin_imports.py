from . import AstChecker


class CheckNoRootPluginImports(AstChecker):
    """Check that package code does not import root-level plugin modules."""

    FAILURE = (
        "Do not import root-level plugin module '.{}'. Sublime Text loads "
        "root-level Python files as independent plugins; move shared code "
        "into a subpackage."
    )

    def check(self):
        self._root_plugin_modules = {
            path.stem
            for path in self.glob("*.py")
            if path.name != "__init__.py"
        }
        if not self._root_plugin_modules:
            return

        super().check()

    def visit_all_pyfiles(self):
        for path in self.glob("**/*.py"):
            self._current_module_parts = self._module_parts(path)
            with self.file_context(path):
                root = self._get_ast(path)
                if root:
                    self.visit(root)

    def visit_ImportFrom(self, node):
        self._fail_about_imports(
            node,
            self._imported_root_plugin_modules(node),
        )

    def _fail_about_imports(self, node, root_modules):
        for root_module in sorted(root_modules):
            with self.node_context(node):
                self.fail(self.FAILURE.format(root_module))

    def _imported_root_plugin_modules(self, node):
        base = self._resolved_from_import_base(node)
        if base is None:
            return set()

        if base:
            root_module = base[0]
            if root_module in self._root_plugin_modules:
                return {root_module}
            return set()

        return {
            alias.name
            for alias in node.names
            if alias.name in self._root_plugin_modules
        }

    def _resolved_from_import_base(self, node):
        if node.level == 0:
            return None

        module_parts = _split_module(node.module)
        package_parts = self._current_package_parts()
        up_levels = node.level - 1
        if up_levels > len(package_parts):
            return None

        base = package_parts[:len(package_parts) - up_levels]
        return base + module_parts

    def _current_package_parts(self):
        return self._current_module_parts[:-1]

    def _module_parts(self, path):
        rel_path = self.rel_path(path).with_suffix("")
        return rel_path.parts


def _split_module(module):
    if not module:
        return ()
    return tuple(module.split("."))

import functools
import ast
import tokenize
from pathlib import Path
from ....check.file import FileChecker
from ....check import find_all

__all__ = ('AstChecker', 'get_checkers')


class AstChecker(FileChecker, ast.NodeVisitor):
    """Groups checks for python source code."""

    _ast_cache = {}

    def __init__(self, base_path, package_name=None, repo=None, st_build=4180):
        super().__init__(
            base_path,
            package_name=package_name,
            repo=repo,
            st_build=st_build,
        )

    def check(self):
        self.visit_all_pyfiles()

    def visit_all_pyfiles(self):
        pyfiles = self.glob("**/*.py")
        for path in pyfiles:
            with self.file_context(path):
                root = self._get_ast(path)
                if root:
                    self.visit(root)

    def _get_ast(self, path):
        try:
            return self._ast_cache[path]
        except KeyError:
            self._ast_cache[path] = None

        try:
            # tokenize.open() honors PEP 263 encoding cookies and defaults to UTF-8,
            # avoiding locale-dependent decoding behavior on Windows.
            with tokenize.open(str(path)) as f:
                source = f.read()
            the_ast = ast.parse(source, str(path))
        except SyntaxError as e:
            with self.context("Line: {}".format(e.lineno)):
                self.fail("Unable to parse Python file", exception=e)
        except UnicodeDecodeError as e:
            self.fail("Unable to decode Python file", exception=e)
        else:
            self._ast_cache[path] = the_ast
            return the_ast

    def node_context(self, node):
        return self.context("Line: {}, Column: {}".format(node.lineno, node.col_offset + 1))


get_checkers = functools.partial(
    find_all,
    Path(__file__).parent,
    __package__,
    base_class=AstChecker
)

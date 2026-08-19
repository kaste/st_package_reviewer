import logging
import token
import tokenize

from . import FileChecker

l = logging.getLogger(__name__)


class CheckPackageMetadata(FileChecker):

    def check(self):
        if self.sub_path("package-metadata.json").is_file():
            self.fail("'package-metadata.json' is supposed to be automatically generated "
                      "by Package Control during installation")


class CheckRootInitContents(FileChecker):

    def check(self):
        path = self.sub_path("__init__.py")
        if path.is_file() and _contains_python_code(path):
            self.fail("The root-level '__init__.py' must be empty or contain only comments. "
                      "Package Control discards this file during installation to avoid "
                      "Sublime Text reload errors, so it cannot be used as the entrypoint "
                      "for your package. You may also want to remove it if it is not needed "
                      "by your development tooling.")


class CheckPycFiles(FileChecker):

    def check(self):
        pyc_files = self.glob("**/*.pyc")
        if not pyc_files:
            return

        for path in pyc_files:
            if path.with_suffix(".py").is_file():
                with self.file_context(path):
                    self.fail("'.pyc' file is redundant because its corresponding .py file exists")


class CheckCacheFiles(FileChecker):

    def check(self):
        cache_files = self.glob("**/*.cache")
        if not cache_files:
            return

        for path in cache_files:
            with self.file_context(path):
                self.fail("'.cache' file is redundant and created by ST automatically")


class CheckSublimePackageFiles(FileChecker):

    def check(self):
        cache_files = self.glob("**/*.sublime-package")
        if not cache_files:
            return

        for path in cache_files:
            with self.file_context(path):
                self.fail("'.sublime-package' files have no business being inside a package")


class CheckSublimeWorkspaceFiles(FileChecker):

    def check(self):
        cache_files = self.glob("**/*.sublime-workspace")
        if not cache_files:
            return

        for path in cache_files:
            with self.file_context(path):
                self.fail("'.sublime-workspace' files contain session data and should never be "
                          "submitted to version control")


def _contains_python_code(path):
    insignificant_tokens = {
        token.ENCODING,
        token.ENDMARKER,
        token.INDENT,
        token.DEDENT,
        token.NEWLINE,
        token.NL,
        token.COMMENT,
    }
    try:
        with path.open("rb") as f:
            return any(
                item.type not in insignificant_tokens
                for item in tokenize.tokenize(f.readline)
            )
    except (SyntaxError, tokenize.TokenError, UnicodeDecodeError):
        return True

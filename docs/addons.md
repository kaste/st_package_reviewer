# Developing additional file checkers

`--add-file-checkers PATH` adds checks to the built-in suite; it does not replace
it. Repeat the option for multiple directories. `--exclude ClassName` applies to
both built-in and additional classes. The path can be relative to your current
working directory, absolute, or start with `~`.

## Ownership and layout

You can maintain your own rules in your own repository without forking the
reviewer. For example:

```text
lsp_add_checks/                 # Root of the addon Git repository.
  pyproject.toml
  uv.lock
  lsp_review_checks/
    __init__.py
    check_settings_menu.py
    _helpers.py
  tests/
    test_settings_menu.py
    test_cli.py
    packages/
      valid_menu/
      missing_menu/
```

Point the reviewer at **`lsp_review_checks/`**, not at the repository root.
Discovery imports Python modules recursively, so keep tests, scripts, and fixture
packages outside that directory. There is no registration decorator, entry point,
Sublime Text runtime, or required publishing step. `__init__.py` is optional, but
using a regular Python package makes editor navigation and unit-test imports easy.
Define checkers in modules, not just in `__init__.py` (which discovery skips).

## Minimal API

```python
from st_package_reviewer.check.file import FileChecker


class LspCheckSettingsMenu(FileChecker):
    def check(self):
        for path in self.glob("**/Main.sublime-menu"):
            with self.file_context(path):
                # Inspect this file and enforce your own menu convention.
                # self.fail(...), self.warn(...), or self.notice(...)
                ...
```

- Inherit `FileChecker`; implement `check()`. Inherit `AstChecker` instead for
  Python AST visitors. Inherit their constructor rather than narrowing its
  signature.
- The reviewer supplies `base_path`, `package_name`, `repo`, `tag_prefixes`,
  `st_build`, and normalized `platforms` to built-in and additional checks alike.
- `glob`, `globs`, `sub_path`, and `file_context` are available for file handling.
  Always read text with an explicit encoding. `st_package_reviewer.lib.jsonc`
  parses Sublime's JSON with comments/trailing commas.
  No better documentation is available right now.
- Prefix class names with `Lsp` or another project-specific name to "namespace" them.
  Exclusions match simple class names, so excluding a name disables every checker with that name.
- Use relative imports for helpers within your addon (`from ._helpers import ...`).
  The loader gives each directory a private import namespace, avoiding collisions
  between identically named folders without changing `sys.path`.

Run the resulting rule together with the built-ins:

```bash
uv run st_package_reviewer \
  --add-file-checkers lsp_review_checks \
  --exclude CheckSettingsMenuEntry \
  --package-name LSP-oxfmt /path/to/LSP-oxfmt
```

Failures fail the review; warnings do so with `--fail-on-warnings`.
Checker exceptions produce internal-error reports; import/configuration errors
are reported before a package is reviewed. `--debug` preserves import tracebacks.

## Dependencies and the edit/test loop

The addon is a normal Python project depending on a pinned reviewer revision.
For unit tests and the package CLI, you can check out **only the addon
repository**: uv installs the reviewer dependency into the addon's environment.
The existing channel-PR script still requires a reviewer checkout; that workflow
is described separately below.

```toml
[project]
name = "lsp-review-checks"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["st-package-reviewer"]

[tool.uv]
package = false

[tool.uv.sources]
st-package-reviewer = { git = "https://github.com/kaste/st_package_reviewer" }

[dependency-groups]
dev = ["pytest>=8,<9", "pytest-cov>=5,<6", "pytest-xdist>=3,<4"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

If you are changing the reviewer itself, you can temporarily replace its Git source with
`{ path = "../st_package_reviewer", editable = true }` and regenerate the lockfile.


## Example workflow

Write a failing unit test before implementing a rule:

```python
from lsp_review_checks.check_settings_menu import LspCheckSettingsMenu
from st_package_reviewer.runner import CheckRunner


def test_missing_menu(tmp_path):
    (tmp_path / "LSP-test.sublime-settings").write_text("{}", encoding="utf-8")
    runner = CheckRunner([LspCheckSettingsMenu])
    runner.run(tmp_path, package_name="LSP-test")
    assert not runner.errors  # Unexpected exceptions are not expected failures.
    assert [failure.message for failure in runner.failures] == ["Expected message"]
```

The rule in that example still needs to be implemented; the point is to test the
same reporting lifecycle as production without running unrelated built-in rules.
Add CLI smoke tests using `sys.executable -m st_package_reviewer` on small fixture
packages to verify discovery, relative imports, exclusions, reports, and exit
codes. There is no need to copy or depend on the reviewer's own test suite.

```bash
uv sync --group dev
uv run pytest -xq tests/test_settings_menu.py  # red -> implement -> green
uv run pytest -f                             # xdist's rerun-on-failure loop
uv run pytest -q --cov=lsp_review_checks
uv run st_package_reviewer --add-file-checkers lsp_review_checks /path/to/package
```

CI (of your addon) only needs the addon checkout: set up uv/Python 3.13, then run
`uv sync --locked --group dev` followed by `uv run pytest`.


## Iterating on a *concrete* channel PR (Optional)

Working dir is the **addon checkout** (for example, `lsp_add_checks/`). Alternate
focused tests with the existing PR script in a normal reviewer checkout:

```bash
uv run pytest -q
uv run python -u ../st_package_reviewer/gh_action/action.py \
  --pr https://github.com/sublimehq/package_control_channel/pull/9580 \
  --add-file-checkers lsp_review_checks \
  --exclude CheckSettingsMenuEntry
```

Here `../st_package_reviewer` is an example location of the reviewer checkout;
substitute its actual path.

As you can see, this works against real PR's and roughly does the same as the
CI on the `repository.json` will do.  The output of this command is a `review.md`.
This should read like the comment the reviewer adds to the PR.

Typical workflow hence: you see a PR with awkward wording or a false positive (god forbid!).
Run the script against the actual PR.  You then have a review on your computer.
Read it, iterate on the checker, run the unit-tests, then the integration test against
the PR. Review `review.md` again.


## Consuming an addon in GitHub Actions

Both composite actions accept `add-file-checkers`: **one directory per line**,
allowing spaces in paths.

```yaml
- uses: actions/checkout@v6
  with:
    repository: your-org/lsp-review-checks
    ref: <TRUSTED_ADDON_COMMIT>
    path: review-addon

- uses: kaste/st_package_reviewer/gh_action@<REVIEWER_REF_WITH_ADDON_SUPPORT>
  with:
    pr: ${{ github.event.pull_request.html_url }}
    add-file-checkers: review-addon/lsp_review_checks
    exclude: CheckSettingsMenuEntry
```

The same input works with `gh_action_package`.

Only use **trusted addon code**, ideally pinned to a reviewed commit. Do not
implicitly load Python checkers from the package/PR being reviewed. Importing an
addon executes Python with the reviewer's privileges. A private import namespace
prevents name collisions, not access to secrets or the filesystem.

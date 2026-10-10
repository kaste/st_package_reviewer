# st_package_reviewer

[![Build Status](https://travis-ci.org/packagecontrol/st_package_reviewer.svg?branch=master)](https://travis-ci.org/packagecontrol/st_package_reviewer)
[![Coverage Status](https://coveralls.io/repos/github/packagecontrol/st_package_reviewer/badge.svg?branch=master)](https://coveralls.io/github/packagecontrol/st_package_reviewer?branch=master)

A tool to review packages for [Sublime Text][]
(and its package manager [Package Control][]).
Supports passing local file paths
or URLs to GitHub repositories.

This README focuses on installation and usage of the tool.
The complete catalog of emitted failures, warnings, and notices is in
[rules.md](rules.md). For how to *resolve* failures or warnings reported by the
tool, [refer to the wiki][wiki].


## Usage as a GitHub Action

- Channel/registry PRs: see [gh_action/README.md](gh_action/README.md)
- Package/plugin repositories: see [gh_action_package/README.md](gh_action_package/README.md)

### Alt Recipe: run on a package/plugin repository

If you can't or don't want to use the github action you can also use a workflow like this:

```yaml
name: Package Review
on:
  pull_request:
  push:
    branches: [master, main]

jobs:
  package-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          # Repository checks inspect tags; the checkout action does not fetch
          # them by default for shallow clones.
          fetch-depth: 0

      - uses: astral-sh/setup-uv@v8.1.0
        with:
          python-version: "3.13"
          # This workflow has no local uv project dependency file to key on.
          enable-cache: false

      - name: Run st_package_reviewer (official fork)
        run: uvx --from git+https://github.com/kaste/st_package_reviewer.git st_package_reviewer --repo=. .
        # Optional: pin and/or fail on warnings too
        # run: uvx --from git+https://github.com/kaste/st_package_reviewer.git@<TAG_OR_SHA> st_package_reviewer --repo=. --fail-on-warnings .
```

This runs package checks on the checked-out repository (`.`) and enables repository checks via `--repo=.`.
Repository checks need access to tags, so the checkout must fetch them.


## Installation

Requires **Python 3.13**.

This fork is currently **not published on PyPI**.
Install from GitHub instead:

```bash
# uv (tool install)
$ uv tool install --from git+https://github.com/kaste/st_package_reviewer.git st_package_reviewer
# optionally pin:
$ uv tool install --from git+https://github.com/kaste/st_package_reviewer.git@<TAG_OR_SHA> st_package_reviewer

# pip
$ pip install git+https://github.com/kaste/st_package_reviewer.git
# optionally pin:
$ pip install git+https://github.com/kaste/st_package_reviewer.git@<TAG_OR_SHA>
```


## Usage

```
usage: st_package_reviewer [-h] [--version] [--clip] [--repo-only]
                           [--package-name PACKAGE_NAME] [--repo [REPO]]
                           [--tag-prefix TAG_PREFIXES] [--st-build ST_BUILD]
                           [--platforms PLATFORMS] [--exclude CLASS_NAME]
                           [--add-file-checkers PATH]
                           [-w] [--compact] [-v] [--debug]
                           [path_or_URL [path_or_URL ...]]

Check a Sublime Text package for common errors.

positional arguments:
  path_or_URL           URL to the repository or path to the package to be checked. If not provided, runs in interactive mode.

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --clip                Copy report to clipboard.
  --repo-only           Do not check the package itself and only its repository.
  --package-name PACKAGE_NAME
                        Proposed package name (as used in the registry;
                        enables additional checks).
  --repo [REPO]         Enable repository checks for package paths.
                        Optional value: git repo path or URL.
                        Default: current directory (.).
  --tag-prefix TAG_PREFIXES
                        Expected Package Control tag prefix. Repeat for multiple
                        prefixes; an empty value has tags: true semantics.
  --st-build ST_BUILD   Minimum required Sublime Text build.
                        Default: 4180.
  --platforms PLATFORMS
                        Comma-separated supported platforms. Use 'all' for all
                        platforms. Default: all.
  -w, --fail-on-warnings
                        Return a non-zero exit code for warnings as well.
  --exclude CLASS_NAME  Skip a checker class by name. Repeat to exclude multiple classes.
  --add-file-checkers PATH
                        Load additional file/AST checkers from a trusted directory.
                        Repeat for multiple directories.
  --compact             Reduce output verbosity.
  -v, --verbose         Increase verbosity.
  --debug               Enter pdb on exceptions. Implies --verbose.

Return values:
    0: No errors
    -1: Invalid command line arguments

Additional return values in non-interactive mode (a combination of bit flags):
    1: Package check finished with failures
    2: Repository check finished with failures
    4: Unable to download repository

Interactive mode:
    Enter package paths or repository URLS continuously.
    Type `c` to copy the last report to your clipboard.
```


Skip whole checker classes by their exact, case-sensitive names (see
[rules.md](rules.md)), for example:

```bash
st_package_reviewer --exclude CheckSettingsMenuEntry --exclude CheckLicense --package-name LSP-oxfmt .
```

Exclusions apply to file, AST, and repository checks. Unknown names are ignored.
Both GitHub Actions accept an optional `exclude` input with whitespace-separated
class names (spaces or newlines).


## Additional checker repositories

Use `--add-file-checkers /path/to/addon/checkers` to add your own file or AST
checkers alongside the built-ins. Repeat for multiple directories and use
`--exclude` to disable a stock rule or an addon class.

For the directory layout, minimal API, TDD workflow, dependency setup, and
GitHub Action integration, see [Developing additional checkers](docs/addons.md).


## Development (uv, Python 3.13)

This repo uses [uv](https://github.com/astral-sh/uv) and targets Python 3.13.

- Setup environment: `uv sync --group dev`
- Run the CLI: `uv run st_package_reviewer --version`
- Run tests: `uv run pytest`
- Lint: `uv run flake8 .`
- Optional watch mode (loop on fail): `uv run pytest -f`
- Optional parallel runs: `uv run pytest -n auto`


[Sublime Text]: https://sublimetext.com/
[Package Control]: https://packagecontrol.io/
[wiki]: https://github.com/packagecontrol/st_package_reviewer/wiki

## Development Workflow

- Tests
  - Quick run: `uv run pytest -q`
  - With coverage: `uv run pytest --cov st_package_reviewer --cov tests --cov-report term-missing`
  - Watch mode (loop on fail): `uv run pytest -f`
  - Parallel runs: `uv run pytest -n auto`

- Run the CLI during development
  - Are we there?: `uv run st_package_reviewer --version`
  - Interactive: `uv run st_package_reviewer`
  - Local path: `uv run st_package_reviewer /path/to/package`
  - GitHub repo URL: `uv run st_package_reviewer https://github.com/owner/repo`
  - Override package name during local review:
    `uv run st_package_reviewer --package-name "My Package" /path/to/package`
  - Enable repo tag checks using the current git checkout (bare `--repo` means `.`):
    `uv run st_package_reviewer --repo /path/to/package`
  - Enable repo tag checks for an extracted archive (which usually has no `.git`) using a remote URL:
    `uv run st_package_reviewer --repo https://github.com/owner/repo /path/to/extracted/archive`
  - Review for older Sublime builds explicitly (legacy API-init constraints):
    `uv run st_package_reviewer --st-build 4169 /path/to/package`

- Canary-test the GitHub Action against a real Package Control Channel PR before
  updating upstream workflow refs:

  ```bash
  # Push the candidate reviewer commit to the remote canary ref.
  git push kaste HEAD:refs/heads/action-canary --force-with-lease

  # Run the canary with the concrete PR whose review output you want to inspect.
  gh workflow run action-canary.yml \
    --repo kaste/st_package_reviewer \
    --ref main \
    -f pr=https://github.com/sublimehq/package_control_channel/pull/REAL_PR_NUMBER
  ```

  Then watch the run and inspect the generated `review.md` artifact:

  ```bash
  gh run list --repo kaste/st_package_reviewer --workflow action-canary.yml --limit 1
  gh run watch RUN_ID --repo kaste/st_package_reviewer
  ```

  The canary invokes `kaste/st_package_reviewer/gh_action@action-canary` as a
  remote composite action, so GitHub downloads it as an action archive without
  `.git` metadata, just like Package Control Channel will.  It exercises the real
  review-generation phase for the supplied PR.  It does not test the follow-up
  `workflow_run` comment-posting phase.

## Releases

- Create a tag named `vX.Y.Z` (for example `v0.4.0`) for versioned releases.
- This fork is currently not published on PyPI.
- Per GitHub convention, update the tag `vX` to the latest subversion.  E.g. `v1` moves to `v.1.1.0`
- For automation, prefer pinning GitHub Action usage to a tag or commit SHA.

# Package/Plugin Repository Action

This composite action is meant for package/plugin repositories that want to run `st_package_reviewer` directly on their own checkout.

It is separate from `gh_action/` (which is designed for channel/registry PR diffs).

## Inputs

- `path` (optional): Path to the package directory to review. Default: `.`
- `repo` (optional): Value passed to `--repo` for repository checks. Default: `.`
  - Set to empty (`repo: ""`) to disable repository health checks.
- `package-name` (optional): Explicit package name.
  - If omitted, this action guesses it from `GITHUB_REPOSITORY` (repo name part).
- `st-build` (optional): Passed to `--st-build`.
- `fail-on-warnings` (optional): `"true"` to fail on warnings too. Default: `"false"`.
- `compact` (optional): `"true"` to pass `--compact`. Default: `"false"`.

## Example Usage

```yaml
name: Package Review
on:
  pull_request:
  push:
    branches: [main, master]

jobs:
  package-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # Repository checks inspect tags; the checkout action does not fetch
          # them by default for shallow clones.
          fetch-depth: 0

      - name: Review this package repository
        uses: kaste/st_package_reviewer/gh_action_package@<PINNED_REF>
        with:
          # path: .
          # package-name: My Package   # optional override when repo-name guess is not desired
          # st-build: 4180             # optional
          # fail-on-warnings: "true"  # optional
```

## Notes

- Pin `@<PINNED_REF>` to a stable tag or commit SHA.
- Repository health checks need access to git tags. Use `fetch-depth: 0` with
  `actions/checkout`, or pass a remote URL via `repo:` if you intentionally keep
  the local checkout shallow.
- `package-name` guessing is a convenience; set `package-name` explicitly if your Package Control name differs from the repository name.

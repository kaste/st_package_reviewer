# TODO

## Platform-specific package checks

The old platform-usage warning was too broad: seeing `sublime.platform()` or
`sublime.arch()` often means the package author already handled platform
specifics, not that the package needs a Package Control `platforms` restriction.

Collect concrete, recurring pain points instead and add targeted checks for
those. Possible examples:

- Shell commands or `shell=True` without clear platform handling.
- Hard-coded platform tools such as `pbcopy`, `xdg-open`, `open`, `cmd.exe`, or
  `powershell`.
- Hard-coded Unix paths, Windows paths, or path separators.
- Platform branches that implement only one OS and raise/return unsupported for
  the others.
- Bundled platform-specific binaries without matching Package Control platform
  metadata.

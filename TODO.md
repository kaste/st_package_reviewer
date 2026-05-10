# TODO

## Platform-specific package checks

The old platform-usage warning was too broad: seeing `sublime.platform()` or
`sublime.arch()` often means the package author already handled platform
specifics, not that the package needs a Package Control `platforms` restriction.

Collect concrete, recurring pain points instead and add targeted checks for
those. Possible examples:

- `subprocess.Popen` on Windows without hidden-window `STARTUPINFO` handling.
- Shell commands or `shell=True` without clear platform handling.
- Hard-coded platform tools such as `pbcopy`, `xdg-open`, `open`, `cmd.exe`, or
  `powershell`.
- Hard-coded Unix paths, Windows paths, or path separators.
- Platform branches that implement only one OS and raise/return unsupported for
  the others.
- Bundled platform-specific binaries without matching Package Control platform
  metadata.

## Keymap context checks

Masked conflicts with Sublime Text default key bindings are usually fine when a
`context` is present, so the reviewer no longer reports them by default. If this
comes back, add targeted checks for suspicious contexts instead of enumerating
all masked conflicts. Possible examples:

- Bindings that only use broad built-in state contexts such as `num_selections`
  or `selection_empty`.
- Treat scope-limiting contexts such as `selector` and package-specific settings
  like `setting.<package-name>...` as intentional and quiet.
- Consider reporting custom contexts only when the message can explain a concrete
  risk and a concrete fix.

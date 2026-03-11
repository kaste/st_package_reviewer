import argparse
import json


"""
Tooling: given a workspace file and a package name, extract a single
(url, version) pair for the newest release by date.

Pre-releases are valid candidates.
"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Print the newest release (url, version) pair from a workspace file"
            " for a specific package"
        )
    )
    p.add_argument("workspace", help="Path to workspace JSON")
    p.add_argument("name", help="Package name to extract")
    p.add_argument(
        "-z",
        action="store_true",
        help="Separate entries with NUL (\\0) instead of newlines",
    )
    args = p.parse_args(argv)

    try:
        with open(args.workspace, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 1

    pkgs = data.get("packages", {})
    pkg = pkgs.get(args.name)
    if not isinstance(pkg, dict):
        return 2

    releases = pkg.get("releases", [])
    if not isinstance(releases, list):
        return 0

    selected = _newest_release(releases)

    for rel in selected:
        url = rel.get("url")
        if not url:
            continue
        ver = rel.get("version", "")
        if args.z:
            print(f"{url}\t{ver}", end="\0")
        else:
            print(f"{url}\t{ver}")
    return 0


def _newest_release(releases: list[dict]) -> list[dict]:
    candidates = [
        rel
        for rel in releases
        if isinstance(rel, dict) and rel.get("url")
    ]
    if not candidates:
        return []

    # thecrawl emits sortable ISO-like timestamps for release dates,
    # so plain string ordering is sufficient.
    newest = max(candidates, key=lambda rel: str(rel.get("date", "")))
    return [newest]


if __name__ == "__main__":
    raise SystemExit(main())

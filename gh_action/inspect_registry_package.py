import argparse
import json
from urllib.parse import urljoin
from urllib.request import urlopen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect one package in a channel/repository definition and print metadata."
    )
    parser.add_argument("--source", required=True, help="Channel or repository URL")
    parser.add_argument("--name", required=True, help="Package name")
    args = parser.parse_args(argv)

    package = _find_package(args.source, args.name)
    if package is None:
        return 2

    tags_mode = _is_tags_mode(package)
    print("tags_mode\t{}".format("1" if tags_mode else "0"))

    details = package.get("details")
    if isinstance(details, str) and details:
        print("repo\t{}".format(details))

    return 0


def _find_package(source_url, package_name):
    pending = [source_url]
    seen = set()

    while pending:
        url = pending.pop(0)
        if url in seen:
            continue
        seen.add(url)

        data = _load_json_url(url)
        if not isinstance(data, dict):
            continue

        for package in data.get("packages", []):
            if isinstance(package, dict) and package.get("name") == package_name:
                return package

        includes = data.get("includes")
        if not isinstance(includes, list):
            continue

        for include in includes:
            if not isinstance(include, str) or not include:
                continue
            pending.append(urljoin(url, include))

    return None


def _load_json_url(url):
    with urlopen(url) as response:
        return json.load(response)


def _is_tags_mode(package_definition):
    releases = package_definition.get("releases")
    if not isinstance(releases, list) or not releases:
        return True

    for release in releases:
        if not isinstance(release, dict):
            continue
        if any(key in release for key in ("asset", "url", "branch")):
            return False

    return True


if __name__ == "__main__":
    raise SystemExit(main())

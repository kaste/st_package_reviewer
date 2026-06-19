from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Protocol
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


class Logger(Protocol):
    def write(self, message: str) -> None: ...


def review_package_entry(
    package_name: str,
    package_definition: dict[str, object] | None,
    source_text: str | None = None,
) -> EntryReview:
    review = EntryReview()
    if not isinstance(package_definition, dict):
        return review

    check_redundant_details_fields(package_name, package_definition, review)
    check_release_mode_advice(package_name, package_definition, review)

    if source_text is not None:
        check_source_entry(package_name, source_text, review)

    return review


def load_package_entry_source(
    package_definition: dict[str, object] | None,
    source_cache: dict[str, str | None],
    console: Logger,
) -> str | None:
    if not isinstance(package_definition, dict):
        return None

    source = package_definition.get("source")
    if not isinstance(source, str) or not source:
        return None

    if source not in source_cache:
        source_cache[source] = fetch_text(source, console)

    return source_cache[source]


class EntryReview:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.notices: list[str] = []

    @property
    def empty(self) -> bool:
        return not (self.failures or self.warnings or self.notices)


def check_redundant_details_fields(
    package_name: str,
    package_definition: dict[str, object],
    review: EntryReview,
) -> None:
    details = package_definition.get("details")
    if not isinstance(details, str):
        return

    repo = parse_hosted_repo(details)
    if repo is None:
        return

    author = package_definition.get("author")
    if isinstance(author, str):
        if same_value(author, repo.owner):
            review.warnings.append(
                f"`{package_name}` sets `author` to `{author}`, which is already "
                "derived from `details`. Omit it unless it differs from the "
                "repository owner."
            )
    elif isinstance(author, list) and len(author) == 1:
        only_author = author[0]
        if same_value(only_author, repo.owner):
            review.warnings.append(
                f"`{package_name}` sets `author` to [`{only_author}`], which is "
                "already derived from `details`. Omit it unless it differs from "
                "the repository owner; if you keep it, prefer a simple string "
                "unless there are multiple authors."
            )
        elif isinstance(only_author, str):
            review.warnings.append(
                f"`{package_name}` sets `author` to a single-item array. "
                "Prefer a simple string unless there are multiple authors."
            )

    name = package_definition.get("name")
    if isinstance(name, str) and name == repo.repo:
        review.warnings.append(
            f"`{package_name}` sets `name` to `{name}`, which is already derived "
            "from `details`. Omit it unless the display name differs from the "
            "repository name."
        )

    issues = package_definition.get("issues")
    standard_issues = repo.standard_issues_url()
    if isinstance(issues, str) and same_url(issues, standard_issues):
        review.warnings.append(
            f"`{package_name}` sets `issues` to the standard issue tracker "
            f"URL `{issues}`, which is already derived from `details`."
        )


def check_release_mode_advice(
    package_name: str,
    package_definition: dict[str, object],
    review: EntryReview,
) -> None:
    releases = package_definition.get("releases")
    if not isinstance(releases, list) or not releases:
        return

    release_dicts = [release for release in releases if isinstance(release, dict)]
    if not release_dicts:
        return

    if all("branch" in release and "tags" not in release for release in release_dicts):
        review.notices.append(
            f"Tip: `{package_name}` only defines branch-based releases. Consider "
            "adding at least one `tags: true` release so Package Control can "
            "install stable tagged versions."
        )


def check_source_entry(package_name: str, source_text: str, review: EntryReview) -> None:
    entries = extract_package_entries(source_text)
    if not entries:
        return

    matching_entries = [entry for entry in entries if entry.name == package_name]
    if not matching_entries:
        return

    names = [entry.name for entry in entries]
    for entry in matching_entries:
        indentation_issues = source_entry_indentation_issues(entry)
        for line_number, message in indentation_issues:
            review.failures.append(
                f"`{package_name}` has invalid indentation on line {line_number}: "
                f"{message}"
            )

        sorting_issue = source_entry_sorting_issue(names, entry.index)
        if sorting_issue:
            review.failures.append(f"`{package_name}` is not sorted: {sorting_issue}")


def format_entry_review(entry_review: EntryReview) -> str:
    lines = ["Entry checks:", ""]
    for title, messages in (
        ("failures", entry_review.failures),
        ("warnings", entry_review.warnings),
        ("notices", entry_review.notices),
    ):
        if not messages:
            continue
        lines.append(f"{len(messages)} {singular_or_plural(len(messages), title)}:")
        lines.extend(f"- {message}" for message in messages)
        lines.append("")
    return "\n".join(lines).rstrip()


class HostedRepo:
    def __init__(self, host: str, owner: str, repo: str) -> None:
        self.host = host
        self.owner = owner
        self.repo = repo

    def standard_issues_url(self) -> str:
        if self.host == "gitlab.com":
            return f"https://{self.host}/{self.owner}/{self.repo}/-/issues"
        return f"https://{self.host}/{self.owner}/{self.repo}/issues"


class SourceEntry:
    def __init__(self, name: str, index: int, start: int, end: int, source: str) -> None:
        self.name = name
        self.index = index
        self.start = start
        self.end = end
        self.source = source

    @property
    def lines(self) -> list[tuple[int, str]]:
        start_line = self.source.count("\n", 0, self.start) + 1
        prefix_start = self.source.rfind("\n", 0, self.start) + 1
        suffix_end = self.source.find("\n", self.end)
        if suffix_end == -1:
            suffix_end = len(self.source)

        text = self.source[prefix_start:suffix_end]
        return [
            (start_line + offset, line)
            for offset, line in enumerate(text.splitlines())
        ]


def singular_or_plural(count: int, plural: str) -> str:
    if count == 1 and plural.endswith("s"):
        return plural[:-1]
    return plural


def parse_hosted_repo(url: str) -> HostedRepo | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host not in {"bitbucket.org", "codeberg.org", "github.com", "gitlab.com"}:
        return None

    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None

    return HostedRepo(host, parts[0], strip_git_suffix(parts[1]))


def fetch_text(location: str, console: Logger) -> str | None:
    try:
        if re.match(r"https?://", location, re.I):
            req = Request(location, headers={"User-Agent": "st_package_reviewer"})
            with urlopen(req, timeout=30) as response:
                return response.read().decode("utf-8", "strict")

        path = Path(location)
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except Exception as exc:
        console.write(f"::notice ::Could not read entry source {location}: {exc}")

    return None


def extract_package_entries(source: str) -> list[SourceEntry]:
    array_start = find_json_array_for_key(source, "packages")
    if array_start is None:
        return []

    entries = []
    for index, start, end, value in iterate_json_array_objects(source, array_start):
        name = package_entry_name(value)
        if name:
            entries.append(SourceEntry(name, index, start, end, source))
    return entries


def source_entry_indentation_issues(entry: SourceEntry) -> list[tuple[int, str]]:
    issues = []
    expected_indent = 2
    for line_number, line in entry.lines:
        if not line.strip():
            continue

        leading = line[: len(line) - len(line.lstrip(" \t"))]
        if " " in leading:
            issues.append((line_number, "use tabs for indentation, not spaces"))
            continue

        stripped = line.lstrip("\t")
        expected_line_indent = expected_indent
        if stripped.startswith(("}", "]")):
            expected_line_indent -= 1

        actual_indent = len(leading)
        if actual_indent != expected_line_indent:
            issues.append(
                (
                    line_number,
                    f"expected {expected_line_indent} leading tab(s), "
                    f"found {actual_indent}",
                )
            )

        expected_indent += json_nesting_delta(stripped)

    return issues


def source_entry_sorting_issue(names: list[str], index: int) -> str:
    name = names[index]
    key = name.casefold()
    if index > 0 and names[index - 1].casefold() > key:
        return f"move it before `{names[index - 1]}`."
    if index + 1 < len(names) and key > names[index + 1].casefold():
        return f"move it after `{names[index + 1]}`."
    return ""


def find_json_array_for_key(source: str, key: str) -> int | None:
    key_literal = json.dumps(key)
    start = source.find(key_literal)
    while start != -1:
        pos = skip_ws(source, start + len(key_literal))
        if pos < len(source) and source[pos] == ":":
            value_pos = skip_ws(source, pos + 1)
            if value_pos < len(source) and source[value_pos] == "[":
                return value_pos
        start = source.find(key_literal, start + 1)
    return None


def iterate_json_array_objects(
    source: str,
    array_start: int,
) -> list[tuple[int, int, int, dict[str, object]]]:
    values = []
    index = 0
    pos = skip_ws(source, array_start + 1)
    while pos < len(source) and source[pos] != "]":
        if source[pos] != "{":
            return values

        end = find_json_value_end(source, pos)
        try:
            value = json.loads(source[pos:end])
        except json.JSONDecodeError:
            return values

        if isinstance(value, dict):
            values.append((index, pos, end, value))

        index += 1
        pos = skip_ws(source, end)
        if pos < len(source) and source[pos] == ",":
            pos = skip_ws(source, pos + 1)

    return values


def find_json_value_end(source: str, start: int) -> int:
    stack = []
    pos = start
    while pos < len(source):
        char = source[pos]
        if char == '"':
            pos = skip_json_string(source, pos)
            continue
        if char in "[{":
            stack.append(char)
        elif char in "]}":
            if stack:
                stack.pop()
            if not stack:
                return pos + 1
        pos += 1
    return len(source)


def skip_json_string(source: str, start: int) -> int:
    pos = start + 1
    while pos < len(source):
        char = source[pos]
        if char == "\\":
            pos += 2
            continue
        if char == '"':
            return pos + 1
        pos += 1
    return len(source)


def skip_ws(source: str, start: int) -> int:
    pos = start
    while pos < len(source) and source[pos] in " \t\r\n":
        pos += 1
    return pos


def package_entry_name(entry: dict[str, object]) -> str:
    name = entry.get("name")
    if isinstance(name, str) and name:
        return name

    details = entry.get("details")
    if not isinstance(details, str):
        return ""

    repo = parse_hosted_repo(details)
    if repo is None:
        return details.strip("/").rsplit("/", 1)[-1]
    return repo.repo


def json_nesting_delta(line: str) -> int:
    delta = 0
    pos = 0
    while pos < len(line):
        char = line[pos]
        if char == '"':
            pos = skip_json_string(line, pos)
            continue
        if char in "[{":
            delta += 1
        elif char in "]}":
            delta -= 1
        pos += 1
    return delta


def same_value(value: object, expected: str) -> bool:
    return isinstance(value, str) and value.casefold() == expected.casefold()


def same_url(url: str, expected: str) -> bool:
    return normalize_url(url) == normalize_url(expected)


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return parsed._replace(path=path, query="", fragment="").geturl().casefold()


def strip_git_suffix(value: str) -> str:
    if value.endswith(".git"):
        return value[:-4]
    return value



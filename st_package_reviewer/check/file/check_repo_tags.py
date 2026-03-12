import re
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple, Optional

from . import FileChecker


class VersionInfo(NamedTuple):
    major: int
    minor: int
    patch: int
    prerelease: Optional[str]
    build: Optional[str]

    @property
    def is_final(self) -> bool:
        return self.prerelease is None and self.build is None

    @property
    def is_prerelease(self) -> bool:
        return self.prerelease is not None


SEMVER_RE = re.compile(
    r'^'
    r'(0|[1-9]\d*)\.'
    r'(0|[1-9]\d*)\.'
    r'(0|[1-9]\d*)'
    r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
    r'(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
    r'$'
)


def _parse_version(version):
    match = SEMVER_RE.match(version)
    if not match:
        return None

    major, minor, patch, prerelease, build = match.groups()
    return VersionInfo(
        int(major),
        int(minor),
        int(patch),
        prerelease,
        build,
    )


def _parse_version_from_tag(tag_name):
    if tag_name.startswith("v"):
        tag_name = tag_name[1:]

    return _parse_version(tag_name)


def _normalize_tag_name(tag_name):
    if tag_name.startswith("v"):
        return tag_name[1:]
    return tag_name


def _semver_sort_key(version):
    prerelease_marker = 0 if version.prerelease else 1
    return (
        version.major,
        version.minor,
        version.patch,
        prerelease_marker,
        version.prerelease or "",
        version.build or "",
    )


def git(*args):
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _parse_semver_tags(tag_names):
    parsed = []
    for tag_name in tag_names:
        version = _parse_version_from_tag(tag_name)
        if version is not None:
            parsed.append((tag_name, version))
    return parsed


def _latest_semver_tag(semver_tags):
    return max(semver_tags, key=lambda item: _semver_sort_key(item[1]))[0]


def _select_best_semver_tag(tag_names):
    parsed_versions = _parse_semver_tags(tag_names)
    if not parsed_versions:
        return None

    best_tag, _ = max(
        parsed_versions,
        key=lambda item: _semver_sort_key(item[1]),
    )
    return _normalize_tag_name(best_tag)


class CheckRepoTags(FileChecker):

    def check(self):
        if not self.repo:
            return

        repo_path = Path(self.repo)
        is_local_repo = repo_path.is_dir() and self._is_git_repo(repo_path)

        with self.context("Repository: {}".format(self.repo)):
            if is_local_repo:
                tags, error = self._list_local_tags(repo_path)
            else:
                tags, error = self._list_remote_tags(self.repo)
            if error:
                self.fail("Unable to inspect repository tags: {}".format(error))
                return

            semver_tags = _parse_semver_tags(tags)
            if not semver_tags:
                message = "No semantic version tags found"
                if not tags:
                    message += " (no tags found at all)"
                self.fail(message)
                return

            if all(version.is_prerelease for _, version in semver_tags):
                self.warn("Only found pre-release tags.")

            latest_semver_tag = _latest_semver_tag(semver_tags)
            if is_local_repo:
                tip_status = self._collect_tip_status_local(repo_path, latest_semver_tag)
            else:
                tip_status = self._collect_tip_status_remote(self.repo, latest_semver_tag)
            if not tip_status:
                return

            branch_name, tip_tag_version, commits_behind = tip_status
            if tip_tag_version:
                self.notice("Tip of {} is tagged with {}.".format(branch_name, tip_tag_version))
                return

            if commits_behind is not None:
                self.notice(
                    "Latest version {} is {} commit{} behind tip of {}."
                    .format(
                        _normalize_tag_name(latest_semver_tag),
                        commits_behind,
                        "s" if commits_behind != 1 else "",
                        branch_name,
                    )
                )

    def _is_git_repo(self, path):
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def _list_local_tags(self, path):
        proc = subprocess.run(
            ["git", "-C", str(path), "tag", "--list"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return [], proc.stderr.strip() or "git tag failed"

        tags = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        return tags, None

    def _list_remote_tags(self, repo):
        proc = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", str(repo)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return [], proc.stderr.strip() or "git ls-remote failed"

        tags = []
        for line in proc.stdout.splitlines():
            if "\t" not in line:
                continue
            _, ref = line.split("\t", 1)
            if not ref.startswith("refs/tags/"):
                continue
            tags.append(ref[len("refs/tags/"):])

        return tags, None

    def _collect_tip_status_local(self, repo_path, latest_semver_tag):
        branch_name = git(
            "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"
        )
        if not branch_name:
            return None

        tags_raw = git(
            "-C", str(repo_path), "tag", "--points-at", "HEAD"
        )
        tip_tag_version = _select_best_semver_tag(tags_raw.splitlines() if tags_raw else [])

        commits_behind = self._count_commits_behind_local(repo_path, latest_semver_tag)
        return branch_name, tip_tag_version, commits_behind

    def _collect_tip_status_remote(self, repo, latest_semver_tag):
        branch_name = self._resolve_remote_default_branch(repo)
        if not branch_name:
            return None

        with tempfile.TemporaryDirectory(prefix="pkg-rev-git-") as tempdir:
            repo_path = Path(tempdir)
            init_ok = git(
                "-C", str(repo_path), "init", "-q"
            )
            if init_ok is None:
                return None

            add_ok = git(
                "-C", str(repo_path), "remote", "add", "origin", str(repo)
            )
            if add_ok is None:
                return None

            fetch_ok = git(
                "-C", str(repo_path), "fetch", "origin", branch_name, "--tags"
            )
            if fetch_ok is None:
                return None

            tip_tags_raw = git(
                "-C", str(repo_path), "tag", "--points-at", "FETCH_HEAD"
            )
            tip_tag_version = _select_best_semver_tag(
                tip_tags_raw.splitlines() if tip_tags_raw else []
            )

            commits_behind = self._count_commits_behind_clone(repo_path, latest_semver_tag)
            return branch_name, tip_tag_version, commits_behind

    def _resolve_remote_default_branch(self, repo):
        symref_output = git("ls-remote", "--symref", str(repo), "HEAD")
        if not symref_output:
            return None

        for line in symref_output.splitlines():
            if line.startswith("ref: refs/heads/") and line.endswith("\tHEAD"):
                return line.split("ref: refs/heads/", 1)[1].split("\t", 1)[0]

        return None

    def _count_commits_behind_local(self, repo_path, latest_semver_tag):
        count = git(
            "-C", str(repo_path), "rev-list", "--count",
            "{}..HEAD".format(latest_semver_tag),
        )
        return int(count) if count and count.isdigit() else None

    def _count_commits_behind_clone(self, repo_path, latest_semver_tag):
        count = git(
            "-C", str(repo_path), "rev-list", "--count",
            "{}..FETCH_HEAD".format(latest_semver_tag),
        )
        return int(count) if count and count.isdigit() else None

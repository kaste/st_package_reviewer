#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="action.py",
        description=(
            "Diff a channel/repository PR and review changed packages."
        ),
    )
    parser.add_argument("--pr", required=True, help="GitHub Pull Request URL")
    parser.add_argument(
        "--file",
        default="repository.json",
        help="Path within repo to channel JSON (default: repository.json)",
    )
    parser.add_argument(
        "--thecrawl",
        default="https://github.com/packagecontrol/thecrawl",
        help="Path to local thecrawl repo or URL (supports @ref for https URLs)",
    )
    ns = parser.parse_args(argv)
    ns.file = ns.file[2:] if ns.file.startswith("./") else ns.file
    return ns


def main(argv: list[str] | None = None) -> None:
    # Keep buffering policy outside this script (uv run python -u ... /
    # PYTHONUNBUFFERED=1) for consistent behavior across environments and
    # stream wrappers.
    console = Console()
    args = parse_args(argv)

    if not command_exists("gh"):
        console.write("Error: gh (GitHub CLI) is required")
        raise SystemExit(2)
    if not command_exists("uv"):
        console.write("Error: uv is required")
        raise SystemExit(2)

    os.environ.setdefault(
        "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ST_PACKAGE_REVIEWER", "0.0.0"
    )
    os.environ.setdefault(
        "SETUPTOOLS_SCM_PRETEND_VERSION",
        os.environ["SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ST_PACKAGE_REVIEWER"],
    )

    review_md = Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd())) / "review.md"
    init_review_md(review_md)

    with console.group("Fetching PR metadata"):
        console.write(f"Resolving PR metadata via gh: {args.pr}")
        try:
            pr_meta = fetch_pr_metadata(args.pr, args.file, console)
        except RuntimeError as exc:
            console.write(f"::error ::{exc}")
            raise SystemExit(2)
        console.write(f"Base URL:   {pr_meta.base_url}")
        console.write(f"Target URL: {pr_meta.head_url}")

    with console.group("Getting thecrawl"):
        try:
            crawler_repo = setup_thecrawl(
                args.thecrawl,
                Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd())) / ".thecrawl",
                console,
            )
        except RuntimeError as exc:
            console.write(f"::error ::{exc}")
            raise SystemExit(2)
        console.write(f"Using thecrawl at: {crawler_repo}")

    failures = 0
    with tempfile.TemporaryDirectory() as tmp_s:
        tmpdir = Path(tmp_s)
        base_reg = tmpdir / "base_registry.json"
        head_reg = tmpdir / "head_registry.json"

        with console.group("Generating base registry…"):
            if not generate_registry(crawler_repo, pr_meta.base_url, base_reg):
                raise SystemExit(1)

        with console.group("Generating target registry…"):
            if not generate_registry(crawler_repo, pr_meta.head_url, head_reg):
                raise SystemExit(1)

        script_dir = Path(__file__).resolve().parent
        root_dir = script_dir.parent
        try:
            head_packages = load_registry_packages(head_reg)
        except Exception as exc:
            console.write(f"::error ::Failed to load generated registry: {exc}")
            raise SystemExit(1)

        diff_proc = run(
            sys.executable,
            str(script_dir / "diff_repository.py"),
            "--base-file",
            str(base_reg),
            "--target-file",
            str(head_reg),
            "-z",
            capture_output=True,
            check=False,
        )
        if diff_proc.stderr:
            for line in diff_proc.stderr.splitlines():
                console.write(line)
        if diff_proc.returncode != 0:
            console.write(
                f"::error ::diff_repository.py failed with exit code {diff_proc.returncode}."
            )
            raise SystemExit(1)
        pkgs = [p for p in diff_proc.stdout.split("\0") if p]

        changes_line = ""
        for line in diff_proc.stderr.splitlines():
            if line.startswith("::notice title=CHANGES ::"):
                changes_line = line
                break
        append_changes_to_review_md(review_md, changes_line)

        if not pkgs:
            console.write("::notice ::No changed or added packages to crawl.")
            with review_md.open("a", encoding="utf-8") as f:
                f.write("## Result\n\nNo changed or added packages to review.\n\n")
            raise SystemExit(0)

        console.write(f"Crawling {len(pkgs)} package(s) from target registry…")

        with console.group("Preparing st_package_reviewer environment"):
            run_sh("uv sync --no-dev", cwd=root_dir)

        wsdir = tmpdir / "workspaces"
        wsdir.mkdir(parents=True, exist_ok=True)

        for pkg in pkgs:
            with console.group(f"Crawling: {pkg}"):
                wsfile = wsdir / f"{pkg}.json"
                console.write(f"Workspace file is {wsfile}")
                crawl = run(
                    "uv",
                    "run",
                    "-m",
                    "scripts.crawl",
                    "--registry",
                    str(head_reg),
                    "--workspace",
                    str(wsfile),
                    "--name",
                    pkg,
                    cwd=crawler_repo,
                    check=False,
                )
                if crawl.returncode != 0 or not wsfile.exists() or wsfile.stat().st_size == 0:
                    console.write(f"::error ::! Crawl failed for {pkg}")
                    failures += 1
                    continue

            review_repo_args: list[str] = []
            tags_mode, repo_url = inspect_registry_package(
                head_packages.get(pkg),
                pkg,
                console,
            )
            if tags_mode and repo_url:
                review_repo_args = ["--repo", repo_url]

            release = parse_workspace_release(wsfile, pkg)
            if release is None:
                console.write(f"::error  ::! No releases found for {pkg}")
                failures += 1
                continue

            url = release.get("url", "")
            if not url:
                console.write(f"::error  ::! Missing release URL for {pkg}")
                failures += 1
                continue

            ver = release.get("version", "")
            if not ver:
                console.write(
                    f"::warning ::Could not extract a version for {pkg} "
                    f"(url: {url}); using r1"
                )
                ver = "r1"

            safe_ver = re.sub(r"[^A-Za-z0-9._-]", "_", ver)
            workdir = tmpdir / "review" / pkg / safe_ver
            workdir.mkdir(parents=True, exist_ok=True)

            zipfile_path = workdir / "pkg.zip"
            with console.group(f"Downloading {pkg}-{ver}"):
                console.write(f"  Downloading release {ver}: {url}")
                if not download_zip(url, zipfile_path, console):
                    console.write(f"::error  ::! Download failed for {pkg}@{ver}")
                    failures += 1
                    continue

            with console.group(f"Unzipping {pkg}-{ver}"):
                topdir = unzip_release(zipfile_path, workdir, pkg, ver, console)
                if topdir is None:
                    failures += 1
                    continue

            with console.group(f"Reviewing {pkg}-{safe_ver}"):
                console.write(f"  Reviewing with st_package_reviewer: {topdir}")
                raw_review_out = workdir / "review.txt"
                with raw_review_out.open("w", encoding="utf-8") as out_file:
                    review = run(
                        "uv",
                        "run",
                        "--no-sync",
                        "st_package_reviewer",
                        "--compact",
                        "--package-name",
                        pkg,
                        *review_repo_args,
                        str(topdir),
                        cwd=root_dir,
                        stdout=out_file,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )

                emit_review_annotations(raw_review_out, console)
                append_package_review_to_review_md(review_md, pkg, ver, raw_review_out)

                if review.returncode != 0:
                    console.write(f"  ! Review failed for {pkg}@{ver}")
                    failures += 1
                    continue

    if failures > 0:
        console.write(f"::error ::Completed with {failures} failure(s).")
        raise SystemExit(1)

    console.write("::notice title=PASS ::Completed successfully.")
    raise SystemExit(0)


class PrMeta:
    def __init__(self, base_url: str, head_url: str) -> None:
        self.base_url = base_url
        self.head_url = head_url


class Console:
    @contextmanager
    def group(self, title: str, *, stderr: bool = True):
        self.write(f"::group::{title}") if stderr else self.write_stdout(f"::group::{title}")
        try:
            yield
        finally:
            self.write("::endgroup::") if stderr else self.write_stdout("::endgroup::")

    def write(self, message: str) -> None:
        print(message, file=sys.stderr)

    def write_stdout(self, message: str) -> None:
        print(message, file=sys.stdout)


def parse_workspace_release(workspace: Path, package_name: str) -> dict[str, str] | None:
    try:
        with workspace.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    packages = data.get("packages", {})
    package = packages.get(package_name)
    if not isinstance(package, dict):
        return None

    releases = package.get("releases", [])
    newest = newest_workspace_release(releases)
    if newest is None:
        return None

    return {
        "url": str(newest.get("url") or ""),
        "version": str(newest.get("version") or ""),
    }


def newest_workspace_release(releases: list[dict]) -> dict | None:
    candidates = [
        release
        for release in releases
        if isinstance(release, dict) and release.get("url")
    ]
    if not candidates:
        return None

    return max(candidates, key=lambda release: str(release.get("date", "")))


def inspect_registry_package(
    package: dict[str, object],
    package_name: str,
    console: Console,
) -> tuple[bool, str]:
    if package is None:
        console.write(
            f"::warning ::Unable to inspect registry metadata for {package_name}; "
            "skipping repo checks."
        )
        return False, ""

    repo = package.get("details", "")
    tags_mode = is_tags_mode(package)
    if tags_mode and not repo:
        console.write(
            "::warning title=CHECK ::Package appears to be in tags mode, "
            "but no repository URL was found; skipping repo tag checks."
        )

    return tags_mode, repo


def load_registry_packages(registry_file: Path) -> dict[str, dict[str, object]]:
    with registry_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return {package["name"]: package for package in data["packages"]}


def is_tags_mode(package_definition: dict[str, object]) -> bool:
    releases = package_definition.get("releases", [])
    for release in releases:
        if any(key in release for key in ("asset", "url", "branch")):
            return False

    return True


def generate_registry(crawler_repo: Path, registry_url: str, output: Path) -> bool:
    proc = run(
        "uv",
        "run",
        "-m",
        "scripts.generate_registry",
        "-c",
        registry_url,
        "-o",
        str(output),
        cwd=crawler_repo,
        check=False,
    )
    return proc.returncode == 0


def unzip_release(
    zipfile_path: Path,
    workdir: Path,
    pkg: str,
    ver: str,
    console: Console,
) -> Path | None:
    if shutil.which("unzip"):
        unzip = run(
            "unzip",
            "-q",
            "-o",
            str(zipfile_path),
            "-d",
            str(workdir),
            check=False,
        )
        if unzip.returncode != 0:
            console.write(f"::error  ::! Unzip failed for {pkg}@{ver}")
            return None
    else:
        console.write("::notice ::unzip not available; falling back to use Python.")
        try:
            with zipfile.ZipFile(zipfile_path) as zf:
                zf.extractall(workdir)
        except Exception:
            console.write(f"::error  ::! Unzip failed for {pkg}@{ver} (Python)")
            return None

    extracted_entries = [p for p in workdir.iterdir()]
    extracted_dirs = [p for p in extracted_entries if p.is_dir()]
    extracted_files = [p for p in extracted_entries if p.is_file()]

    if len(extracted_dirs) == 1 and not extracted_files:
        return extracted_dirs[0]

    console.write(
        f"::notice ::Using flat archive root for {pkg}@{ver} "
        f"({len(extracted_dirs)} dir(s), {len(extracted_files)} file(s))."
    )
    return workdir


def run_sh(
    command: str,
    *,
    cwd: Path | None = None,
    capture_output: bool = False,
    stdout=None,
    stderr=None,
    check: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess:
    return run(
        *shlex.split(command),
        cwd=cwd,
        capture_output=capture_output,
        stdout=stdout,
        stderr=stderr,
        check=check,
        text=text,
    )


def run(
    *args: str,
    cwd: Path | None = None,
    capture_output: bool = False,
    stdout=None,
    stderr=None,
    check: bool = True,
    text: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    kwargs: dict[str, object] = {
        "cwd": str(cwd) if cwd else None,
        "text": text,
    }
    if capture_output:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    else:
        if stdout is not None:
            kwargs["stdout"] = stdout
        if stderr is not None:
            kwargs["stderr"] = stderr

    command = list(args)

    if env is not None:
        run_env = dict(env)
    else:
        run_env = None

    if command and Path(command[0]).name == "uv":
        base_env = os.environ.copy()
        base_env.pop("VIRTUAL_ENV", None)
        if run_env is not None:
            base_env.update(run_env)
        run_env = base_env

    if run_env is not None:
        kwargs["env"] = run_env

    proc = subprocess.run(command, **kwargs)
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(command)}")
    return proc


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def init_review_md(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Package Review\n\n", encoding="utf-8")


def append_changes_to_review_md(path: Path, changes_line: str) -> None:
    prefix = "::notice title=CHANGES ::"
    if not changes_line.startswith(prefix):
        return
    msg = changes_line[len(prefix):]
    with path.open("a", encoding="utf-8") as f:
        f.write(f"## Channel Diff\n\n{msg}\n\n")


def append_package_review_to_review_md(
    path: Path,
    package: str,
    version: str,
    raw_review: Path,
) -> None:
    raw = raw_review.read_text(encoding="utf-8", errors="replace")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"## Review for {package} {version}\n\n")
        f.write("```text\n")
        f.write(raw)
        if not raw.endswith("\n"):
            f.write("\n")
        f.write("```\n\n")


def setup_thecrawl(src: str, target: Path, console: Console) -> Path:
    if not src:
        src = "https://github.com/packagecontrol/thecrawl"

    if re.match(r"^(https?://|git@)", src):
        url_base = src
        ref = ""
        if re.match(r"^https?://.+@.+$", url_base):
            url_base, ref = url_base.rsplit("@", 1)

        if (target / ".git").is_dir():
            run("git", "-C", str(target), "remote", "set-url", "origin", url_base, check=False)
            if ref:
                console.write(f"Checking out thecrawl ref '{ref}' in {target}")
                run("git", "-C", str(target), "fetch", "--depth", "1", "origin", ref)
                run("git", "-C", str(target), "checkout", "-q", "FETCH_HEAD")
            return target

        if ref:
            console.write(f"Cloning thecrawl {url_base} at ref '{ref}' into {target}")
            run("git", "init", "-q", str(target))
            run("git", "-C", str(target), "remote", "add", "origin", url_base)
            run("git", "-C", str(target), "fetch", "--depth", "1", "origin", ref)
            run("git", "-C", str(target), "checkout", "-q", "FETCH_HEAD")
        else:
            console.write(f"Cloning thecrawl from {url_base} into {target}")
            run("git", "clone", "--depth", "1", url_base, str(target))
        return target

    if not Path(src).is_dir():
        raise RuntimeError("Error: could not find or clone thecrawl")
    return Path(src)


def fetch_pr_metadata(pr_url: str, rel_path: str, console: Console) -> PrMeta:
    m = re.match(r"^https?://[^/]+/([^/]+)/([^/]+)/pull/\d+", pr_url)
    if not m:
        raise RuntimeError(f"Error: invalid PR URL: {pr_url}")
    base_nwo = f"{m.group(1)}/{m.group(2)}"

    view = run(
        "gh",
        "pr",
        "view",
        pr_url,
        "--json",
        "headRepository,baseRefOid,headRefOid",
        capture_output=True,
        check=False,
    )
    if view.returncode != 0:
        raise RuntimeError("Error: failed to resolve PR details via gh")

    try:
        payload = json.loads(view.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Error: invalid gh output: {exc}") from exc

    head_repo = payload.get("headRepository") or {}
    head_nwo = head_repo.get("nameWithOwner") or base_nwo
    base_sha = payload.get("baseRefOid") or ""
    head_sha = payload.get("headRefOid") or ""

    if not base_nwo or not base_sha or not head_sha:
        console.write("Error: failed to resolve PR details via gh")
        console.write(f"  PR:        {pr_url}")
        console.write(f"  base nwo:  {base_nwo or '<empty>'}")
        console.write(f"  base sha:  {base_sha or '<empty>'}")
        console.write(f"  head nwo:  {head_nwo or '<empty>'} (may match base)")
        console.write(f"  head sha:  {head_sha or '<empty>'}")
        console.write("Hint:")
        console.write(
            "  - Commands used: 'gh pr view <url> --json "
            "baseRefOid,headRefOid,headRepository'"
        )
        raise RuntimeError("Error: failed to resolve PR details via gh")

    base_ref_sha = base_sha
    merge_base_sha = resolve_merge_base(base_nwo, base_sha, head_nwo, head_sha)
    if merge_base_sha:
        base_sha = merge_base_sha
        console.write(f"Merge base SHA: {merge_base_sha}")
        if base_ref_sha != merge_base_sha:
            console.write(f"Base ref SHA:   {base_ref_sha}")

    base_url = f"https://raw.githubusercontent.com/{base_nwo}/{base_sha}/{rel_path}"
    head_url = f"https://raw.githubusercontent.com/{head_nwo}/{head_sha}/{rel_path}"
    return PrMeta(base_url, head_url)


def resolve_merge_base(base_nwo: str, base_sha: str, head_nwo: str, head_sha: str) -> str:
    head_ref = head_sha
    if head_nwo != base_nwo:
        head_owner = head_nwo.split("/", 1)[0]
        head_ref = f"{head_owner}:{head_sha}"

    compare = run(
        "gh",
        "api",
        f"repos/{base_nwo}/compare/{base_sha}...{head_ref}",
        capture_output=True,
        check=False,
    )
    if compare.returncode != 0:
        return ""

    try:
        payload = json.loads(compare.stdout)
    except json.JSONDecodeError:
        return ""

    merge = payload.get("merge_base_commit") or {}
    sha = merge.get("sha")
    return sha if isinstance(sha, str) else ""


def download_zip(url: str, dest: Path, console: Console) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = Path(str(dest) + ".part")
    if part.exists():
        part.unlink()
    if dest.exists():
        dest.unlink()

    curl = run(
        "curl",
        "-fSL",
        "--retry",
        "3",
        "--retry-all-errors",
        "--connect-timeout",
        "15",
        "--max-time",
        "600",
        "-o",
        str(part),
        url,
        check=False,
    )
    if curl.returncode == 0:
        part.replace(dest)
        return True

    if part.exists():
        part.unlink()

    m = re.match(r"^https://codeload\.github\.com/([^/]+)/([^/]+)/zip/(.+)$", url)
    if not m:
        return False

    owner, repo, ref = m.group(1), m.group(2), m.group(3)
    console.write(f"    curl failed; using gh api zipball for {owner}/{repo}@{ref}")
    with part.open("wb") as f:
        gh = run(
            "gh",
            "api",
            "-H",
            "Accept: application/octet-stream",
            f"repos/{owner}/{repo}/zipball/{ref}",
            stdout=f,
            check=False,
            text=False,
        )
    if gh.returncode == 0:
        part.replace(dest)
        return True

    if part.exists():
        part.unlink()
    return False


def emit_review_annotations(raw_review_out: Path, console: Console) -> None:
    mode = ""
    with raw_review_out.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.rstrip("\n")
            if re.match(r"^(Reporting )?[0-9]+ failures:", stripped):
                mode = "error"
                continue
            if re.match(r"^(Reporting )?[0-9]+ warnings:", stripped):
                mode = "warning"
                continue
            if re.match(r"^(Reporting )?[0-9]+ notices:", stripped):
                mode = "notice"
                continue
            if stripped.startswith("- ") and mode:
                console.write_stdout(f"::{mode} title=CHECK ::{stripped[2:]}")
                continue
            if stripped.startswith("    ") and mode:
                console.write_stdout(stripped)
                continue

            mode = ""
            console.write_stdout(stripped)


if __name__ == "__main__":
    main()

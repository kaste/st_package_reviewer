#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<EOF
Usage: $0 --pr <pr_url> [--file <path>] [--thecrawl <path-or-url[@ref]>]

Arguments:
  --pr        GitHub Pull Request URL (e.g. https://github.com/wbond/package_control_channel/pull/9236)
  --file      Path within the repo to the channel JSON (default: repository.json)
  --thecrawl  Path to local thecrawl repo or URL to clone (supports @ref to pin, default: https://github.com/packagecontrol/thecrawl)

Requires: gh, uv
EOF
}

PR_URL=""
REL_PATH="repository.json"
THECRAWL="https://github.com/packagecontrol/thecrawl"
REVIEW_MD="${GITHUB_WORKSPACE:-$PWD}/review.md"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr)
      PR_URL="$2"; shift 2;;
    --file)
      REL_PATH="$2"; shift 2;;
    --thecrawl)
      THECRAWL="$2"; shift 2;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown argument: $1" >&2; usage; exit 2;;
  esac
done

if [[ -z "$PR_URL" ]]; then
  echo "Error: --pr is required" >&2; usage; exit 2
fi

# Normalize relative path (strip leading ./)
REL_PATH="${REL_PATH#./}"

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: gh (GitHub CLI) is required" >&2; exit 2
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is required" >&2; exit 2
fi

# When this action is downloaded by GitHub, it does not include the .git folder.
# Our project uses hatch-vcs/setuptools-scm for dynamic versioning, which needs VCS metadata.
# Provide a fallback version so the build backend can proceed when running under Actions.
# Project-specific env var recommended by setuptools-scm
export SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ST_PACKAGE_REVIEWER=${SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ST_PACKAGE_REVIEWER:-0.0.0}
# Generic fallback for environments that ignore the project-specific variant
export SETUPTOOLS_SCM_PRETEND_VERSION=${SETUPTOOLS_SCM_PRETEND_VERSION:-$SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ST_PACKAGE_REVIEWER}


init_review_md() {
  : >"$REVIEW_MD"
  cat >>"$REVIEW_MD" <<'MD'
# Package Review

MD
}

append_changes_to_review_md() {
  local changes_line="$1"
  local msg="${changes_line#::notice title=CHANGES ::}"
  if [[ -z "$changes_line" || "$msg" == "$changes_line" ]]; then
    return 0
  fi
  {
    echo "## Channel Diff"
    echo
    echo "$msg"
    echo
  } >>"$REVIEW_MD"
}

append_package_review_to_review_md() {
  local pkg="$1" ver="$2" raw_path="$3"
  {
    echo "## Review for $pkg $ver"
    echo
    echo '```text'
    cat "$raw_path"
    echo '```'
    echo
  } >>"$REVIEW_MD"
}

init_review_md


setup_thecrawl() {
  local src="$1"; shift || true
  [[ -z "$src" ]] && src="https://github.com/packagecontrol/thecrawl"
  local target="${GITHUB_WORKSPACE:-$PWD}/.thecrawl"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --target) target="$2"; shift 2;;
      *) echo "Unknown setup_thecrawl arg: $1" >&2; return 2;;
    esac
  done

  if [[ "$src" =~ ^https?:// || "$src" =~ ^git@ ]]; then
    local url_base="$src" ref=""
    if [[ "$url_base" =~ ^https?://.+@.+$ ]]; then
      ref="${url_base##*@}"
      url_base="${url_base%*@$ref}"
    fi
    if [[ -d "$target/.git" ]]; then
      git -C "$target" remote set-url origin "$url_base" >/dev/null 2>&1 || true
      if [[ -n "$ref" ]]; then
        echo "Checking out thecrawl ref '$ref' in $target" >&2
        git -C "$target" fetch --depth 1 origin "$ref" >&2
        git -C "$target" checkout -q FETCH_HEAD >&2
      fi
      echo "$target"; return 0
    fi
    if [[ -n "$ref" ]]; then
      echo "Cloning thecrawl $url_base at ref '$ref' into $target" >&2
      git init -q "$target" >&2
      git -C "$target" remote add origin "$url_base" >&2
      git -C "$target" fetch --depth 1 origin "$ref" >&2
      git -C "$target" checkout -q FETCH_HEAD >&2
    else
      echo "Cloning thecrawl from $url_base into $target" >&2
      git clone --depth 1 "$url_base" "$target" >&2
    fi
    echo "$target"; return 0
  fi
  echo "$src"; return 0
}


fetch_pr_metadata() {
  local pr_url="$1"
  BASE_NWO=$(echo "$pr_url" | awk -F/ '{print $4"/"$5}')
  IFS=: read -r HEAD_NWO BASE_SHA HEAD_SHA < <(
    gh pr view "$pr_url" \
      --json headRepository,baseRefOid,headRefOid \
      -q '[.headRepository.nameWithOwner // "", .baseRefOid, .headRefOid] | join(":")'
  )
  if [[ -z "$BASE_NWO" || -z "$BASE_SHA" || -z "$HEAD_SHA" ]]; then
    echo "Error: failed to resolve PR details via gh" >&2
    echo "  PR:        $pr_url" >&2
    echo "  base nwo:  ${BASE_NWO:-<empty>}" >&2
    echo "  base sha:  ${BASE_SHA:-<empty>}" >&2
    echo "  head nwo:  ${HEAD_NWO:-<empty>} (may match base)" >&2
    echo "  head sha:  ${HEAD_SHA:-<empty>}" >&2
    echo "Hint:" >&2
    echo "  - Commands used: 'gh pr view <url> --json baseRefOid,headRefOid,headRepository'" >&2
    return 2
  fi
  if [[ -z "$HEAD_NWO" ]]; then
    HEAD_NWO="$BASE_NWO"
  fi
  local base_ref_sha="$BASE_SHA"
  local merge_base_sha=""
  merge_base_sha=$(resolve_merge_base "$BASE_NWO" "$BASE_SHA" "$HEAD_NWO" "$HEAD_SHA" || true)
  if [[ -n "$merge_base_sha" ]]; then
    BASE_SHA="$merge_base_sha"
    echo "Merge base SHA: $merge_base_sha" >&2
    if [[ "$base_ref_sha" != "$merge_base_sha" ]]; then
      echo "Base ref SHA:   $base_ref_sha" >&2
    fi
  fi
  BASE_URL="https://raw.githubusercontent.com/${BASE_NWO}/${BASE_SHA}/${REL_PATH}"
  HEAD_URL="https://raw.githubusercontent.com/${HEAD_NWO}/${HEAD_SHA}/${REL_PATH}"
  echo "Base URL:   $BASE_URL" >&2
  echo "Target URL: $HEAD_URL" >&2
}


resolve_merge_base() {
  local base_nwo="$1" base_sha="$2" head_nwo="$3" head_sha="$4"
  local head_ref="$head_sha"
  if [[ "$head_nwo" != "$base_nwo" ]]; then
    local head_owner="${head_nwo%%/*}"
    head_ref="${head_owner}:${head_sha}"
  fi
  gh api "repos/${base_nwo}/compare/${base_sha}...${head_ref}" \
    -q '.merge_base_commit.sha'
}


# Robust ZIP downloader with fallback to gh for GitHub zipball URLs
download_zip() {
  local url="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  rm -f "$dest.part" "$dest"
  # First try curl with retries
  if curl -fSL --retry 3 --retry-all-errors --connect-timeout 15 --max-time 600 \
      -o "$dest.part" "$url"; then
    mv "$dest.part" "$dest"
    return 0
  fi
  rm -f "$dest.part"
  # Fallback for codeload.github.com/<owner>/<repo>/zip/<ref>
  if [[ "$url" =~ ^https://codeload\.github\.com/([^/]+)/([^/]+)/zip/(.+)$ ]]; then
    local owner="${BASH_REMATCH[1]}" repo="${BASH_REMATCH[2]}" ref="${BASH_REMATCH[3]}"
    echo "    curl failed; using gh api zipball for $owner/$repo@$ref" >&2
    if gh api -H "Accept: application/octet-stream" \
        "repos/${owner}/${repo}/zipball/${ref}" > "$dest.part"; then
      mv "$dest.part" "$dest"
      return 0
    fi
    rm -f "$dest.part"
  fi
  return 1
}


echo "::group::Fetching PR metadata"
echo "Resolving PR metadata via gh: $PR_URL" >&2
if ! fetch_pr_metadata "$PR_URL"; then
  echo "::error ::Error: failed to resolve PR details via gh" >&2
  exit 2
fi
echo "::endgroup::"


echo "::group::Getting thecrawl"
CRAWLER_REPO=$(setup_thecrawl "$THECRAWL" --target "${GITHUB_WORKSPACE:-$PWD}/.thecrawl")
if [[ ! -d "$CRAWLER_REPO" ]]; then
  echo "::error ::Error: could not find or clone thecrawl" >&2
  exit 2
fi
echo "Using thecrawl at: $CRAWLER_REPO" >&2
echo "::endgroup::"

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

BASE_REG="$TMPDIR/base_registry.json"
HEAD_REG="$TMPDIR/head_registry.json"

echo "::group::Generating base registry…" >&2
(cd "$CRAWLER_REPO" && uv run -m scripts.generate_registry -c "$BASE_URL" -o "$BASE_REG")
echo "::endgroup::"

echo "::group::Generating target registry…" >&2
(cd "$CRAWLER_REPO" && uv run -m scripts.generate_registry -c "$HEAD_URL" -o "$HEAD_REG")
echo "::endgroup::"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Invoke Python diff to print results and collect changed+added package names
DIFF_STDERR="$TMPDIR/diff_repository.stderr"
PKGS=()
while IFS= read -r -d '' __pkg; do
  PKGS+=("$__pkg")
done < <(python3 "$SCRIPT_DIR/diff_repository.py" --base-file "$BASE_REG" --target-file "$HEAD_REG" -z 2> >(tee "$DIFF_STDERR" >&2))
append_changes_to_review_md "$(grep -m1 '^::notice title=CHANGES ::' "$DIFF_STDERR" 2>/dev/null || true)"

if [[ ${#PKGS[@]} -eq 0 ]]; then
  echo "::notice ::No changed or added packages to crawl." >&2
  {
    echo "## Result"
    echo
    echo "No changed or added packages to review."
    echo
  } >>"$REVIEW_MD"
  exit 0
fi

echo "Crawling ${#PKGS[@]} package(s) from target registry…" >&2

ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
echo "::group::Preparing st_package_reviewer environment" >&2
(cd "$ROOT_DIR" && uv sync --no-dev) >&2
echo "::endgroup::" >&2

failures=0
for pkg in "${PKGS[@]}"; do
  echo "::group::Crawling: $pkg" >&2
  # Use workspace file output for robust parsing
  wsdir="$TMPDIR/workspaces"
  mkdir -p "$wsdir"
  wsfile="$wsdir/${pkg}.json"
  echo "Workspace file is $wsfile" >&2
  set +e
  (cd "$CRAWLER_REPO" && uv run -m scripts.crawl --registry "$HEAD_REG" --workspace "$wsfile" --name "$pkg" 2> >(cat >&2))
  STATUS=$?
  set -e
  if [[ $STATUS -ne 0 || ! -s "$wsfile" ]]; then
    echo "::error ::! Crawl failed for $pkg" >&2
    failures=$((failures+1))
    continue
  fi

  # Extract release URLs (and versions) from workspace
  RELS=()
  while IFS= read -r -d '' __rec; do
    RELS+=("$__rec")
  done < <(python3 "$SCRIPT_DIR/parse_workspace.py" "$wsfile" "$pkg" -z)
  if [[ ${#RELS[@]} -eq 0 ]]; then
    echo "::error  ::! No releases found for $pkg" >&2
    failures=$((failures+1))
    continue
  fi
  echo "::endgroup::"

  i=0
  for rec in "${RELS[@]}"; do
    i=$((i+1))
    url="${rec%%$'\t'*}"
    ver="${rec#*$'\t'}"

    if [[ -z "$url" ]]; then
      echo "::error  ::! Missing release URL for $pkg release #$i" >&2
      failures=$((failures+1))
      continue
    fi

    # if no tab present, ver==url; fix that
    if [[ "$ver" == "$url" ]]; then ver=""; fi
    if [[ -z "$ver" ]]; then
      echo "::warning ::Could not extract a version for $pkg release #$i (url: $url); using r$i" >&2
      ver="r$i"
    fi
    # sanitize for filesystem path
    safe_ver=$(printf '%s' "$ver" | sed 's/[^A-Za-z0-9._-]/_/g')

    workdir="$TMPDIR/review/$pkg/$safe_ver"
    mkdir -p "$workdir"

    zipfile="$workdir/pkg.zip"
    echo "::group::Downloading $pkg-$ver" >&2
    echo "  Downloading release $ver: $url" >&2
    if ! download_zip "$url" "$zipfile"; then
      echo "::error  ::! Download failed for $pkg@$ver" >&2
      failures=$((failures+1))
      continue
    fi

    echo "  Unpacking…" >&2
    # Prefer unzip; fallback to Python zipfile
    if command -v unzip >/dev/null 2>&1; then
      if ! unzip -q -o "$zipfile" -d "$workdir"; then
        echo "::error  ::! Unzip failed for $pkg@$ver" >&2
        failures=$((failures+1))
        continue
      fi
    else
      echo "::notice ::unzip not available; falling back to use Python."
      python3 - "$zipfile" "$workdir" <<'PY'
import sys, zipfile, os
zf = zipfile.ZipFile(sys.argv[1])
zf.extractall(sys.argv[2])
PY
      if [[ $? -ne 0 ]]; then
        echo "::error  ::! Unzip failed for $pkg@$ver (Python)" >&2
        failures=$((failures+1))
        continue
      fi
    fi

    # Determine the top-level extracted directory
    topdir=$(find "$workdir" -mindepth 1 -maxdepth 1 -type d | head -n1)
    if [[ -z "$topdir" ]]; then
      echo "::error  ::! Could not locate extracted folder for $pkg@$ver" >&2
      failures=$((failures+1))
      continue
    fi
    echo "::endgroup::"

    echo "::group::Reviewing $pkg-$safe_ver" >&2
    echo "  Reviewing with st_package_reviewer: $topdir" >&2
    raw_review_out="$workdir/review.txt"
    set +e
    (cd "$ROOT_DIR" && uv run --no-sync st_package_reviewer --compact --package-name "$pkg" "$topdir") >"$raw_review_out" 2>&1
    STATUS=$?
    set -e

    awk '
      /^(Reporting )?[0-9]+ failures:/ { mode = "error";   next }
      /^(Reporting )?[0-9]+ warnings:/ { mode = "warning"; next }
      /^(Reporting )?[0-9]+ notices:/ { mode = "notice"; next }
      /^- / && mode {
        sub(/^- /, "");
        print "::" mode " title=CHECK ::" $0;
        next;
      }
      { mode = ""; print }
    ' <"$raw_review_out"

    append_package_review_to_review_md "$pkg" "$ver" "$raw_review_out"

    if [[ $STATUS -ne 0 ]]; then
      echo "  ! Review failed for $pkg@$ver" >&2
      failures=$((failures+1))
      continue
    fi
    echo "::endgroup::"
  done
done

if [[ $failures -gt 0 ]]; then
  echo "::error ::Completed with $failures failure(s)." >&2
  exit 1
else
  echo "::notice title=PASS ::Completed successfully." >&2
  exit 0
fi

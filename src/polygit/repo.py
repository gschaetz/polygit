import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from .config import HOSTS

_print_lock = threading.Lock()
MAX_WORKERS = 8

# Errors seen when the SSH server drops a connection under concurrent load
# rather than a real failure — safe to retry.
_TRANSIENT_ERR_MARKERS = (
    "kex_exchange_identification",
    "Connection reset by peer",
    "Connection timed out",
    "Could not read from remote repository",
    "early EOF",
    "The remote end hung up unexpectedly",
)


def _pool(jobs=None):
    return ThreadPoolExecutor(max_workers=jobs or MAX_WORKERS)


def _is_transient(stderr):
    return any(marker in stderr for marker in _TRANSIENT_ERR_MARKERS)


def _run_git(args, retries=2, delay=1.5, cleanup=None):
    """Run a git subprocess, retrying on transient SSH/network errors.

    `cleanup`, if given, runs before each retry (e.g. to remove a partial
    clone directory left behind by the failed attempt).
    """
    for attempt in range(retries + 1):
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode == 0 or not _is_transient(result.stderr):
            return result
        if attempt < retries:
            if cleanup:
                cleanup()
            time.sleep(delay * (attempt + 1))
    return result


_USE_COLOR = sys.stdout.isatty()

_G  = "\033[32m" if _USE_COLOR else ""   # green
_R  = "\033[31m" if _USE_COLOR else ""   # red
_C  = "\033[36m" if _USE_COLOR else ""   # cyan
_Y  = "\033[33m" if _USE_COLOR else ""   # yellow
_DIM = "\033[2m" if _USE_COLOR else ""   # dim
_RST = "\033[0m" if _USE_COLOR else ""   # reset

OK   = f"{_G}✓{_RST}"
UPD  = f"{_G}↓{_RST}"
ERR  = f"{_R}✗{_RST}"
WARN = f"{_Y}⚠{_RST}"
NEW  = f"{_C}+{_RST}"


def _emit(lines):
    """Print a block of lines atomically."""
    with _print_lock:
        for line in lines:
            print(line)


def walk(node, prefix):
    """Yield (local_path, remote_path) for every repo in the tree."""
    if node is None:
        yield prefix, prefix
    elif isinstance(node, dict) and set(node.keys()) == {"remote"}:
        yield prefix, node["remote"]
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{prefix}/{key}")


def each_repo(config, base):
    """Yield (platform, local_path, remote_path, dir) for all configured repos."""
    for platform, namespaces in config.items():
        if platform not in HOSTS:
            continue
        for ns_key, ns_value in namespaces.items():
            for local_path, remote_path in walk(ns_value, ns_key):
                yield platform, local_path, remote_path, base / platform / local_path


def each_existing_repo(config, base, only=None):
    """Yield only repos that are already cloned locally.

    If *only* is set, only repos under that platform are yielded. The helper
    is used by :func:`cmd_status`, :func:`cmd_pull` and :func:`cmd_push`.
    """
    for platform, local_path, remote_path, d in each_repo(config, base):
        if only is not None and platform != only:
            continue
        if (d / ".git").exists():
            yield platform, local_path, remote_path, d


def is_dirty(d):
    result = subprocess.run(
        ["git", "-C", str(d), "status", "--porcelain"],
        capture_output=True, text=True
    )
    return bool(result.stdout.strip())


def _commit_and_push(d, label, msg):
    lines = [f"  Committing {label}..."]
    ok, sha, error = _commit_one(d, msg)
    if not ok:
        lines.append(f"{ERR} {label}: {error}")
        _emit(lines)
        return
    result = _run_git(["git", "-C", str(d), "push"])
    if result.returncode != 0:
        lines.append(f"{ERR} {label}: push failed — {result.stderr.strip().splitlines()[0]}")
    else:
        lines.append(f"{UPD} {label}: pushed")
    _emit(lines)


def _commit_one(d, msg):
    """Run git add -A then git commit -m msg, returning (ok, sha, error)."""
    add_result = subprocess.run(
        ["git", "-C", str(d), "add", "-A"],
        capture_output=True, text=True
    )
    if add_result.returncode != 0:
        out = add_result.stderr.strip() or add_result.stdout.strip()
        return False, None, f"add failed — {out.splitlines()[-1] if out else 'unknown error'}"
    commit_result = subprocess.run(
        ["git", "-C", str(d), "commit", "-m", msg],
        capture_output=True, text=True
    )
    if commit_result.returncode != 0:
        out = commit_result.stderr.strip() or commit_result.stdout.strip()
        msg_line = out.splitlines()[-1] if out else "unknown error"
        return False, None, f"commit failed — {msg_line}"
    sha_result = subprocess.run(
        ["git", "-C", str(d), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True
    )
    sha = sha_result.stdout.strip() if sha_result.returncode == 0 else None
    return True, sha, None


def _wip_message():
    """Return a WIP commit message with timestamp."""
    return f"WIP {datetime.now().strftime('%Y-%m-%d %H:%M')}"


def _sync_one(platform, local_path, remote_path, d):
    url = f"{HOSTS[platform]}:{remote_path}.git"
    label = f"{platform}/{local_path}"
    if (d / ".git").exists():
        result = _run_git(["git", "-C", str(d), "fetch", "--all", "-q"])
        if result.returncode != 0:
            lines = [f"{ERR} {label}: {result.stderr.strip().splitlines()[0]}"]
        else:
            lines = [f"{OK} {_DIM}{label}{_RST}"]
    else:
        d.parent.mkdir(parents=True, exist_ok=True)
        result = _run_git(
            ["git", "clone", url, str(d)],
            cleanup=lambda: shutil.rmtree(d, ignore_errors=True),
        )
        if result.returncode != 0:
            lines = [f"{ERR} {label}: {result.stderr.strip().splitlines()[0]}"]
        else:
            lines = [f"{NEW} {label}: cloned"]
    _emit(lines)


def _pull_dry_run(label, d):
    """Report ahead/behind vs. upstream without touching the repo."""
    counts = subprocess.run(
        ["git", "-C", str(d), "rev-list", "--left-right", "--count", "HEAD...@{u}"],
        capture_output=True, text=True,
    )
    if counts.returncode != 0:
        return [f"{WARN} {label}: no upstream branch set"]
    ahead, behind = counts.stdout.split()
    if ahead == "0" and behind == "0":
        return [f"{OK} {_DIM}{label}{_RST}"]
    return [f"{UPD} {label}: {ahead} ahead, {behind} behind"]


def _pull_one(platform, local_path, d, dry_run=False):
    label = f"{platform}/{local_path}"
    if dry_run:
        _emit(_pull_dry_run(label, d))
        return
    lines = []
    stashed = False
    if is_dirty(d):
        subprocess.run(["git", "-C", str(d), "stash"], capture_output=True)
        stashed = True
    result = _run_git(["git", "-C", str(d), "pull", "--rebase"])
    if result.returncode != 0:
        err = result.stderr.strip()
        if "no tracking information" in err or "no upstream" in err.lower():
            lines.append(f"{WARN} {label}: no upstream branch set")
        else:
            lines.append(f"{ERR} {label}: {err.splitlines()[0]}")
    elif result.stdout.strip() and "up to date" not in result.stdout.lower():
        lines.append(f"{UPD} {label}:")
        for ln in result.stdout.strip().splitlines():
            lines.append(f"   {ln}")
    else:
        lines.append(f"{OK} {_DIM}{label}{_RST}")
    if stashed:
        pop = subprocess.run(
            ["git", "-C", str(d), "stash", "pop"],
            capture_output=True, text=True
        )
        if pop.returncode != 0:
            lines.append(f"  {_Y}warning:{_RST} stash pop had conflicts in {label}")
        else:
            lines.append(f"  stash restored")
    _emit(lines)


def cmd_sync(config, base, jobs=None):
    repos = list(each_repo(config, base))
    with _pool(jobs) as pool:
        futures = [pool.submit(_sync_one, p, lp, rp, d) for p, lp, rp, d in repos]
        for f in as_completed(futures):
            f.result()


def cmd_status(config, base, json_output=False, only=None, jobs=None):
    results = []

    def _check(platform, local_path, d):
        result = subprocess.run(
            ["git", "-C", str(d), "status", "--short"],
            capture_output=True, text=True
        )
        return platform, local_path, result.stdout.strip()

    repos = list(each_existing_repo(config, base, only=only))
    with _pool(jobs) as pool:
        futures = {pool.submit(_check, p, lp, d): (p, lp) for p, lp, _, d in repos}
        for f in as_completed(futures):
            results.append(f.result())

    if json_output:
        entries = [
            {"platform": platform, "path": local_path, "changed_files": len(output.splitlines())}
            for platform, local_path, output in sorted(results)
            if output
        ]
        print(json.dumps(entries))
        return

    found_dirty = False
    for platform, local_path, output in sorted(results):
        if output:
            found_dirty = True
            print(f"\n{_Y}~{_RST} {platform}/{local_path}:")
            for line in output.splitlines():
                print(f"  {line}")
    if not found_dirty:
        print(f"{OK} All repos are clean.")


def cmd_pull(config, base, dry_run=False, only=None, jobs=None):
    repos = list(each_existing_repo(config, base, only=only))
    with _pool(jobs) as pool:
        futures = [pool.submit(_pull_one, p, lp, d, dry_run) for p, lp, _, d in repos]
        for f in as_completed(futures):
            f.result()


def cmd_push(config, base, mode="interactive", dry_run=False, only=None, jobs=None):
    dirty = [
        (platform, local_path, d)
        for platform, local_path, _, d in each_existing_repo(config, base, only=only)
        if is_dirty(d)
    ]

    if not dirty:
        print("No dirty repos to commit.")
        return

    if dry_run:
        print("Would commit and push the following dirty repos:")
        for platform, local_path, _ in dirty:
            print(f"  {platform}/{local_path}")
        return

    if mode == "wip":
        msg = _wip_message()
        with _pool(jobs) as pool:
            futures = [pool.submit(_commit_and_push, d, f"{p}/{lp}", msg) for p, lp, d in dirty]
            for f in as_completed(futures):
                f.result()

    elif mode == "all":
        print("Dirty repos:")
        for platform, local_path, _ in dirty:
            print(f"  {platform}/{local_path}")
        msg = input("\nCommit message for all repos (blank to abort): ").strip()
        if not msg:
            print("Aborted.")
            return
        with _pool(jobs) as pool:
            futures = [pool.submit(_commit_and_push, d, f"{p}/{lp}", msg) for p, lp, d in dirty]
            for f in as_completed(futures):
                f.result()

    else:  # interactive — must stay sequential for user input
        for platform, local_path, d in dirty:
            label = f"{platform}/{local_path}"
            status = subprocess.run(
                ["git", "-C", str(d), "status", "--short"],
                capture_output=True, text=True
            ).stdout.strip()
            print(f"\n{label}:")
            for line in status.splitlines():
                print(f"  {line}")
            msg = input("  Commit message (blank to skip): ").strip()
            if not msg:
                print("  Skipped.")
                continue
            _commit_and_push(d, label, msg)


def cmd_commit(config, base, mode="interactive", dry_run=False, only=None, jobs=None, json_output=False):
    """Commit dirty repos without pushing."""
    dirty = [
        (platform, local_path, d)
        for platform, local_path, _, d in each_existing_repo(config, base, only=only)
        if is_dirty(d)
    ]

    if not dirty:
        if json_output:
            print(json.dumps([]))
        else:
            print("No dirty repos to commit.")
        return

    if dry_run:
        if json_output:
            print(json.dumps([
                {"platform": p, "path": lp, "status": "planned", "message": None, "sha": None, "error": None}
                for p, lp, _ in dirty
            ]))
        else:
            print("Would commit the following dirty repos:")
            for platform, local_path, _ in dirty:
                print(f"  {platform}/{local_path}")
        return

    results = []
    results_lock = threading.Lock()

    def _commit_task(platform, local_path, d, msg):
        label = f"{platform}/{local_path}"
        ok, sha, error = _commit_one(d, msg)
        entry = {
            "platform": platform,
            "path": local_path,
            "status": "committed" if ok else "failed",
            "message": msg if ok else None,
            "sha": sha,
            "error": None if ok else error,
        }
        with results_lock:
            results.append(entry)
        if not json_output:
            if not ok:
                print(f"{ERR} {label}: {error}")
            else:
                print(f"{OK} {label}: committed {sha}")

    if mode == "wip":
        msg = _wip_message()
        with _pool(jobs) as pool:
            futures = [pool.submit(_commit_task, p, lp, d, msg) for p, lp, d in dirty]
            for f in as_completed(futures):
                f.result()

    elif mode == "all":
        if not json_output:
            print("Dirty repos:")
            for platform, local_path, _ in dirty:
                print(f"  {platform}/{local_path}")
        prompt = "\nCommit message for all repos (blank to abort): "
        if json_output:
            # stdout is reserved for the JSON result
            print(prompt, end="", file=sys.stderr, flush=True)
            msg = input().strip()
        else:
            msg = input(prompt).strip()
        if not msg:
            if json_output:
                print(json.dumps([]))
            else:
                print("Aborted.")
            return
        with _pool(jobs) as pool:
            futures = [pool.submit(_commit_task, p, lp, d, msg) for p, lp, d in dirty]
            for f in as_completed(futures):
                f.result()

    else:  # interactive — must stay sequential for user input (never --json)
        for platform, local_path, d in dirty:
            label = f"{platform}/{local_path}"
            status = subprocess.run(
                ["git", "-C", str(d), "status", "--short"],
                capture_output=True, text=True
            ).stdout.strip()
            print(f"\n{label}:")
            for line in status.splitlines():
                print(f"  {line}")
            msg = input("  Commit message (blank to skip): ").strip()
            if not msg:
                print("  Skipped.")
                continue
            _commit_task(platform, local_path, d, msg)

    if json_output:
        results.sort(key=lambda r: (r["platform"], r["path"]))
        print(json.dumps(results))


def _merge_precheck(d, target):
    """Return (status, detail) if the repo should not be merged, else None."""
    branch = subprocess.run(
        ["git", "-C", str(d), "symbolic-ref", "--short", "-q", "HEAD"],
        capture_output=True, text=True
    )
    if branch.returncode != 0:
        return "skipped", "detached HEAD"
    current = branch.stdout.strip()

    exists = subprocess.run(
        ["git", "-C", str(d), "rev-parse", "--verify", "-q", f"refs/heads/{target}"],
        capture_output=True, text=True
    )
    if exists.returncode != 0:
        return "skipped", f"target branch '{target}' not found"

    if target == current:
        return "up-to-date", ""

    in_progress = subprocess.run(
        ["git", "-C", str(d), "rev-parse", "--verify", "-q", "MERGE_HEAD"],
        capture_output=True, text=True
    )
    if in_progress.returncode == 0:
        return "skipped", "merge in progress"

    if is_dirty(d):
        return "skipped", "dirty working tree"

    contained = subprocess.run(
        ["git", "-C", str(d), "merge-base", "--is-ancestor", f"refs/heads/{target}", "HEAD"],
        capture_output=True, text=True
    )
    if contained.returncode == 0:
        return "up-to-date", ""
    return None


def _merge_one(d, target, no_ff=False, squash=False):
    """Merge target into the current branch of the repo at d.

    Returns (status, detail, conflict_files). Status is one of merged,
    up-to-date, conflict, skipped, failed.
    """
    skip = _merge_precheck(d, target)
    if skip:
        return skip[0], skip[1], []

    head_before = _git_out(d, "rev-parse", "HEAD")

    cmd = ["git", "-C", str(d), "merge"]
    if squash:
        cmd.append("--squash")
    if no_ff:
        cmd.append("--no-ff")
    cmd.append(target)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        unmerged = (_git_out(d, "diff", "--name-only", "--diff-filter=U") or "").splitlines()
        if unmerged:
            return "conflict", f"{len(unmerged)} file(s)", unmerged
        out = (result.stderr.strip() or result.stdout.strip()).splitlines()
        return "failed", out[-1] if out else "unknown error", []

    if squash:
        return "merged", "squashed (staged)", []

    head_after = _git_out(d, "rev-parse", "HEAD")
    if head_after == head_before:
        return "up-to-date", "", []
    parents = (_git_out(d, "rev-list", "--parents", "-n", "1", "HEAD") or "").split()
    if len(parents) > 2:
        return "merged", f"commit {head_after[:7]}", []
    return "merged", "fast-forward", []


def _merge_line(status, detail):
    if status == "up-to-date":
        return "up to date"
    if status == "planned":
        return "would merge"
    if status == "merged":
        return detail if detail.startswith("squashed") else f"merged ({detail})"
    return f"{status}: {detail}"


def cmd_merge(config, base, target, no_ff=False, squash=False, dry_run=False, only=None, jobs=None, json_output=False):
    """Merge a local target branch into each repo's current branch."""
    repos = list(each_existing_repo(config, base, only=only))
    strategy = "squash" if squash else ("no-ff" if no_ff else "default")
    results = []
    results_lock = threading.Lock()

    def _merge_task(platform, local_path, d):
        if dry_run:
            status, detail = _merge_precheck(d, target) or ("planned", "")
            conflict_files = []
        else:
            status, detail, conflict_files = _merge_one(d, target, no_ff=no_ff, squash=squash)
        entry = {
            "platform": platform,
            "path": local_path,
            "status": status,
            "strategy": strategy,
            "detail": detail or None,
        }
        if status == "conflict":
            entry["conflict_files"] = conflict_files
        with results_lock:
            results.append(entry)
        if not json_output:
            symbol = {"merged": UPD, "up-to-date": OK, "planned": OK, "conflict": ERR, "failed": ERR}.get(status, WARN)
            _emit([f"{symbol} {platform}/{local_path}: {_merge_line(status, detail)}"])

    with _pool(jobs) as pool:
        futures = [pool.submit(_merge_task, p, lp, d) for p, lp, _, d in repos]
        for f in as_completed(futures):
            f.result()

    if json_output:
        results.sort(key=lambda r: (r["platform"], r["path"]))
        print(json.dumps(results))
    elif not repos:
        print("No cloned repos found.")


AHEAD = f"{_Y}↑{_RST}"


def _git_out(d, *args):
    result = subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True)
    return result.stdout.strip("\n") if result.returncode == 0 else None


def _get_branch_info(d):
    """Return (branch, upstream, ahead, behind, state) for a repo.

    state is one of "tracking", "none" (no upstream configured), "gone"
    (upstream configured but deleted on the remote) or "detached" (branch
    then holds the short SHA). Reads local refs only, so counts reflect the
    last fetch.
    """
    out = _git_out(
        d, "for-each-ref", "refs/heads",
        "--format=%(HEAD)%09%(refname:short)%09%(upstream:short)%09%(upstream:track,nobracket)",
    )
    for line in (out or "").splitlines():
        head, branch, upstream, track = line.split("\t")
        if head != "*":
            continue
        if not upstream:
            return branch, None, 0, 0, "none"
        if track == "gone":
            return branch, upstream, 0, 0, "gone"
        ahead = re.search(r"ahead (\d+)", track)
        behind = re.search(r"behind (\d+)", track)
        return branch, upstream, int(ahead[1]) if ahead else 0, int(behind[1]) if behind else 0, "tracking"

    # No local branch is checked out: unborn branch (empty repo) or detached HEAD.
    branch = _git_out(d, "symbolic-ref", "--short", "-q", "HEAD")
    if branch:
        return branch, None, 0, 0, "none"
    return _git_out(d, "rev-parse", "--short", "HEAD") or "?", None, 0, 0, "detached"


def _format_branch_info(platform, local_path, branch, upstream, ahead, behind, state):
    """Format branch info for a single repo."""
    label = f"{platform}/{local_path}"
    if state == "detached":
        return f"{WARN} {label}: detached HEAD at {branch}"
    if state == "none":
        return f"{_Y}~{_RST} {label}: {branch} (no upstream)"
    if state == "gone":
        return f"{WARN} {label}: {branch} -> {upstream} (upstream gone)"

    if ahead == 0 and behind == 0:
        return f"{OK} {_DIM}{label}: {branch} -> {upstream} (up to date){_RST}"
    if ahead and behind:
        return f"{WARN} {label}: {branch} -> {upstream} ({ahead} ahead, {behind} behind)"
    if ahead:
        return f"{AHEAD} {label}: {branch} -> {upstream} ({ahead} ahead)"
    return f"{UPD} {label}: {branch} -> {upstream} ({behind} behind)"


def cmd_branches(config, base, json_output=False, only=None, jobs=None):
    """Show current branch and tracking status for each repo (as of the last fetch)."""
    repos = list(each_existing_repo(config, base, only=only))

    if not repos:
        print("[]" if json_output else "No cloned repos found.")
        return

    results = []

    def _check(platform, local_path, d):
        return (platform, local_path, *_get_branch_info(d))

    with _pool(jobs) as pool:
        futures = {pool.submit(_check, p, lp, d): (p, lp) for p, lp, _, d in repos}
        for f in as_completed(futures):
            results.append(f.result())

    results.sort()

    if json_output:
        entries = [
            {
                "platform": platform,
                "path": local_path,
                "branch": None if state == "detached" else branch,
                "sha": branch if state == "detached" else None,
                "upstream": upstream,
                "ahead": ahead,
                "behind": behind,
                "state": state,
            }
            for platform, local_path, branch, upstream, ahead, behind, state in results
        ]
        print(json.dumps(entries))
        return

    for result in results:
        print(_format_branch_info(*result))


def _parse_remote_url(remote_url):
    """Return (host, path) from an SSH or HTTPS remote URL.

    path keeps subgroups and drops a trailing ".git". Returns (None, None) on
    unparseable input.
    """
    remote_url = (remote_url or "").strip()
    if not remote_url:
        return None, None
    if remote_url.startswith("git@"):
        host_part, path = remote_url.split(":", 1)
        host = host_part.split("@", 1)[1] if "@" in host_part else host_part
    elif "://" in remote_url:
        parsed = urllib.parse.urlparse(remote_url)
        host = parsed.hostname
        path = parsed.path.lstrip("/")
    else:
        return None, None
    if path is None:
        return None, None
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return host, path


def _get_token(platform):
    if platform == "github":
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    return os.environ.get("GITLAB_TOKEN") or os.environ.get("GL_TOKEN")


def _resolve_base(d, remote, base_arg):
    """Return the base branch name for a repo, or None if unresolved.

    Uses --base when given, otherwise the remote's default branch via
    refs/remotes/<remote>/HEAD, falling back to <remote>/main then <remote>/master.
    """
    if base_arg:
        return base_arg
    out = subprocess.run(
        ["git", "-C", str(d), "symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD"],
        capture_output=True, text=True,
    )
    if out.returncode == 0:
        ref = out.stdout.strip()
        prefix = f"{remote}/"
        if ref.startswith(prefix):
            return ref[len(prefix):]
    for cand in ("main", "master"):
        check = subprocess.run(
            ["git", "-C", str(d), "rev-parse", "--verify", "-q", f"{remote}/{cand}"],
            capture_output=True, text=True,
        )
        if check.returncode == 0:
            return cand
    return None


def _github_create_pr(token, owner, repo, title, body, head, base):
    """Create a GitHub PR via REST API; return the PR URL or raise."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    data = json.dumps({"title": title, "body": body, "head": head, "base": base}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result.get("html_url")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        msg = body
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                msg = parsed.get("message") or parsed.get("error") or body
        except (ValueError, json.JSONDecodeError):
            pass
        raise RuntimeError(f"GitHub API error {e.code}: {msg}") from e


def _gitlab_create_mr(token, project_path, title, body, source_branch, target_branch):
    """Create a GitLab merge request via API v4; return the MR URL or raise."""
    encoded = urllib.parse.quote(project_path, safe="")
    url = f"https://gitlab.com/api/v4/projects/{encoded}/merge_requests"
    data = urllib.parse.urlencode({
        "source_branch": source_branch,
        "target_branch": target_branch,
        "title": title,
        "description": body,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("PRIVATE-TOKEN", token)
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result.get("web_url")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        msg = body
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                msg = parsed.get("message") or parsed.get("error") or body
        except (ValueError, json.JSONDecodeError):
            pass
        raise RuntimeError(f"GitLab API error {e.code}: {msg}") from e


def _fallback_url(platform, remote_url, head, base):
    """Construct a web URL for manually creating a PR/MR, or the raw URL."""
    host, path = _parse_remote_url(remote_url)
    if host is None or path is None:
        return remote_url
    enc_head = urllib.parse.quote(head, safe="/")
    enc_base = urllib.parse.quote(base, safe="/")
    if platform == "github":
        return f"https://{host}/{path}/compare/{enc_base}...{enc_head}?expand=1"
    return f"https://{host}/{path}/-/merge_requests/new?merge_request[source_branch]={enc_head}&merge_request[target_branch]={enc_base}"


def _auto_title(branch):
    """Auto-generate a conventional-commit style title from a branch name."""
    branch = branch or ""
    if "/" in branch:
        type_part, rest = branch.split("/", 1)
        return f"{type_part}: {rest.replace('-', ' ').replace('_', ' ')}"
    return branch.replace("-", " ").replace("_", " ").strip()


def _get_review_candidates(config, base, only=None, base_branch=None):
    """Return candidate dicts for repos with pushed branches ahead of the base."""
    candidates = []
    failed = []
    for platform, local_path, remote_path, d in each_existing_repo(config, base, only=only):
        branch, upstream, ahead, behind, state = _get_branch_info(d)
        if state != "tracking" or not upstream or "/" not in upstream:
            continue
        if "/" not in upstream:
            continue
        remote, remote_branch = upstream.split("/", 1)
        if remote_branch != branch:
            continue
        resolved_base = _resolve_base(d, remote, base_branch)
        if resolved_base is None:
            failed.append((platform, local_path, branch, d, "could not resolve base branch; use --base"))
            continue
        if branch == resolved_base:
            continue
        count_result = subprocess.run(
            ["git", "-C", str(d), "rev-list", "--count", f"{remote}/{resolved_base}..{remote}/{branch}"],
            capture_output=True, text=True,
        )
        try:
            count = int(count_result.stdout.strip()) if count_result.returncode == 0 else 0
        except (ValueError, AttributeError):
            count = 0
        if count <= 0:
            continue
        candidates.append({
            "platform": platform,
            "local_path": local_path,
            "d": d,
            "remote": remote,
            "branch": branch,
            "base": resolved_base,
            "count": count,
            "unpushed": ahead > 0,
        })
    return candidates, failed


def _review_task(c, title, body, dry_run, json_output, results, results_lock):
    """Create (or plan) a PR for one review candidate."""
    platform = c["platform"]
    local_path = c["local_path"]
    d = c["d"]
    branch = c["branch"]
    base = c["base"]
    label = f"{platform}/{local_path}"
    remote_url = _git_out(d, "remote", "get-url", c["remote"]) or ""
    fallback = _fallback_url(platform, remote_url, branch, base)
    token = _get_token(platform)

    if dry_run:
        entry = {
            "platform": platform,
            "path": local_path,
            "branch": branch,
            "status": "planned",
            "url": fallback,
            "error": None,
        }
        with results_lock:
            results.append(entry)
        if not json_output:
            print(f"{OK} {label}: {branch} -> {base} (title: {title})")
            print(f"  URL: {fallback}")
        return

    url = None
    error = None
    status = "created"
    if token:
        host, path = _parse_remote_url(remote_url)
        try:
            if platform == "github":
                owner, repo = path.split("/", 1)
                url = _github_create_pr(token, owner, repo, title, body, branch, base)
            else:
                url = _gitlab_create_mr(token, path, title, body, branch, base)
        except Exception as e:  # noqa: BLE001
            status = "failed"
            error = str(e)
            url = fallback
    else:
        url = fallback
        status = "manual"

    entry = {
        "platform": platform,
        "path": local_path,
        "branch": branch,
        "status": status,
        "url": url,
        "error": error,
    }
    with results_lock:
        results.append(entry)
    if not json_output:
        if status == "failed":
            print(f"{ERR} {label}: {error}")
            print(f"  URL: {fallback}")
        elif token:
            print(f"{OK} {label}: PR created -> {url}")
        else:
            print(f"{_Y}~{_RST} {label}: no token; open manually -> {url}")


def cmd_review(config, base, mode="interactive", base_branch=None, dry_run=False, only=None, jobs=None, json_output=False):
    """Open PRs for pushed branches ahead of the default branch."""
    candidates, failed = _get_review_candidates(config, base, only=only, base_branch=base_branch)

    if not candidates and not failed:
        if json_output:
            print(json.dumps([]))
        else:
            print("No branches to review.")
        return

    results = []
    results_lock = threading.Lock()

    for platform, local_path, branch, d, err in failed:
        entry = {
            "platform": platform,
            "path": local_path,
            "branch": branch,
            "status": "failed",
            "url": None,
            "error": err,
        }
        with results_lock:
            results.append(entry)
        if not json_output:
            print(f"{ERR} {platform}/{local_path}: {err}")

    for c in candidates:
        if c["unpushed"]:
            print(f"{WARN} {c['platform']}/{c['local_path']}: branch '{c['branch']}' has unpushed commits; they will not be in the PR.",
                  file=sys.stderr)

    if mode == "interactive":
        for c in candidates:
            label = f"{c['platform']}/{c['local_path']}"
            if dry_run:
                remote_url = _git_out(c["d"], "remote", "get-url", c["remote"]) or ""
                url = _fallback_url(c["platform"], remote_url, c["branch"], c["base"])
                print(f"{OK} {label}: {c['branch']} -> {c['base']} (title: <prompted>)")
                print(f"  URL: {url}")
                continue
            diff = subprocess.run(
                ["git", "-C", str(c["d"]), "diff", "--stat", f"{c['remote']}/{c['base']}...{c['remote']}/{c['branch']}"],
                capture_output=True, text=True,
            ).stdout.strip()
            print(f"\n{label}:")
            print(f"  {c['branch']} -> {c['base']}")
            if diff:
                for line in diff.splitlines():
                    print(f"    {line}")
            title = input("  PR title (blank to skip): ").strip()
            if not title:
                print("  Skipped.")
                continue
            body = input("  PR body (blank for none): ").strip()
            _review_task(c, title, body, dry_run, json_output, results, results_lock)

    elif mode == "all":
        if not json_output:
            print("Eligible repos:")
            for c in candidates:
                print(f"  {c['platform']}/{c['local_path']}: {c['branch']} -> {c['base']}")
        prompt = "\nPR title for all repos (blank to abort): "
        if json_output:
            print(prompt, end="", file=sys.stderr, flush=True)
            title = input().strip()
        else:
            title = input(prompt).strip()
        if not title:
            if json_output:
                print(json.dumps([]))
            else:
                print("Aborted.")
            return
        body_prompt = "\nPR body (blank for none): "
        if json_output:
            print(body_prompt, end="", file=sys.stderr, flush=True)
            body = input().strip()
        else:
            body = input(body_prompt).strip()
        if dry_run:
            for c in candidates:
                remote_url = _git_out(c["d"], "remote", "get-url", c["remote"]) or ""
                url = _fallback_url(c["platform"], remote_url, c["branch"], c["base"])
                with results_lock:
                    results.append({
                        "platform": c["platform"],
                        "path": c["local_path"],
                        "branch": c["branch"],
                        "status": "planned",
                        "url": url,
                        "error": None,
                    })
                if not json_output:
                    print(f"{OK} {c['platform']}/{c['local_path']}: {c['branch']} -> {c['base']} (title: {title})")
        else:
            with _pool(jobs) as pool:
                futures = [pool.submit(_review_task, c, title, body, False, json_output, results, results_lock) for c in candidates]
                for f in as_completed(futures):
                    f.result()

    elif mode == "auto":
        if dry_run:
            for c in candidates:
                title = _auto_title(c["branch"])
                body = f"Branch: {c['branch']}\nCommits: {c['count']}"
                remote_url = _git_out(c["d"], "remote", "get-url", c["remote"]) or ""
                url = _fallback_url(c["platform"], remote_url, c["branch"], c["base"])
                with results_lock:
                    results.append({
                        "platform": c["platform"],
                        "path": c["local_path"],
                        "branch": c["branch"],
                        "status": "planned",
                        "url": url,
                        "error": None,
                    })
                if not json_output:
                    print(f"{OK} {c['platform']}/{c['local_path']}: {c['branch']} -> {c['base']} (title: {title})")
                    print(f"  URL: {url}")
        else:
            with _pool(jobs) as pool:
                futures = [
                    pool.submit(_review_task, c, _auto_title(c["branch"]), f"Branch: {c['branch']}\nCommits: {c['count']}", False, json_output, results, results_lock)
                    for c in candidates
                ]
                for f in as_completed(futures):
                    f.result()

    if json_output:
        results.sort(key=lambda r: (r["platform"], r["path"]))
        print(json.dumps(results))

import json
import re
import shutil
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

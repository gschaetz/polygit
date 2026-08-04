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


def each_existing_repo(config, base):
    """Yield only repos that are already cloned locally."""
    for platform, local_path, remote_path, d in each_repo(config, base):
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
    subprocess.run(["git", "-C", str(d), "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", str(d), "commit", "-m", msg], capture_output=True)
    result = _run_git(["git", "-C", str(d), "push"])
    if result.returncode != 0:
        lines.append(f"{ERR} {label}: push failed — {result.stderr.strip().splitlines()[0]}")
    else:
        lines.append(f"{UPD} {label}: pushed")
    _emit(lines)


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


def _pull_one(platform, local_path, d):
    label = f"{platform}/{local_path}"
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


def cmd_sync(config, base):
    repos = list(each_repo(config, base))
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_sync_one, p, lp, rp, d) for p, lp, rp, d in repos]
        for f in as_completed(futures):
            f.result()


def cmd_status(config, base):
    results = []

    def _check(platform, local_path, d):
        result = subprocess.run(
            ["git", "-C", str(d), "status", "--short"],
            capture_output=True, text=True
        )
        return platform, local_path, result.stdout.strip()

    repos = list(each_existing_repo(config, base))
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_check, p, lp, d): (p, lp) for p, lp, _, d in repos}
        for f in as_completed(futures):
            results.append(f.result())

    found_dirty = False
    for platform, local_path, output in sorted(results):
        if output:
            found_dirty = True
            print(f"\n{_Y}~{_RST} {platform}/{local_path}:")
            for line in output.splitlines():
                print(f"  {line}")
    if not found_dirty:
        print(f"{OK} All repos are clean.")


def cmd_pull(config, base):
    repos = list(each_existing_repo(config, base))
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_pull_one, p, lp, d) for p, lp, _, d in repos]
        for f in as_completed(futures):
            f.result()


def cmd_push(config, base, mode="interactive"):
    dirty = [
        (platform, local_path, d)
        for platform, local_path, _, d in each_existing_repo(config, base)
        if is_dirty(d)
    ]

    if not dirty:
        print("No dirty repos to commit.")
        return

    if mode == "wip":
        msg = f"WIP {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
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
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
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

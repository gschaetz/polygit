import subprocess
from datetime import datetime
from pathlib import Path
from .config import HOSTS


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
    print(f"Committing {label}...")
    subprocess.run(["git", "-C", str(d), "add", "-A"])
    subprocess.run(["git", "-C", str(d), "commit", "-m", msg])
    result = subprocess.run(["git", "-C", str(d), "push"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Push failed: {result.stderr.strip()}")
    else:
        print(f"  Pushed.")


def cmd_sync(config, base):
    for platform, local_path, remote_path, d in each_repo(config, base):
        url = f"{HOSTS[platform]}:{remote_path}.git"
        if (d / ".git").exists():
            print(f"Fetching {platform}/{local_path}...")
            subprocess.run(["git", "-C", str(d), "fetch", "--all", "-q"])
        else:
            print(f"Cloning {platform}/{local_path}...")
            d.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", url, str(d)])


def cmd_status(config, base):
    found_dirty = False
    for platform, local_path, _, d in each_existing_repo(config, base):
        result = subprocess.run(
            ["git", "-C", str(d), "status", "--short"],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            found_dirty = True
            print(f"\n{platform}/{local_path}:")
            for line in result.stdout.strip().splitlines():
                print(f"  {line}")
    if not found_dirty:
        print("All repos are clean.")


def cmd_pull(config, base):
    for platform, local_path, _, d in each_existing_repo(config, base):
        label = f"{platform}/{local_path}"
        stashed = False
        if is_dirty(d):
            print(f"Stashing {label}...")
            subprocess.run(["git", "-C", str(d), "stash"], capture_output=True)
            stashed = True
        print(f"Pulling {label}...")
        result = subprocess.run(
            ["git", "-C", str(d), "pull", "--rebase"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  Error: {result.stderr.strip()}")
        elif result.stdout.strip() and result.stdout.strip() != "Already up to date.":
            print(f"  {result.stdout.strip()}")
        if stashed:
            pop = subprocess.run(
                ["git", "-C", str(d), "stash", "pop"],
                capture_output=True, text=True
            )
            if pop.returncode != 0:
                print(f"  Warning: stash pop had conflicts in {label}")
            else:
                print(f"  Stash restored.")


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
        for platform, local_path, d in dirty:
            _commit_and_push(d, f"{platform}/{local_path}", msg)

    elif mode == "all":
        print("Dirty repos:")
        for platform, local_path, _ in dirty:
            print(f"  {platform}/{local_path}")
        msg = input("\nCommit message for all repos (blank to abort): ").strip()
        if not msg:
            print("Aborted.")
            return
        for platform, local_path, d in dirty:
            _commit_and_push(d, f"{platform}/{local_path}", msg)

    else:  # interactive
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

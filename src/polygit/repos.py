import subprocess
from pathlib import Path
from .config import HOSTS, write_config
from .repo import walk


def parse_remote_url(url):
    """Parse a git remote URL into (platform, remote_path).

    git@github.com:org/repo.git       -> (github, org/repo)
    git@gitlab.com:ns/sub/repo.git    -> (gitlab, ns/sub/repo)
    https://github.com/org/repo.git   -> (github, org/repo)
    """
    if not url:
        return None, None
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("git@"):
        host, path = url[4:].split(":", 1)
    elif "://" in url:
        rest = url.split("://", 1)[1]
        host, path = rest.split("/", 1)
    else:
        return None, None
    platform = "github" if "github" in host else ("gitlab" if "gitlab" in host else None)
    return platform, path


def del_nested(d, keys):
    """Delete d[k0][k1]...[kn], pruning empty parent dicts."""
    if not keys or keys[0] not in d:
        return
    if len(keys) == 1:
        del d[keys[0]]
    else:
        del_nested(d[keys[0]], keys[1:])
        if isinstance(d[keys[0]], dict) and not d[keys[0]]:
            del d[keys[0]]


def _add_to_config(config, fs_platform, local_path, remote_url):
    """Insert a repo entry into the config data structure.

    Always nests under the *local* namespace (the repo's actual directory
    location), with a `{remote: ...}` override when the remote path differs
    — e.g. a repo cloned under a local namespace unrelated to its remote
    org/namespace.
    """
    local_parts = local_path.split("/")
    local_name  = local_parts[-1]
    local_ns    = "/".join(local_parts[:-1])
    _, remote_path = parse_remote_url(remote_url)
    platform_data = config.setdefault(fs_platform, {})
    ns_data = platform_data.setdefault(local_ns, {})

    if remote_path and remote_path != local_path:
        ns_data[local_name] = {"remote": remote_path}
    else:
        ns_data[local_name] = None


def cmd_repos(config, base, config_path):
    """Diff .pgit config against the filesystem and offer to update."""

    # ── 1. Scan filesystem ──────────────────────────────────────────────────
    local_repos = {}  # "platform/local_path" -> (dir, remote_url)
    for platform in ["github", "gitlab"]:
        platform_dir = base / platform
        if not platform_dir.exists():
            continue
        for git_marker in sorted(platform_dir.rglob(".git")):
            if not git_marker.is_dir():
                continue
            repo_dir = git_marker.parent
            rel      = repo_dir.relative_to(platform_dir)
            parts    = rel.parts
            # Skip repos nested inside another git repo
            if any((platform_dir.joinpath(*parts[:i]) / ".git").is_dir()
                   for i in range(1, len(parts))):
                continue
            result = subprocess.run(
                ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
                capture_output=True, text=True
            )
            remote_url = result.stdout.strip() if result.returncode == 0 else None
            local_repos[f"{platform}/{rel}"] = (repo_dir, remote_url)

    # ── 2. Build tracked indices ─────────────────────────────────────────────
    tracked_by_local  = {}  # "platform/local_path"   -> (remote_path, expected_url)
    tracked_by_remote = {}  # "platform/remote_path"  -> "platform/local_path"

    for platform, namespaces in config.items():
        host = HOSTS.get(platform, "")
        for ns_key, ns_value in namespaces.items():
            for local_path, remote_path in walk(ns_value, ns_key):
                lkey = f"{platform}/{local_path}"
                rkey = f"{platform}/{remote_path}"
                tracked_by_local[lkey]  = (remote_path, f"{host}:{remote_path}.git")
                tracked_by_remote[rkey] = lkey

    # ── 3. Categorize ────────────────────────────────────────────────────────
    untracked       = {}  # key -> (dir, url)
    wrong_location  = {}  # key -> (dir, url, config_key)
    remote_mismatch = {}  # key -> (expected_url, actual_url)
    missing = {k for k in tracked_by_local if k not in local_repos}

    for key, (repo_dir, remote_url) in local_repos.items():
        fs_platform = key.split("/")[0]
        _, remote_path = parse_remote_url(remote_url)
        rkey = f"{fs_platform}/{remote_path}" if remote_path else None

        if key in tracked_by_local:
            _, expected_url = tracked_by_local[key]
            if remote_url and remote_url != expected_url:
                remote_mismatch[key] = (expected_url, remote_url)
        elif rkey and rkey in tracked_by_remote:
            wrong_location[key] = (repo_dir, remote_url, tracked_by_remote[rkey])
        else:
            untracked[key] = (repo_dir, remote_url)

    # ── 4. Report ─────────────────────────────────────────────────────────────
    if not any([untracked, wrong_location, remote_mismatch, missing]):
        print(".pgit is in sync with the filesystem.")
        return

    if remote_mismatch:
        print("\nRemote mismatch (local path matches config but git remote differs):")
        for key, (expected, actual) in sorted(remote_mismatch.items()):
            print(f"  ~ {key}")
            print(f"      config: {expected}")
            print(f"      actual: {actual}")

    if wrong_location:
        print("\nCloned to a different path than .pgit expects:")
        for key, (_, url, config_key) in sorted(wrong_location.items()):
            actual_dir   = base / Path(*key.split("/"))
            expected_dir = base / Path(*config_key.split("/"))
            is_rename    = actual_dir.parent == expected_dir.parent
            hint = f"  (rename: {actual_dir.name} → {expected_dir.name})" if is_rename else ""
            print(f"  ? {key}")
            print(f"      remote:   {url}")
            print(f"      expected: {config_key}{hint}")

    if untracked:
        print("\nOn disk but not in .pgit:")
        for key, (_, url) in sorted(untracked.items()):
            print(f"  + {key}  ({url or 'no remote'})")

    if missing:
        print("\nIn .pgit but not cloned locally (run: pgit sync):")
        for key in sorted(missing):
            print(f"  - {key}")

    # ── 5. Add untracked ──────────────────────────────────────────────────────
    if untracked:
        print()
        if input("Add untracked repos to .pgit? [y/N] ").strip().lower() == "y":
            for key, (_, remote_url) in sorted(untracked.items()):
                fs_platform, local_path = key.split("/", 1)
                _add_to_config(config, fs_platform, local_path, remote_url)
                print(f"  Added {key}")
            write_config(config, config_path)
            print(f"\nUpdated {config_path}")

    # ── 6. Fix wrong-location ─────────────────────────────────────────────────
    if wrong_location:
        for key, (_, remote_url, config_key) in sorted(wrong_location.items()):
            actual_dir   = base / Path(*key.split("/"))
            expected_dir = base / Path(*config_key.split("/"))
            is_rename    = actual_dir.parent == expected_dir.parent
            print()
            if is_rename:
                if input(f"Rename {actual_dir.name} → {expected_dir.name}? [y/N] ").strip().lower() == "y":
                    actual_dir.rename(expected_dir)
                    print(f"  Renamed.")
            else:
                if input(f"Add {key} to .pgit with remote override? [y/N] ").strip().lower() == "y":
                    fs_platform, local_path = key.split("/", 1)
                    _add_to_config(config, fs_platform, local_path, remote_url)
                    print(f"  Added {key}")
                    write_config(config, config_path)
                    print(f"\nUpdated {config_path}")

    # ── 7. Remove missing ─────────────────────────────────────────────────────
    if missing:
        print()
        if input("Remove missing repos from .pgit? [y/N] ").strip().lower() == "y":
            for key in sorted(missing):
                fs_platform, local_path = key.split("/", 1)
                for ns_key in list(config.get(fs_platform, {}).keys()):
                    if local_path.startswith(ns_key + "/"):
                        sub = local_path[len(ns_key)+1:].split("/")
                        del_nested(config[fs_platform][ns_key], sub)
                        if not config[fs_platform][ns_key]:
                            del config[fs_platform][ns_key]
                        break
                print(f"  Removed {key}")
            write_config(config, config_path)
            print(f"\nUpdated {config_path}")

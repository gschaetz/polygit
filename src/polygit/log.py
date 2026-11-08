"""Read and merge recent commits across configured repositories."""

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def read_commits(d, limit, since=None, author=None):
    """Return recent commits from one repository's current HEAD."""
    if limit == 0:
        return []

    args = [
        "git", "-C", str(d), "log", "-n", str(limit),
        "--format=%h%x1f%an%x1f%ct%x1f%cI%x1f%s",
    ]
    if since is not None:
        args.append(f"--since={since}")
    if author is not None:
        args.extend(["--fixed-strings", "--regexp-ignore-case", f"--author={author}"])

    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        return []

    commits = []
    for line in result.stdout.splitlines():
        fields = line.split("\x1f", 4)
        if len(fields) != 5:
            continue
        commit_hash, commit_author, timestamp, date, subject = fields
        commits.append({
            "hash": commit_hash,
            "author": commit_author,
            "timestamp": int(timestamp),
            "date": date,
            "subject": subject,
        })
    return commits


def merge_commits(per_repo, limit):
    """Sort commits newest-first with deterministic path and hash tie-breaks."""
    commits = (commit for repo_commits in per_repo for commit in repo_commits)
    return sorted(
        commits,
        key=lambda commit: (-commit["timestamp"], commit["path"], commit["hash"]),
    )[:limit]


def collect_commits(config, base, limit, since, author, only, jobs):
    """Read commits from cloned configured repos and merge their results."""
    from .repo import MAX_WORKERS, each_existing_repo

    repos = list(each_existing_repo(config, base, only=only))

    def _read(repo):
        platform, local_path, _, directory = repo
        commits = read_commits(directory, limit, since=since, author=author)
        name = Path(local_path).name
        return [
            {
                **commit,
                "name": name,
                "path": str(directory),
                "platform": platform,
            }
            for commit in commits
        ]

    with ThreadPoolExecutor(max_workers=jobs or MAX_WORKERS) as pool:
        per_repo = list(pool.map(_read, repos))

    return merge_commits(per_repo, limit)

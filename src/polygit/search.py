"""Search module for finding repos by name, path, or remote URL.

Matching is case-insensitive and exact apart from case (no typo tolerance). Each
repo's score is the maximum of its name, path, and remote scores.
"""

import subprocess
from concurrent.futures import ThreadPoolExecutor

# Base scores per field and match kind. The position bonus is below 1, so it
# never lifts a match into a higher tier.
_NAME_PREFIX = 10
_NAME_BOUNDARY = 7
_NAME_SUBSTRING = 5
_PATH_SCORE = 3
_REMOTE_SCORE = 2


def _find_match(term, text):
    """Locate the best match of term in text, both already lowercased.

    Returns (kind, index) where kind is "prefix", "boundary" or "substring" and
    index is where the match starts, or None when term does not occur. A word
    boundary is the start of text or a position after a non-alphanumeric char.
    """
    idx = text.find(term)
    if idx < 0:
        return None
    if idx == 0:
        return "prefix", 0
    substring_idx = idx
    while idx >= 0:
        if not text[idx - 1].isalnum():
            return "boundary", idx
        idx = text.find(term, idx + 1)
    return "substring", substring_idx


def _position_bonus(index):
    """Bonus in (0, 0.5] that is larger the earlier the match is."""
    return 0.5 / (1 + index)


def _compute_relevance_term(term, name):
    """Score term against a repo name.

    Args:
        term: The search term (case-insensitive).
        name: The repo name (final path component).

    Returns:
        10+ for a prefix match, 7+ for a word-boundary match, 5+ for a substring
        match (plus a position bonus below 1), or 0 for no match.
    """
    match = _find_match(term.lower(), name.lower())
    if match is None:
        return 0
    kind, idx = match
    base = {"prefix": _NAME_PREFIX, "boundary": _NAME_BOUNDARY, "substring": _NAME_SUBSTRING}[kind]
    return base + _position_bonus(idx)


def _compute_relevance_path(term, path):
    """Score term against a filesystem path: 3+ position bonus, or 0 for no match."""
    idx = path.lower().find(term.lower())
    if idx < 0:
        return 0
    return _PATH_SCORE + _position_bonus(idx)


def _compute_relevance_remote(term, remote_url):
    """Score term against a remote URL as-is: 2+ position bonus, or 0 for no match."""
    idx = (remote_url or "").lower().find(term.lower())
    if idx < 0:
        return 0
    return _REMOTE_SCORE + _position_bonus(idx)


def rank_search_results(results, term):
    """Score repos against term and rank them.

    A repo's score is the maximum of its name, path, and remote scores. Repos
    that do not match are dropped. Results are sorted by descending score, then
    alphabetically by path.

    Args:
        results: List of repo dicts with 'name', 'path', and 'remote' fields.
        term: The search term.

    Returns:
        New list of repo dicts, each with an added 'score' field.
    """
    scored = []
    for repo in results:
        score = max(
            _compute_relevance_term(term, repo["name"]),
            _compute_relevance_path(term, repo["path"]),
            _compute_relevance_remote(term, repo.get("remote", "")),
        )
        if score > 0:
            scored.append({**repo, "score": round(score, 4)})
    return sorted(scored, key=lambda r: (-r["score"], r["path"]))


def build_search_index(config, base, jobs=None, only=None):
    """Build the list of cloned repos to search.

    Reads each repo's origin remote with `git remote get-url origin`, in parallel.
    A repo without an origin gets an empty remote.

    Args:
        config: The loaded .pgit configuration.
        base: The repos root directory.
        jobs: Maximum number of parallel git calls (default: 8).
        only: Optional platform name to limit the index to.

    Returns:
        List of dicts with 'name', 'path', 'platform' and 'remote'.
    """
    from .repo import each_existing_repo, MAX_WORKERS  # repo imports this module

    repos = list(each_existing_repo(config, base, only=only))

    def _origin(d):
        result = subprocess.run(["git", "-C", str(d), "remote", "get-url", "origin"],
                                capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else ""

    with ThreadPoolExecutor(max_workers=jobs or MAX_WORKERS) as pool:
        remotes = list(pool.map(_origin, (d for _, _, _, d in repos)))

    return [
        {"name": local_path.split("/")[-1], "path": str(d), "platform": platform, "remote": remote}
        for (platform, local_path, _, d), remote in zip(repos, remotes)
    ]

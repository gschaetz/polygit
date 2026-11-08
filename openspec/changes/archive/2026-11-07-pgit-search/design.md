# Design

## Context

The `pgit` CLI currently provides commands for managing git repos (`sync`, `status`, `pull`, `push`, `commit`, `merge`, `review`, `checkout`, `branches`) but has no discovery mechanism. Users must remember repo names or use external shell tools to find repositories. The existing codebase uses:
- Pure stdlib (argparse, subprocess)
- Thread pool for parallel ops (`concurrent.futures.ThreadPoolExecutor`)
- Config walking up from cwd via `find_config()`
- `cmd_*` functions in `src/polygit/repo.py`

## Goals / Non-Goals

**Goals:**
- Add search across repo names, paths, and remotes
- Simple, fast implementation using plain string operations
- Consistent CLI pattern matching existing commands (json output, --only filter)

**Non-Goals:**
- Typo-tolerant (fuzzy) matching; may follow in a later change if wanted
- Full-text repository content search (future enhancement)
- Index persistence or caching layer
- Complex scoring algorithms beyond relevance ranking

## Decisions

### 1. Matching Approach
Case-insensitive string operations only: prefix (`startswith`), word-boundary (the term follows a non-alphanumeric character or the start of the string), and substring (`in`). No `fnmatch`, regex, or edit distance.

Alternative considered: `fuzzywuzzy` or `rapidfuzz` - **rejected** due to external dependency requirement.

Rationale: Keeps deps pure; most searches are exact fragments of a name, path, or owner.

### 2. Data Structure for Search Index
Build repository metadata once at command start into a simple list of dicts:
```python
[{
    'name': 'polygit',
    'path': '/home/user/development/polygit',
    'platform': 'github',
    'remote': 'https://github.com/example/polygit.git'
}]
```

Only repos that are cloned on disk are indexed. `remote` is the output of `git remote get-url origin`, read in parallel under the shared `--jobs` limit (same thread-pool pattern as other commands); a repo with no `origin` has `remote` set to `""` and can still match on name and path.

Rationale: Mirrors existing `cmd_status` and other command patterns. Efficient for small-to-medium repo counts (<1000).

### 3. Module and Function Layout
- `src/polygit/search.py` holds the logic: `build_search_index(config, base, jobs)`, `_compute_relevance_term()`, `_compute_relevance_path()`, `_compute_relevance_remote()`, and `rank_search_results()`.
- `cmd_search(config, base, term, limit, only_platform, jobs, json_output)` lives in `src/polygit/repo.py` next to the other `cmd_*` functions and calls into `search.py`.

Rationale: Follows the existing pattern (commands in `repo.py`) while keeping search-specific logic isolated.

### 4. CLI Integration
Add `search_p = sub.add_parser("search", ...)` following the branches pattern:
- Positional `term` argument; empty or whitespace-only terms are rejected with exit status 2 before config lookup
- `--limit N` validated before config lookup with a new `_non_negative_int` type (`0` is allowed and yields an empty result)
- `--json`, `--only`, `--jobs` shared options

Rationale: Consistent with existing command patterns; validates arguments early for better UX.

### 5. Ranking Strategy
Each repo gets a name score, a path score, and a remote score, each `0` when the term does not match. The repo's final `score` is the **maximum** of the three, so a strong name match is never diluted by weak path or remote matches.

Base scores:
- Name prefix: 10
- Name word-boundary: 7
- Name substring: 5
- Path match (word-boundary or substring): 3
- Remote URL match: 2

Position bonus: earlier match in the string adds a bonus smaller than the gap between tiers, so tiers never reorder (e.g. `1 / (1 + index)`, capped below 1).

Rationale: Weight hierarchy reflects user intent (name is most commonly searched attribute). Ties break alphabetically by full path.

## Risks / Trade-offs

**Risk:** Users who mistype a name get no results.
→ **Mitigation:** Out of scope for v1; edit-distance matching can be added later without changing the output format.

**Risk:** Performance degrades with many repos (>1000), mainly from one `git remote get-url` per repo.
→ **Mitigation:** Remotes are read in parallel under `--jobs`; matching itself is O(n*m) which is acceptable at this size.

## Migration Plan

None - this is a new command with no backward compatibility concerns.

## Open Questions

1. Should we support glob patterns (e.g., `pgit search *backend*`) as part of search terms?
   → Answer: Not in v1; keep search term simple string matching only.

2. Should `--limit` default to something finite (e.g., 100) instead of unlimited?
   → Answer: Start with unlimited; adjust based on usage. Can add config option if needed.

3. Should we index remote URLs differently (e.g., extract owner from URL)?
   → Answer: Match against the URL as-is; owner matches (e.g. `example`) work because the owner is part of the URL.

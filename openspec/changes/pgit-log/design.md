# Design

## Context

`pgit` commands that read repo state (`branches`, `status`, `search`) gather per-repo data in a thread pool (`_pool(jobs)`, `each_existing_repo`) and print text or one JSON array. `_git_out` wraps `git -C <dir> ...`. Argument validators live in `cli.py` (`_positive_int`, `_non_negative_int`). See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- One read-only command that merges recent history from every cloned repo
- Same option and output conventions as `search` and `branches`

**Non-Goals:**
- Fetching, other branches, or graph/diff output
- Pattern matching in `--author`, or git's free-form date parsing in `--since`
- Stat or file lists per commit

## Decisions

### 1. Let git do the per-repo work
Run one `git -C <dir> log -n <limit> --fixed-strings --regexp-ignore-case [--since=<v>] [--author=<t>] --format=%h%x1f%an%x1f%ct%x1f%cI%x1f%s` per repo, then merge in Python. Each repo returns at most `limit` commits, which is enough to build the global top `limit`. With `--limit 0` no git calls are made.

Alternative: read all history and filter in Python. Rejected: slow on big repos and re-implements `--since`/`--author`.

### 2. Commit date, not author date
Sort, filter and display the commit date (`%ct` for sorting, `%cI` for display), because git's `--since` filters on it. Mixing it with author dates would make `--since` and the listed date disagree.

### 3. Strict `--since` forms
Git accepts almost any string for `--since` and never fails, so an invalid value could not be reported as exit 2. `cli.py` validates `--since` itself (`_since_value`) against `YYYY-MM-DD` (a real calendar date) or `N.unit` / `N unit` with units `minute|hour|day|week|month|year` (plural allowed) and passes the accepted text to git unchanged.

### 4. Ordering and ties
Sort by commit timestamp descending, then repo `path`, then `hash`. Slice to `limit` after merging.

### 5. Layout
- `src/polygit/log.py`: `read_commits(d, limit, since, author)` (one repo), `merge_commits(per_repo, limit)` (sort and slice), `collect_commits(config, base, limit, since, author, only, jobs)` (index plus pool)
- `cmd_log(config, base, limit, since, author, only, jobs, json_output)` in `repo.py` prints text or JSON, like `cmd_search`
- `path` is the full filesystem path, as in `search`

### 6. Empty and failing repos
A repo whose `git log` exits non-zero (for example, no commits yet) is skipped silently.

## Risks / Trade-offs

[A repo's `git log` fails for another reason and is hidden] → Accepted for v1; it matches how `branches` treats unreadable repos. Revisit if it causes confusion.

[Thousands of repos start thousands of git processes] → Bounded by `--jobs`.

## Migration Plan

None. New command, no changes to existing output.

## Open Questions

None.

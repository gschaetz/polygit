# Proposal

## Why

`pgit checkout` can create a branch everywhere with `-b`, but cannot get back. When a tree mixes `main` and `master` repos, `pgit checkout main` skips the `master` ones, so undoing `pgit checkout -b feat` needs per-repo `git checkout master`. This was hit on a real tree. Git already records each repo's previous branch, so `pgit checkout -` can restore it, as `git checkout -` does.

## What Changes

- `pgit checkout -` switches every repo to the branch it was on before its last switch (git's `@{-1}`), resolved per repo
- A repo with no previous branch (fresh clone, detached previous state, previous branch deleted) is skipped with a reason
- The resolved branch then follows the existing switch rules (dirty tree, detached HEAD, operation in progress, branch missing)
- `-` cannot be combined with `-b`
- `--dry-run`, `--json`, `--only` and `--jobs` work as on other checkouts

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `checkout`: add switching to each repo's previous branch via `-`
- `cli`: the `checkout` branch argument accepts `-`, and `-` with `-b` is a usage error

## Impact

- `src/polygit/repo.py`: resolve the previous branch per repo before the existing precheck
- `src/polygit/cli.py`: accept `-` and reject `-b -` before the config lookup
- Tests in `tests/test_polygit.py`; `README.md` checkout section
- No change to existing `checkout` behavior or output when the argument is a branch name

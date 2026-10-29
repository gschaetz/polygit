# Proposal

## Why

`pgit push` already commits and pushes dirty repos in bulk, but there is no way to **only commit** (without pushing) across multiple repos, nor is there a way to **merge a target branch into the current branch** across multiple repos. Users who want to stage a shared commit message across repos before reviewing/pushing, or who need to keep feature branches in sync with `main` across many repos, must run `git commit` or `git merge` manually in each repo.

## What Changes

- New command `pgit commit` — commit all dirty repos with a shared message (interactive, `--all`, `--wip` modes, mirroring `pgit push` but without the push step). Supports `--json` in the non-interactive modes.
- New command `pgit merge` — merge a specified local branch (e.g., `main`) into the current branch of each cloned repo, with conflict reporting and optional `--no-ff` / `--squash` flags. It does not fetch.
- Both commands follow existing conventions: `--only`, `--jobs`, `--dry-run`, and thread-pool parallelism, plus `--json`.
- `pgit push` is refactored to share the commit step with `pgit commit`; its behavior and output do not change.

## Capabilities

### New Capabilities
- `commit`: Bulk commit of dirty repos without pushing. Covers interactive/auto/WIP message modes, dry-run, parallel execution, and JSON output.
- `merge`: Bulk merge of a target branch into each repo's current branch. Covers merge strategy flags, skip conditions, conflict handling, plan-only dry-run, parallel execution, and JSON output.

### Modified Capabilities
None. The shared `cli` requirements (`--only`, `--jobs`, `--json`) already apply generically and are referenced by the new specs.

## Impact

- `src/polygit/repo.py`: new `cmd_commit` and `cmd_merge`, a shared `_commit_one` helper, and a shared WIP message helper.
- `src/polygit/cli.py`: register the `commit` and `merge` subcommands.
- Tests in `tests/test_polygit.py` using real temporary git repos.
- Documentation updates in `README.md`.

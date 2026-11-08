# Design

## Context

`cmd_checkout` runs `_checkout_one` per repo in a thread pool; `_checkout_precheck` already enforces the dirty, detached, unborn, in-progress and branch-exists rules, and `_git_out` wraps `git -C <dir> ...`. The CLI rejects names that fail `valid_branch_name`, which runs `git check-ref-format --branch` and so rejects `-`. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- One command that undoes a branch switch across repos whose previous branches differ
- Reuse the existing switch rules and result format

**Non-Goals:**
- Remembering state in a pgit file (stateless; git's reflog is the source)
- `@{-N}` for N > 1, or other revision syntax
- Restoring uncommitted work, or `-` together with `-b`

## Decisions

### 1. Resolve `-` per repo with git's reflog
In `_checkout_one` and the dry-run path, when the argument is `-`, run `git -C <dir> rev-parse --abbrev-ref @{-1}` and use its output as the branch for that repo. Verified behavior: it prints the previous branch name; it prints nothing when the previous state was a detached HEAD; and it exits 128 when there is no previous entry or the branch was deleted. Empty output and a non-zero exit both mean `skipped: no previous branch`.

Alternative: store the previous branch in a `.pgit` sidecar when `checkout` runs. Rejected: extra state, wrong after manual `git checkout`, and git already tracks it.

Alternative: `git checkout -` directly. Rejected: it would bypass the precheck (dirty, in-progress) and the planned/dry-run output.

### 2. Run the resolved branch through the existing precheck
After resolving, call the same precheck and checkout with `create=False`. This keeps one set of skip rules and the `up-to-date` result when the resolved branch is already current.

### 3. Result fields
`branch` in text and JSON is the resolved branch for that repo; it is `null` only when resolution fails. `previous` stays the branch the repo was on before this command. The text line for a switch is unchanged (`switched 'feat' -> 'main'`).

### 4. Argument handling
`cli.py` skips the `valid_branch_name` check for the literal `-`. `-b` with `-` exits 2 before the config lookup. argparse already passes a lone `-` through as a positional.

## Risks / Trade-offs

[`@{-1}` can name a branch that was only briefly visited, not the one the user expects] → Same as `git checkout -`; documented in the README as "the branch each repo was on before its last switch".

[Reflog entries expire or are disabled in a repo] → Reported as `skipped: no previous branch`; nothing is changed.

[Repos switched at different times have different previous branches] → Intended; that is the point of per-repo resolution.

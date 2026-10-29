# Design

## Context

The CLI in `src/polygit/cli.py` registers subcommands and dispatches to functions in `src/polygit/repo.py`. Existing commands follow a consistent pattern: gather repos via `each_existing_repo`, filter by `only`, run in a thread pool with `--jobs`, and optionally emit JSON. `cmd_push` already implements the commit-and-push flow with interactive/`--all`/`--wip` modes; the new `commit` command reuses the commit step minus the push.

See proposal.md for motivation and scope.

## Goals / Non-Goals

**Goals:**
- Reuse the existing commit flow from `cmd_push` for `cmd_commit` (add + commit, no push).
- Add a new `cmd_merge` that runs `git merge <target>` per repo in parallel, with conflict reporting.
- Register both commands in `cli.py` with the same option conventions.

**Non-Goals:**
- No new external dependencies (pure stdlib + git subprocesses).
- No rebase or cherry-pick operations; merge only.
- No automatic conflict resolution.
- No fetching: `merge` uses the local target branch as it is.
- No selective staging for `commit`.
- No conflict prediction in `merge --dry-run`.

## Decisions

- **Shared commit step**: Extract a helper `_commit_one(d, msg)` that runs `git add -A` then `git commit -m msg` and returns a structured result `(ok, sha, error)` where `error` is the step-labelled message (`add failed — …` / `commit failed — …`). It does not print. `_commit_and_push` calls it, then pushes, and keeps emitting the same lines as today. `cmd_commit` calls it and renders either lines or JSON.
- **`commit` always stages everything**: like `push`, `commit` runs `git add -A`. Selective staging is out of scope; users who want it run `git commit` themselves.
- **Shared WIP message**: a small `_wip_message()` helper returns `WIP <YYYY-MM-DD HH:MM>` and is used by both `cmd_push` and `cmd_commit`.
- **`--json` and interactive mode**: interactive mode prompts on stdout, which would violate the `cli` rule that `--json` prints a single JSON value and nothing else. `pgit commit --json` therefore requires `--all` or `--wip`; with interactive mode (the default) it is a usage error, printed to stderr, exit status 2. The check happens before config lookup, like other argument validation.
- **Merge strategy flags**: `--no-ff` maps to `git merge --no-ff`, `--squash` to `git merge --squash`. They are mutually exclusive (argparse group, exit 2). Default is `git merge` (fast-forward when possible).
- **Merge eligibility, checked in this order per repo**: detached HEAD → skip; target branch missing locally (`git rev-parse --verify refs/heads/<target>`) → skip; target equals current branch → `up to date`; merge in progress (`MERGE_HEAD` present, via `git rev-parse -q --verify MERGE_HEAD`) → skip; dirty working tree (`is_dirty`) → skip. Skipping dirty trees avoids `git merge` refusing or interleaving with uncommitted work.
- **Local target only**: the target must exist as a local branch. `merge` never fetches, so a stale local branch merges stale content. This is documented in the README and the spec.
- **Outcome classification**: record `HEAD` before the merge, run `git merge`, then:
  - exit 0 and `HEAD` unchanged → `up to date` (also covers `--squash` with nothing to merge);
  - exit 0 and `--squash` → `squashed (staged)` (changes staged, no commit);
  - exit 0 and new `HEAD` has two parents → `merged (commit <short-sha>)`;
  - exit 0 and new `HEAD` has one parent → `merged (fast-forward)`;
  - non-zero exit and `git diff --name-only --diff-filter=U` is non-empty → `conflict: <N> file(s)`, repo left in conflict state;
  - any other non-zero exit → `failed` with the last non-empty stderr line.
  Stdout/stderr text is never parsed to detect conflicts.
- **Plan-only dry-run**: `merge --dry-run` runs the eligibility checks and lists which repos would be merged and which would be skipped, with reasons. It does not simulate the merge, so it cannot say whether the result is a fast-forward, a merge commit or a conflict, and it needs no particular git version.
- **Parallelism**: `merge` and the non-interactive `commit` modes use the existing thread pool. Interactive `commit` stays sequential (user input).
- **Regression gate**: the existing `push` tests must pass unchanged after the `_commit_one` refactor. That is the check that output lines did not drift.

## Risks / Trade-offs

- [Conflict state left on disk] → Clearly report conflict count and leave repo in merge state so the user can resolve it manually.
- [Squash merge doesn't create a commit] → Report `squashed (staged)` and document that the user must commit manually (for example with `pgit commit`).
- [Stale local target branch] → Documented; users run `pgit pull` first.
- [Dry-run gives no conflict preview] → Accepted to keep the change small and independent of git version.

## Migration Plan

No migration needed; new commands are additive. The `push` refactor is behavior-preserving.

## Open Questions

None.

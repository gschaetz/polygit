# Proposal

## Why

`pgit commit`, `push`, `review` and `merge` work across many repos, but starting a cross-repo change still means running `git checkout -b` by hand in every repo. `review` in particular only finds branches that are already pushed under their own name, so users need a quick way to create the same branch everywhere, and to switch every repo back to `main` afterwards.

## What Changes

- New command `pgit checkout <branch>` — switch every cloned repo to an existing local branch.
- `pgit checkout -b <branch>` creates the branch in every cloned repo, from each repo's current HEAD by default, or from `--from <ref>` (any local ref, including remote-tracking refs and tags).
- Never clobbers local work: switching to an existing branch, or creating from `--from`, skips repos with a dirty working tree. Plain `-b` from the current HEAD does not touch the working tree, so it is allowed on a dirty tree and the changes come along, as with `git checkout -b`.
- Per-repo outcomes are reported, and a skip or failure in one repo never stops the others: `switched`, `created`, `up-to-date`, `skipped` (with a reason), `failed`, and `planned` under `--dry-run`.
- Skips: detached HEAD, unborn repos (no commits), an operation in progress (merge, rebase, cherry-pick), a branch that does not exist (without `-b`), a branch that already exists (with `-b`), and a missing `--from` ref.
- Reads local refs only. It does not fetch, and a branch that exists only on the remote counts as not found.
- Follows existing conventions: `--only <platform>`, `--jobs N`, `--dry-run`, and `--json` (stdout is only the JSON array).

## Capabilities

### New Capabilities

- `checkout`: Bulk branch switching and creation across cloned repos. Covers eligibility and skip rules, `-b` and `--from`, dry-run, parallel execution, and JSON output.

### Modified Capabilities

- `cli`: The `checkout` subcommand must be registered with its arguments and options (`<branch>`, `-b`, `--from`, `--dry-run`, `--only`, `--jobs`, `--json`), including the usage errors for `--from` without `-b` and for an invalid branch name.

## Impact

- `src/polygit/cli.py`: register the `checkout` subcommand and validate its arguments before the config lookup.
- `src/polygit/repo.py`: new `cmd_checkout` with a precheck and a per-repo worker, modeled on `cmd_merge`.
- Tests in `tests/test_polygit.py` using real temporary git repos.
- `README.md`: a `checkout` section.
- No new dependencies. Pure stdlib plus `git`, and no minimum git version beyond what the project already assumes.

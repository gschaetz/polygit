# Design

## Context

`cmd_merge` is the closest existing command: it runs a per-repo precheck that returns a skip reason, then a per-repo worker, in a `ThreadPoolExecutor` (`--jobs`), and reports `status`/`detail` in text or as a JSON array sorted by platform and path. `each_existing_repo` yields only cloned repos and honors `--only`. `is_dirty` uses `git status --porcelain`, so untracked files count as dirty. Git state is read from local refs only — no implicit fetch.

Current structure:
- `src/polygit/cli.py` — argument parsing, validation before the config lookup, dispatch
- `src/polygit/repo.py` — `cmd_*` implementations and git helpers (`_git_out`, `is_dirty`, `_merge_precheck`)

## Goals / Non-Goals

**Goals:**
- Switch every cloned repo to an existing local branch, or create a branch everywhere with `-b` / `--from`
- Never overwrite local work, and report every repo with a reason when it is skipped
- Follow the `merge` conventions for flags, statuses, output and JSON

**Non-Goals:**
- Fetching, or creating a local tracking branch from a remote-only branch
- Setting up an upstream or pushing (that is `pgit push`)
- Stashing, forcing (`-f`) or carrying local changes across a switch
- Switching to tags or commits (detached HEAD)
- Atomicity: a failure in one repo does not roll back the others

## Decisions

### 1. One precheck, shared by dry-run and the real run

**Decision:** `_checkout_precheck(d, branch, create, start)` returns `(status, detail)` for repos that should not be changed, or `None` when eligible, like `_merge_precheck`. Order:
1. unborn (no commits): `skipped`, "no commits yet"
2. detached HEAD: `skipped`, "detached HEAD"
3. current branch equals the requested branch: `up-to-date` — checked before the dirty and exists checks so re-running is idempotent
4. merge, rebase or cherry-pick in progress: `skipped`, "operation in progress"
5. dirty working tree, when the operation would change the working tree (switch, or create with `--from`): `skipped`, "dirty working tree"
6. with `-b`: the branch already exists: `skipped`, "branch 'x' already exists"; a `--from` ref that does not resolve to a commit: `skipped`, "start point 'ref' not found"
7. without `-b`: the branch is not a local branch: `skipped`, "branch 'x' not found"

**Rationale:** `--dry-run` runs the same precheck and reports `planned` for the rest, so it cannot disagree with a real run. Putting "already on it" before the other checks makes the command safe to repeat.

**Alternative considered:** Let git decide and report its error. Rejected — git sometimes carries local changes across a switch, or silently creates a tracking branch from `origin/x`, which are exactly the surprises this command should avoid in bulk.

### 2. Dirty trees: skip, except plain `-b`

**Decision:** Skip dirty repos when the working tree may change (switching, or `-b` with `--from`). Allow plain `-b <branch>` on a dirty repo, since creating a branch at the current HEAD does not touch files, and the changes stay in the working tree as with `git checkout -b`.

**Rationale:** The main use case is "I have uncommitted work in several repos; start a feature branch for it". Skipping those repos would make `-b` useless exactly when it is needed. Operations that move files stay conservative.

**Alternative considered:** Skip every dirty repo uniformly (as `merge` does). Rejected for the reason above.

### 3. Local branches only; no remote DWIM

**Decision:** Existence is checked with `git rev-parse --verify -q refs/heads/<branch>`. A branch that exists only on the remote is "not found". The switch runs `git checkout <branch> --` after the check, so git's remote-branch guessing is never reached and a file named like the branch cannot be mistaken for it. Creating from a remote branch is explicit: `-b feat --from origin/feat`.

**Rationale:** Keeps the "no implicit fetch, local refs only" convention and avoids creating tracking branches the user did not ask for.

### 4. `--from` accepts any commit-ish, checked locally

**Decision:** The start point is resolved with `git rev-parse --verify -q <ref>^{commit}`. Remote-tracking refs and tags are accepted. It is only valid with `-b`; this is enforced in `cli.py` before the config lookup, with exit status 2.

**Rationale:** Needed for "branch off `origin/main`", the common case after `pgit sync`.

### 5. Branch name validated once, up front

**Decision:** `git check-ref-format --branch <name>` is run once before the config lookup; failure prints an error and exits with status 2. It needs no repo, so one check covers all repos.

**Rationale:** An invalid name would otherwise fail identically in every repo and report N identical `failed` lines.

### 6. Operation-in-progress detection

**Decision:** A repo counts as mid-operation when `git rev-parse --git-path` resolves an existing `MERGE_HEAD`, `CHERRY_PICK_HEAD`, `rebase-merge` or `rebase-apply`.

**Rationale:** `--git-path` handles worktrees and `.git` files, unlike joining `.git/` by hand.

### 7. Status vocabulary and JSON shape

**Decision:** Statuses are `switched`, `created`, `up-to-date`, `skipped`, `failed` and, with `--dry-run`, `planned`. JSON entries carry `platform`, `path`, `status`, `action` (`switch` or `create`), `branch`, `previous` and `detail`. Text lines use the existing symbols and read like `switched 'main' -> 'feat'`, `created 'feat' from 'main'`, `already on 'feat'`, `would create 'feat'`, `skipped: <reason>`. Exit status is 0 regardless of per-repo outcomes, as for `merge`.

**Rationale:** Mirrors `cmd_merge`; `action` is added so a `planned` entry says what would happen.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Partial result: some repos switched, others skipped | Every repo is reported with a reason; the command is idempotent, so it can be re-run after fixing the skipped ones. |
| `-b` on a dirty repo carries uncommitted work onto the new branch | Intended and documented; matches `git checkout -b`. |
| Detached HEAD repos are skipped, even when clean | Switching away can orphan commits; skipping is the safe default. Users can fix those repos by hand. |
| Branch exists but points elsewhere in some repos (`-b`) | Reported as `skipped: branch 'x' already exists`, never reset. |
| Stale remote-tracking refs for `--from origin/x` | Same as every local-only command; run `pgit sync` first. |

## Open Questions

None blocking. Possible follow-ups: `--force` for dirty trees, and `--track` to set an upstream on creation.

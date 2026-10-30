# Tasks

## 1. CLI Integration

- [x] 1.1 Add the `checkout` subcommand to `src/polygit/cli.py` with a positional `branch`, `-b` (create), `--from REF`, `--dry-run`, `--json`, `--only` and `--jobs` — verify `pgit --help` lists `checkout` and `pgit checkout --help` shows each option
- [x] 1.2 Before the config lookup, exit 2 with a usage error when `--from` is given without `-b` — verify with `_run_main`
- [x] 1.3 Before the config lookup, validate the branch name with `git check-ref-format --branch` and exit 2 with an error when it is invalid — verify with a name like `bad..name`
- [x] 1.4 Wire `checkout` to a new `cmd_checkout` in `repo.py` — verify dispatch with `pgit checkout main --dry-run`

## 2. Core Logic

- [x] 2.1 Add `_operation_in_progress(d)` in `repo.py` using `git rev-parse --git-path` for `MERGE_HEAD`, `CHERRY_PICK_HEAD`, `rebase-merge` and `rebase-apply` — verify with a repo mid-merge and a repo mid-rebase
- [x] 2.2 Add `_checkout_precheck(d, branch, create, start)` returning `(status, detail)` or `None`, in the order given in the design (unborn, detached, already on branch, operation in progress, dirty when the working tree would change, exists / start point missing / branch missing) — verify one case per branch of the logic
- [x] 2.3 Add `_checkout_one(d, branch, create, start)` that runs `git checkout <branch> --` or `git checkout -b <branch> [<start>]`, and returns `(status, detail, previous)`; map a git failure to `failed` with the last error line — verify `switched`, `created` and a forced `failed`
- [x] 2.4 Ensure a branch that exists only on the remote is `skipped: branch 'x' not found` and never creates a local branch — verify with a bare origin that has an extra branch

## 3. Reporting, Dry Run and JSON

- [x] 3.1 Implement `cmd_checkout(config, base, branch, create=False, start=None, dry_run=False, only=None, jobs=None, json_output=False)` modeled on `cmd_merge`: run the precheck then the worker in a `ThreadPoolExecutor`, print one line per repo, and print `No cloned repos found.` when there are none — verify text output for each status
- [x] 3.2 `--dry-run` runs the same precheck, reports `planned` (`would switch` / `would create`) for eligible repos, and changes nothing — verify branches, HEAD and the working tree are untouched
- [x] 3.3 `--json` prints a single array sorted by platform and path with `platform`, `path`, `status`, `action`, `branch`, `previous` and `detail`; stdout holds nothing else; `[]` when no repo is cloned — verify by parsing stdout in a real (non-dry-run) run

## 4. Common Options

- [x] 4.1 `--only <platform>` filters through `each_existing_repo` — verify with repos under two platforms
- [x] 4.2 `--jobs N` limits concurrency — verify the peak concurrency never exceeds N

## 5. Tests

- [x] 5.1 Add tests in `tests/test_polygit.py` for every scenario in the `checkout` and `cli` delta specs, using real temp git repos with a bare remote — verify `pytest tests/test_polygit.py -k checkout` passes
- [x] 5.2 Include tests that fail if the logic is broken, not just that run: dirty plain `-b` keeps the uncommitted file, dirty switch is skipped and the file survives, remote-only branch is not created, `-b` on an existing branch does not move it, and re-running is idempotent
- [x] 5.3 After writing the tests, temporarily break the dirty check and the JSON stdout handling and confirm tests fail, then restore

## 6. Documentation

- [x] 6.1 Add a `checkout` section to `README.md` (usage examples for switch, `-b`, `--from`, `--dry-run`, `--json`; the dirty-tree rule; local refs only) — verify the examples match the real behavior

## 7. Verification

- [x] 7.1 Run the full suite: `pytest tests/test_polygit.py` — all tests pass
- [x] 7.2 Run `openspec validate pgit-checkout --strict`
- [x] 7.3 Manual smoke test in temp repos: create a branch everywhere with a dirty repo, switch back, re-run to confirm idempotency — verify the output and that no local changes are lost

## Workflow follow-up

- Archive the change after implementation is complete and verified: `openspec archive pgit-checkout --yes`
- Verify the archived result by checking `openspec/specs/checkout/spec.md` exists and matches the delta

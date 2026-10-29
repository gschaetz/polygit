# Tasks

## 1. Shared commit helpers in repo.py

- [x] 1.1 Extract `_commit_one(d, msg)` that runs `git add -A` then `git commit -m msg`, prints nothing, and returns a structured result `(ok, sha, error)` where `error` reads `add failed — …` or `commit failed — …`. Verify with a unit test against a real temp repo.
- [x] 1.2 Update `_commit_and_push` to call `_commit_one`, then `git push` on success, emitting exactly the same lines as before. Verify the existing push tests pass unchanged (regression gate).
- [x] 1.3 Add `_wip_message()` returning `WIP <YYYY-MM-DD HH:MM>` and use it in `cmd_push`. Verify the existing WIP push test still passes.

## 2. Implement `cmd_commit` in repo.py

- [x] 2.1 Add `cmd_commit(config, base, mode, dry_run, only, jobs, json_output=False)` mirroring `cmd_push` without the push step, with interactive/all/wip modes, using `_commit_one`. Verify `pgit commit --wip` commits and does not push.
- [x] 2.2 Handle `--dry-run` to list dirty repos without committing.
- [x] 2.3 Implement `--json` output (platform, path, status committed/failed, message, sha, error), printing `[]` when nothing is dirty and printing nothing else to stdout.
- [x] 2.4 Add tests in `tests/test_polygit.py`, using real temporary git repos like the existing suite, for: nothing dirty, interactive skip, `--all`, `--wip`, no push, add/commit failure, dry-run, JSON output, empty JSON. Verify with `uv run pytest tests/test_polygit.py -k commit`.

## 3. Register `commit` in cli.py

- [x] 3.1 Add the `commit` subparser with `--interactive/--all/--wip`, `--dry-run`, `--json`, `--only`, `--jobs`.
- [x] 3.2 Reject `--json` without `--all` or `--wip` as a usage error (stderr, exit 2) before config lookup.
- [x] 3.3 Add the dispatch entry calling `cmd_commit`. Verify `pgit commit --help` and `pgit commit --wip`.

## 4. Implement `cmd_merge` in repo.py

- [x] 4.1 Add a per-repo eligibility check returning a skip reason or none, in order: detached HEAD, target branch missing locally, target equals current branch (up to date), merge in progress, dirty working tree.
- [x] 4.2 Add a merge runner for one repo: build the `git merge` command for default/`--no-ff`/`--squash`, record `HEAD` before, run, and classify the result (up to date, fast-forward, merge commit via parent count, squashed (staged), conflict via exit code plus `git diff --name-only --diff-filter=U`, failed).
- [x] 4.3 Add `cmd_merge(config, base, target, no_ff, squash, dry_run, only, jobs, json_output=False)` running repos through the thread pool and printing one outcome line per repo.
- [x] 4.4 Implement plan-only `--dry-run`: list repos that would be merged and repos that would be skipped with reasons, changing nothing.
- [x] 4.5 Implement `--json` output (platform, path, status, strategy, detail, conflict_files; `planned` under `--dry-run`), printing `[]` when there are no repos.
- [x] 4.6 Add tests in `tests/test_polygit.py`, using real temporary git repos, for: fast-forward, merge commit, `--no-ff`, `--squash`, conflict, up to date, detached HEAD skip, missing target branch, dirty tree skip, merge in progress skip, target equals current, other git error, dry-run, JSON output. Verify with `uv run pytest tests/test_polygit.py -k merge`.

## 5. Register `merge` in cli.py

- [x] 5.1 Add the `merge` subparser with positional `target_branch`, a mutually exclusive `--no-ff`/`--squash` group, `--dry-run`, `--json`, `--only`, `--jobs`. Verify `pgit merge --help`, and that a missing branch or both flags exit with status 2.
- [x] 5.2 Add the dispatch entry calling `cmd_merge`. Verify `pgit merge main` runs.

## 6. Documentation

- [x] 6.1 Update `README.md` with `pgit commit` and `pgit merge` usage, options and examples, noting that `merge` uses the local target branch and does not fetch, and that `--squash` leaves changes staged.

## 7. Verification and spec sync

- [x] 7.1 Run the full suite: `uv run pytest tests/`. All tests pass, including the unchanged push tests.
- [x] 7.2 Manual smoke test in a temp `.pgit` with 2-3 repos: `pgit commit --wip`, `pgit commit --wip --json`, `pgit merge main`, `--no-ff`, `--squash`, `--dry-run`, `--json`.
- [x] 7.3 Add `commit` and `merge` to `openspec/specs/` (for example with `/opsx:sync` or on archive) so the main specs match the delta specs.

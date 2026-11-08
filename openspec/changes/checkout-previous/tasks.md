# Tasks

Apply one section at a time. Check each `Verify:` result before ticking the box. Commands run from the repo root unless a `cd` is shown. `PG=/Users/gschaetz/development/github/gschaetz/polygit/.venv/bin/pgit` must be set in the shell before any `$PG` command, in every section.

## 1. Resolve and switch (`src/polygit/repo.py`)

- [x] 1.1 Create the scratch tree used by every later check: two repos on different default branches, each switched once so a previous branch exists
   Run:
   ```
   rm -rf /tmp/pgit-co-demo && mkdir -p /tmp/pgit-co-demo/github /tmp/pgit-co-demo/gitlab && cd /tmp/pgit-co-demo
   printf 'github:\n  a:\ngitlab:\n  b:\n  c:\n' > .pgit
   git init -q -b main github/a; git init -q -b master gitlab/b; git init -q -b main gitlab/c
   for r in github/a gitlab/b gitlab/c; do git -C $r commit -q --allow-empty -m init; done
   for r in github/a gitlab/b; do git -C $r checkout -q -b feat; done
   ```
   Verify: `for r in github/a gitlab/b gitlab/c; do git -C /tmp/pgit-co-demo/$r branch --show-current; done | tr '\n' ' '` prints `feat feat main `

- [x] 1.2 Add `_previous_branch(d)` to `src/polygit/repo.py` returning the output of `git rev-parse --abbrev-ref @{-1}`, or `None` when git exits non-zero or prints nothing
   Verify: `.venv/bin/python -c "from pathlib import Path; from polygit.repo import _previous_branch as p; r=Path('/tmp/pgit-co-demo'); print(p(r/'github/a'), p(r/'gitlab/b'), p(r/'gitlab/c'))"` prints `main master None`

- [x] 1.3 Make `_checkout_one` and `cmd_checkout`'s dry-run path accept branch `-`: resolve it with `_previous_branch`, return `skipped` / `no previous branch` (with `branch` `None` in the result entry) when unresolved, otherwise continue with the resolved branch through the existing precheck and checkout
   Verify: `.venv/bin/python -c "from pathlib import Path; from polygit.repo import _checkout_one as c; r=Path('/tmp/pgit-co-demo'); print(c(r/'gitlab/c','-',False,None)[:2], c(r/'github/a','-',False,None)[:2], c(r/'github/a','-',False,None)[:2])"` prints `('skipped', 'no previous branch') ('switched', '') ('switched', '')`

- [x] 1.4 Add tests to `tests/test_polygit.py` for: restoring a mixed `main`/`master` tree, toggling twice, no previous branch, previous branch deleted, previous state detached, dirty repo skipped, and already-on-branch `up-to-date`
   Verify: `.venv/bin/python -m pytest tests/test_polygit.py -q -k "checkout and previous"` exits 0 and reports at least 7 passed

- [x] 1.5 Section check: full suite still passes
   Verify: `.venv/bin/python -m pytest tests/test_polygit.py -q` exits 0 with no failures

## 2. CLI, output and docs (`src/polygit/cli.py`, `README.md`)

- [ ] 2.1 Re-create the scratch tree from task 1.1 (run its `Run:` block again) so this section stands alone, then let `cli.py` skip the `valid_branch_name` check for the literal `-` and reject `-b -` with a stderr error and exit status 2 before the config lookup
   Verify: `cd / && $PG checkout -b -; echo $?` prints an error on stderr (no `.pgit` error) then `2`, and `cd / && $PG checkout bad..name; echo $?` still prints an error then `2`

- [ ] 2.2 Real CLI path: restore the mixed tree and check text, dry-run and JSON output
   Verify: `cd /tmp/pgit-co-demo && $PG checkout - --dry-run` prints `would switch to 'main'` for `github/a`, `would switch to 'master'` for `gitlab/b` and `skipped: no previous branch` for `gitlab/c`, and `git -C github/a branch --show-current` still prints `feat`
   Verify: `cd /tmp/pgit-co-demo && $PG checkout - --json | python3 -c "import sys,json; print([(r['path'], r['status'], r['branch']) for r in json.load(sys.stdin)])"` prints `[('a', 'switched', 'main'), ('b', 'switched', 'master'), ('c', 'skipped', None)]` (paths as printed by `pgit`)
   Verify: `cd /tmp/pgit-co-demo && for r in github/a gitlab/b gitlab/c; do git -C $r branch --show-current; done | tr '\n' ' '` prints `main master main `

- [ ] 2.3 Add tests for `-b -` exiting 2 before the config lookup, `-` not rejected as an invalid name, `--dry-run` changing nothing, and the JSON `branch` values (`null` when skipped)
   Verify: `.venv/bin/python -m pytest tests/test_polygit.py -q -k "checkout and previous"` exits 0 and reports at least 11 passed

- [ ] 2.4 Document `pgit checkout -` in the `## checkout` section of `README.md`: an example, "the branch each repo was on before its last switch", the `no previous branch` skip, and that `-` cannot be used with `-b`
   Verify: `grep -c '^pgit checkout - ' README.md` prints `1` and `grep -c 'no previous branch' README.md` prints at least `1`

- [ ] 2.5 Section check: full suite and help output
   Verify: `.venv/bin/python -m pytest tests/test_polygit.py -q` exits 0 with no failures, and `$PG checkout --help | grep -c BRANCH` prints at least `1`

## Workflow follow-up

- Archive the change after every box above is ticked: `openspec archive checkout-previous --yes`
- Confirm with `openspec show checkout --type spec --no-scenarios`

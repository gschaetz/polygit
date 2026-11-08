# Tasks

Apply one section at a time. Check each `Verify:` result before ticking the box. Commands run from the repo root unless a `cd` is shown. In section 2 onward, `PG=/Users/gschaetz/development/github/gschaetz/polygit/.venv/bin/pgit` must be set in the shell first.

## 1. Reading and merging commits (`src/polygit/log.py`)

- [x] 1.1 Create the scratch tree used by every later check
   Run:
   ```
   rm -rf /tmp/pgit-log-demo && mkdir -p /tmp/pgit-log-demo/github /tmp/pgit-log-demo/gitlab && cd /tmp/pgit-log-demo
   printf 'github:\n  a:\n  b:\ngitlab:\n  c:\n' > .pgit
   for r in github/a github/b gitlab/c; do git init -q $r; done
   c() { GIT_AUTHOR_NAME="$2" GIT_AUTHOR_EMAIL="$2@example.com" GIT_COMMITTER_NAME="$2" GIT_COMMITTER_EMAIL="$2@example.com" GIT_AUTHOR_DATE="$3" GIT_COMMITTER_DATE="$3" git -C "$1" commit -q --allow-empty -m "$4"; }
   c github/a Ann 2026-01-01T10:00:00Z a1; c github/b Bob 2026-01-02T10:00:00Z b1; c github/a Ann 2026-01-03T10:00:00Z a2
   ```
   Verify: `git -C /tmp/pgit-log-demo/github/a log --format=%s | tr '\n' ' '` prints `a2 a1 `, and `git -C /tmp/pgit-log-demo/gitlab/c log` exits 128 (repo `c` has no commits)

- [x] 1.2 Implement `read_commits(d, limit, since=None, author=None)` in `src/polygit/log.py` returning a list of dicts with `hash`, `author`, `timestamp`, `date`, `subject`; return `[]` when `limit == 0` (no git call) or when git exits non-zero
   Verify: `.venv/bin/python -c "from pathlib import Path; from polygit.log import read_commits as r; print([c['subject'] for c in r(Path('/tmp/pgit-log-demo/github/a'), 20)])"` prints `['a2', 'a1']`
   Verify: `.venv/bin/python -c "from pathlib import Path; from polygit.log import read_commits as r; print(r(Path('/tmp/pgit-log-demo/gitlab/c'), 20), r(Path('/tmp/pgit-log-demo/github/a'), 0))"` prints `[] []`

- [x] 1.3 Pass `--fixed-strings --regexp-ignore-case` with `--author`, and `--since` unchanged
   Verify: `.venv/bin/python -c "from pathlib import Path; from polygit.log import read_commits as r; d=Path('/tmp/pgit-log-demo/github/a'); print(len(r(d,20,author='ANN')), len(r(d,20,author='a.n')), len(r(d,20,since='2026-01-02')))"` prints `2 0 1`

- [x] 1.4 Implement `merge_commits(per_repo, limit)` (sort by timestamp desc, then path, then hash; slice to `limit`) and `collect_commits(config, base, limit, since, author, only, jobs)` (uses `each_existing_repo` and a thread pool; adds `name`, `path`, `platform` to each commit)
   Verify: `.venv/bin/python -c "import os; os.chdir('/tmp/pgit-log-demo'); from pathlib import Path; from polygit.config import load_config; from polygit.log import collect_commits as c; print([x['subject'] for x in c(load_config('.pgit'), Path('.').resolve(), 20, None, None, None, None)])"` prints `['a2', 'b1', 'a1']`

- [x] 1.5 Section check: run the module path end to end
   Verify: `.venv/bin/python -c "import os; os.chdir('/tmp/pgit-log-demo'); from pathlib import Path; from polygit.config import load_config; from polygit.log import collect_commits as c; print(len(c(load_config('.pgit'), Path('.').resolve(), 2, None, None, 'github', None)), len(c(load_config('.pgit'), Path('.').resolve(), 20, None, None, 'gitlab', None)))"` prints `2 0`

## 2. CLI and `cmd_log`

- [x] 2.1 Add `_since_value` to `src/polygit/cli.py` (accepts `YYYY-MM-DD` as a real date, or `N.unit` / `N unit`; otherwise `argparse.ArgumentTypeError`)
   Verify: `.venv/bin/python -c "from polygit.cli import _since_value as s; print(s('2.weeks'), s('3 days'), s('2026-01-02'))"` prints `2.weeks 3 days 2026-01-02`
   Verify: `.venv/bin/python -c "from polygit.cli import _since_value as s; import argparse\nfor v in ('bogus','2026-02-30','0.weeks.ago'):\n    try: s(v); print('ok', v)\n    except argparse.ArgumentTypeError: print('bad', v)"` prints `bad bogus`, `bad 2026-02-30`, `bad 0.weeks.ago`

- [x] 2.2 Add the `log` subparser (`--limit` via `_non_negative_int` default 20, `--since`, `--author`, `--only`, `--json`, `--jobs`) and dispatch to `cmd_log`
   Verify: `$PG --help | grep -c ' log '` prints `1`

- [x] 2.3 Implement `cmd_log(config, base, limit, since, author, only, jobs, json_output)` in `src/polygit/repo.py`: text line `<hash> <date> <name> (<author>) <subject>`, JSON array with keys `name`, `path`, `platform`, `hash`, `author`, `date`, `subject`, nothing printed (text) or `[]` (JSON) when empty
   Verify: `cd /tmp/pgit-log-demo && $PG log | awk '{print $2, $3}' | head -1` prints `2026-01-03T10:00:00+00:00 a`
   Verify: `cd /tmp/pgit-log-demo && $PG log --json | python3 -c "import sys,json; d=json.load(sys.stdin); print([c['subject'] for c in d], sorted(d[0]))"` prints `['a2', 'b1', 'a1'] ['author', 'date', 'hash', 'name', 'path', 'platform', 'subject']`

- [x] 2.4 Section check: argument errors, filters and empty output through the real CLI
   Verify: `cd /tmp/pgit-log-demo && $PG log --limit 1 --json | python3 -c "import sys,json; print([c['subject'] for c in json.load(sys.stdin)])"` prints `['a2']`
   Verify: `cd /tmp/pgit-log-demo && $PG log --limit 0 --json` prints `[]`, and `$PG log --limit 0` prints nothing
   Verify: `cd /tmp/pgit-log-demo && $PG log --author bob --json | python3 -c "import sys,json; print([c['subject'] for c in json.load(sys.stdin)])"` prints `['b1']`
   Verify: `cd /tmp/pgit-log-demo && $PG log --only gitlab --json` prints `[]`
   Verify: `cd / && $PG log --since bogus; echo $?` prints a usage error on stderr then `2`, and `cd / && $PG log --limit -1; echo $?` prints a usage error then `2` (no `.pgit` error appears)

## 3. Tests (`tests/test_polygit.py`)

- [ ] 3.1 Add a fixture building the same three repos with fixed dates, and tests for ordering across repos, equal-date tie-break, repo with no commits, uncloned repo skipped, and no fetch (commits only on the remote are not listed)
   Verify: `.venv/bin/python -m pytest tests/test_polygit.py -q -k log` exits 0 and reports these tests passed

- [ ] 3.2 Add tests for `--limit` (2, default 20 with 25 commits, 0), `--since` (date and relative), `--author` (name, email, case, literal `a.n`), `--only`, `--json` keys and `[]`, text line format, and exit-2 errors for invalid `--limit` and `--since` before the config lookup
   Verify: `.venv/bin/python -m pytest tests/test_polygit.py -q -k log` exits 0 and the number of passed tests is at least 14

- [ ] 3.3 Section check: full suite
   Verify: `.venv/bin/python -m pytest tests/test_polygit.py -q` exits 0 with no failures

## 4. Documentation

- [ ] 4.1 Add a `## log` section to `README.md` with examples for `--limit`, `--since`, `--author`, `--only` and `--json`, stating that it reads local refs only (no fetch)
   Verify: `grep -c '^## log' README.md` prints `1`, and `grep -c 'pgit log' README.md` prints at least `4`

- [ ] 4.2 Update `docs/roadmap.md`: list `pgit search` and `pgit log` under "Shipped" and remove their lines from "Repo discovery & navigation"
   Verify: `grep -c 'pgit log\|pgit search' docs/roadmap.md` prints `1` (only the Shipped line)

- [ ] 4.3 Section check: docs match the real CLI
   Verify: `$PG log --help | grep -c -e --since -e --author -e --limit` prints `3`

## Workflow follow-up

- Archive the change after every box above is ticked: `openspec archive pgit-log --yes`
- Confirm with `openspec show log --type spec --no-scenarios`

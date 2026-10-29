# Tasks

## 1. CLI Integration

- [x] 1.1 Add `review` subcommand to `src/polygit/cli.py` with arguments: `--all`, `--auto` (mutually exclusive; no mode flag means interactive), `--base <branch>`, `--dry-run`, `--only`, `--jobs`, `--json` — verify `pgit --help` shows the new command and `--all --auto` exits 2
- [x] 1.2 Wire `review` to a new `cmd_review` function in `repo.py` — verify dispatch works by running `pgit review --dry-run` (prints "No branches to review." when no eligible repos)

## 2. Core Logic — Repo Detection

- [x] 2.1 Add `_resolve_base(d, remote, base)` helper in `repo.py`: return `--base` if given, else the remote's default branch via `git symbolic-ref --short refs/remotes/<remote>/HEAD`, falling back to `<remote>/main` then `<remote>/master` (`git rev-parse --verify`); return `None` if unresolved — verify with fixtures that have `origin/HEAD`, only `main`, only `master`, and none
- [x] 2.2 Add `_get_review_candidates(config, base, only)` helper in `repo.py` that, per repo from `each_existing_repo`, uses `_get_branch_info` and keeps repos with `state == "tracking"`, an upstream named `<remote>/<branch>`, a branch different from the base, and `git rev-list --count <remote>/<base>..<remote>/<branch>` > 0 — verify against fixtures: on base branch, upstream name differs, no commits ahead of base, no upstream, detached HEAD
- [x] 2.3 Flag candidates whose branch is also `ahead > 0` of its own upstream and print a warning that those commits will not be in the PR — verify the warning appears and the repo stays in the list
- [x] 2.4 Report repos whose base cannot be resolved as `failed` with an error suggesting `--base`, without stopping others — verify with a fixture lacking `origin/HEAD`, `main` and `master`
- [x] 2.5 Handle "no candidates" case: print "No branches to review." and exit cleanly — verify with `pgit review --dry-run` on clean workspace

## 3. Platform API Clients (stdlib only)

- [x] 3.1 Implement `_github_create_pr(token, owner, repo, title, body, head, base)` using `urllib.request` — POST to `https://api.github.com/repos/{owner}/{repo}/pulls`; return PR URL or raise with error details — verify with a mocked test using `unittest.mock`
- [x] 3.2 Implement `_gitlab_create_mr(token, project_path, title, body, source_branch, target_branch)` using `urllib.request` — POST to `https://gitlab.com/api/v4/projects/{url_encoded_project_path}/merge_requests` (e.g. `group%2Fsub%2Frepo`, via `urllib.parse.quote(path, safe="")`); return MR URL or raise — verify with mocked test, including a subgroup path
- [x] 3.3 Add `_parse_remote_url(remote_url)` helper to extract `(host, path)` from SSH (`git@host:owner/repo.git`) and HTTPS (`https://host/owner/repo.git`) formats, where `path` keeps subgroups and drops `.git`; GitHub callers split it into owner/repo — verify with test cases for GitHub/GitLab, including subgroups

## 4. Review Modes Implementation

- [x] 4.1 Implement `--auto` mode: generate title from branch name (kebab/snake_case → conventional: `feat/auth` → `feat: auth`), body with branch + commit count — verify title generation with test cases
- [x] 4.2 Implement `--all` mode: prompt once for title/body (blank title aborts), apply to all candidates — verify interactive prompt works and blank aborts
- [x] 4.3 Implement default interactive mode: per-repo prompt with diff summary (`git diff --stat <remote>/<base>...<remote>/<branch>`), blank title skips repo — verify sequential handling and skip behavior

## 5. Dry Run & JSON Output

- [x] 5.1 Implement `--dry-run`: list candidates with planned titles and fallback URLs, no API calls; in interactive mode show a `<prompted>` placeholder instead of a title and show no prompts — verify output format matches spec scenarios
- [x] 5.2 Implement `--json` output: array of objects with `platform`, `path`, `branch`, `status` (`created`/`planned`/`failed`), `url`, `error`; require `--all` or `--auto` — verify JSON is valid and only on stdout; verify error on `--json` without `--all/--auto`

## 6. Parallelism & Common Options

- [x] 6.1 Apply `--jobs` to non-interactive modes (`--all`, `--auto`) via `ThreadPoolExecutor`; interactive stays sequential — verify with `--auto --jobs 2` processes at most 2 concurrently
- [x] 6.2 Apply `--only <platform>` filter to candidate detection — verify `pgit review --only github` only considers GitHub repos
- [x] 6.3 Apply `--base` to eligibility, API calls and fallback URLs — verify `--base release` targets `release` everywhere

## 7. Error Handling & Fallback

- [x] 7.1 On API failure (401, 403, 422, 429, network error): report error on repo's line, print fallback URL, continue other repos — verify with mocked 401/422 responses, including 422 "PR exists"
- [x] 7.2 Fallback URL construction using the resolved base: GitHub compare URL, GitLab new MR URL with pre-filled source and target branches — verify URL format for both platforms
- [x] 7.3 Token discovery: check `GH_TOKEN`/`GITHUB_TOKEN` for GitHub, `GITLAB_TOKEN`/`GL_TOKEN` for GitLab; if missing, use fallback URL — verify env var priority

## 8. Tests

- [x] 8.1 Add tests in `tests/test_polygit.py` for all spec scenarios, in both the `review` and `cli` delta specs (use temp git repos with a bare remote so `origin/<branch>` and `origin/HEAD` exist, mock `urllib.request.urlopen`) — verify `pytest tests/test_polygit.py -k review` passes
- [x] 8.2 Test JSON output structure matches spec — verify `pgit review --auto --json` outputs valid JSON array
- [x] 8.3 Test the unpushed-commits warning and unresolved-base failure — verify both appear and other repos continue

## 9. Documentation

- [x] 9.1 Update `README.md` with `pgit review` usage section (detection rule, `--base`, modes, options, examples, env vars, token scopes, note that branches must be pushed first) — verify rendered examples match actual command behavior

## 10. Integration Verification

- [x] 10.1 Run full test suite: `pytest tests/test_polygit.py` — all tests pass
- [ ] 10.2 Manual smoke test: create temp multi-repo setup, push feature branches, run `pgit review --auto --dry-run`, then `pgit review --auto` with tokens — verify PRs created against the default branch

## Workflow follow-up

- Archive the change after implementation is complete and verified: `openspec archive pgit-review --yes`
- Verify the archived result by checking `openspec/specs/review/spec.md` exists and matches the delta

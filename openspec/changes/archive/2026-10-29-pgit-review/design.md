# Design

## Context

The codebase uses pure stdlib with `subprocess` for git operations. Per-repo work runs in a `ThreadPoolExecutor` (default 8 workers via `--jobs`). Machine-readable output (`--json`) prints only JSON to stdout. Git state is read from local refs only — no implicit fetch. The existing `_get_branch_info` helper returns the current branch, its upstream, ahead/behind counts and a tracking state from local refs.

A PR only contains commits that are on the remote. So "review candidates" are branches that are already pushed and differ from the default branch — not branches with unpushed commits.

Current structure:
- `src/polygit/cli.py` — argument parsing, command dispatch
- `src/polygit/repo.py` — all git operations, command implementations (`cmd_*`)
- `src/polygit/config.py` — config discovery/loading, `HOSTS` dict for SSH URLs

## Goals / Non-Goals

**Goals:**
- Implement `pgit review` command with interactive, `--all`, and `--auto` modes
- Detect repos whose current branch is pushed under the same name and is ahead of the default branch
- Resolve the PR base from the remote's default branch, overridable with `--base`
- Create PRs via GitHub/GitLab REST APIs when tokens are available
- Fall back to printing PR URLs when no token
- Support `--dry-run`, `--only`, `--jobs`, `--json` per existing conventions
- Follow existing patterns for parallelism, error handling, JSON output

**Non-Goals:**
- OAuth/web auth flow (users provide tokens via env vars)
- PR review/approval workflow (creation only)
- Fetching from remotes (works from local state like `branches`)
- Pushing branches (run `pgit push` first)
- Editing existing PRs (create new only)
- Cross-platform PR (each repo uses its own platform)

## Decisions

### 1. Candidate detection from local refs

**Decision:** A repo is a candidate when all of the following hold, using `_get_branch_info` plus `git rev-list`:
- `state == "tracking"` (not detached, no upstream, or gone)
- the upstream is `<remote>/<branch>` — the same branch name as the local branch
- the branch is not the base branch
- `git rev-list --count <remote>/<base>..<remote>/<branch>` is greater than 0

If `ahead > 0` against its own upstream (unpushed commits), the repo is still a candidate but a warning is printed and recorded: those commits will not be in the PR.

**Rationale:** A PR is built from the remote branch, so the count must be taken against the upstream ref, not the local branch. Same-name upstream avoids treating `feat/x` tracking `origin/main` as reviewable. Whether a PR already exists is not knowable from local refs; the API reports it (see Risks).

**Alternative considered:** Treat `ahead > 0` of upstream as the candidate signal (the original draft). Rejected — those are exactly the commits a PR would not contain, and a branch tracking its same-named upstream with nothing unpushed would be skipped even though it needs a PR.

### 2. Base branch resolution

**Decision:** The base is `--base <branch>` when given, otherwise the remote's default branch: `git symbolic-ref --short refs/remotes/<remote>/HEAD`, falling back to `<remote>/main` then `<remote>/master` (checked with `git rev-parse --verify`). `<remote>` is the remote part of the branch's upstream. If no base can be resolved, that repo is reported as `failed` with a message suggesting `--base`.

**Rationale:** Using the upstream as base would make head and base the same branch for a normal feature branch. `origin/HEAD` is set by `git clone`, so local-only resolution works for typical repos.

**Alternative considered:** Ask the platform API for the default branch. Rejected — needs a token and a network call, breaking the dry-run and fallback modes.

### 3. Platform API clients using stdlib only

**Decision:** Use `urllib.request` (stdlib) for GitHub/GitLab API calls. No `requests` dependency. GitLab calls use the URL-encoded `namespace/project` path as the `:id` (e.g. `group%2Fsub%2Frepo`), so no separate project-id lookup is needed and subgroups work.

**Rationale:** Keeps zero external dependencies. `urllib` is verbose but sufficient for simple POST requests. The project explicitly avoids non-stdlib deps.

**Alternative considered:** Add `requests` as optional dependency. Rejected — violates project constraint (stdlib only).

### 4. Token discovery via environment variables

**Decision:** Check `GH_TOKEN` / `GITHUB_TOKEN` for GitHub; `GITLAB_TOKEN` / `GL_TOKEN` for GitLab. No config file storage.

**Rationale:** Matches common CI patterns (GitHub Actions, GitLab CI). Avoids secrets in config files. Users can set in shell profile.

**Alternative considered:** `.pgit` config with token fields. Rejected — security risk, not needed for CI use case.

### 5. Auto title generation from branch name

**Decision:** Convert kebab/snake_case branch names to conventional commit style: `feat/auth` → `feat: auth`, `fix/login-bug` → `fix: login bug`.

**Rationale:** Useful default for `--auto` mode. Simple heuristic, no LLM needed.

**Alternative considered:** Use first commit message as title. Rejected — requires extra git call, less predictable.

### 6. PR URL construction for fallback

**Decision:** Parse the upstream remote's URL (`git remote get-url <remote>`) to extract host and path, then construct the web URL using the resolved base:
- GitHub: `https://github.com/{owner}/{repo}/compare/{base}...{head}?expand=1`
- GitLab: `https://gitlab.com/{path}/-/merge_requests/new?merge_request[source_branch]={head}&merge_request[target_branch]={base}`

**Rationale:** Works without API.

**Alternative considered:** Always require API. Rejected — users without tokens still need the workflow.

### 7. JSON output structure

**Decision:** Mirror `cmd_commit`/`cmd_merge` pattern: array of objects with `platform`, `path`, `branch`, `status` (`created` when a PR was created via the API, `manual` when no token was available and only a URL was provided, `planned` under `--dry-run`, or `failed`), `url`, `error`.

**Rationale:** Consistent with existing commands. Consumers can parse uniformly.

### 8. Interactive mode stays sequential

**Decision:** Like `push`/`commit`, interactive mode processes repos one at a time (no `--jobs` parallelism) because it prompts per repo. In interactive `--dry-run`, titles are not known, so the output shows a `<prompted>` placeholder.

**Rationale:** User input cannot be parallelized. Non-interactive modes (`--all`, `--auto`) use thread pool.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| API rate limits (GitHub: 5000/hr, GitLab: varies) | `--jobs` default 8 is conservative; users can lower. Print warning if 429 received. |
| Token scopes insufficient (needs `repo` for GitHub, `api` for GitLab) | Document required scopes in README. Fail gracefully with clear error. |
| PR already exists for branch | Not detectable locally. API returns 422/409; catch and report as `failed` with "PR exists" error, print fallback URL. |
| Local remote-tracking refs are stale (no fetch) | Same as `pgit branches`; documented. A stale `origin/HEAD` or upstream may misreport candidates. |
| Branch has unpushed commits | Warn that they will not be in the PR; suggest `pgit push`. |
| Remote URL parsing edge cases (subgroups, enterprise hosts) | Parse SSH `git@host:path.git` and HTTPS `https://host/path.git`. Fallback to printing raw remote if parse fails. |
| Large diffs in interactive mode | Show only `git diff --stat <remote>/<base>...<remote>/<branch>` summary, not full diff. |
| Default branch cannot be resolved | Report that repo as `failed` and suggest `--base`. |

## Open Questions

1. **Enterprise GitHub/GitLab hosts:** The `HOSTS` dict only has `github.com` and `gitlab.com`. If users configure custom hosts in `.pgit`, the API endpoint would need to be derived. For now, assume standard hosts; enterprise support can be a follow-up.

2. **GitLab API version:** Use v4 (`/api/v4/...`). Hardcoded for now; GitLab is stable on v4.

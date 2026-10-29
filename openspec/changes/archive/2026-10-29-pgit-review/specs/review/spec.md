# Spec Delta

## Purpose

Open pull/merge requests for repos whose current branch is pushed and ahead of the default branch, using platform APIs when authenticated or printing ready-to-click URLs as a fallback.

## ADDED Requirements

### Requirement: Only pushed branches ahead of the base

`pgit review` SHALL act only on cloned repos whose current branch is not the base branch, tracks an upstream branch with the same name, and whose upstream has commits not present in the base branch. Only local refs are read; nothing is fetched.

#### Scenario: Nothing to review
- **WHEN** no cloned repo qualifies
- **THEN** the command prints `No branches to review.`

#### Scenario: Branch with no commits ahead of base
- **WHEN** a cloned repo's upstream branch has no commits beyond the base branch
- **THEN** that repo is not included in the review list

#### Scenario: Base branch skipped
- **WHEN** a cloned repo is on the base branch itself
- **THEN** that repo is not included in the review list

#### Scenario: Upstream name differs
- **WHEN** a cloned repo's branch tracks an upstream branch with a different name (e.g. `feat/x` tracking `origin/main`)
- **THEN** that repo is not included in the review list

#### Scenario: Repo without upstream skipped
- **WHEN** a cloned repo's branch has no upstream configured, or its upstream is gone
- **THEN** that repo is not included in the review list

#### Scenario: Detached HEAD skipped
- **WHEN** a cloned repo is in detached HEAD state
- **THEN** that repo is not included in the review list

#### Scenario: Unpushed commits warned
- **WHEN** an otherwise eligible repo's branch also has commits not yet pushed to its upstream
- **THEN** the repo stays in the review list and a warning states that those commits will not be in the PR

### Requirement: Base branch

The PR base SHALL be the value of `--base <branch>` when given, otherwise the remote's default branch as recorded locally (`origin/HEAD`, falling back to `main` then `master`).

#### Scenario: Default base
- **WHEN** `--base` is not given
- **THEN** each repo's PR targets that repo's default branch

#### Scenario: Explicit base
- **WHEN** `--base release` is given
- **THEN** every PR targets `release`, and eligibility is measured against it

#### Scenario: Base unresolved
- **WHEN** no default branch can be determined for a repo and `--base` is not given
- **THEN** that repo is reported as `failed` with an error suggesting `--base`, and other repos continue

### Requirement: Review modes

The command SHALL support three mutually exclusive modes: interactive (default), `--all`, and `--auto`.

#### Scenario: Interactive
- **WHEN** no mode is given
- **THEN** each eligible repo is presented in turn with its diff summary, and the user is prompted for a PR title and body; a blank title skips the repo; repos are handled sequentially

#### Scenario: All
- **WHEN** `--all` is given
- **THEN** one PR title and body are prompted for, a blank title aborts, and every eligible repo gets a PR created with the same title/body

#### Scenario: Auto
- **WHEN** `--auto` is given
- **THEN** PR titles are auto-generated from the branch name (e.g., `feat/auth` → `feat: auth`), bodies are minimal (branch name + commit count), and PRs are created without prompts

#### Scenario: Conflicting modes
- **WHEN** both `--all` and `--auto` are given
- **THEN** the CLI prints a usage error to stderr and exits with status 2

### Requirement: Platform API integration

For each eligible repo, the command SHALL attempt to create a PR from the branch into the base via the platform's API (GitHub REST API `POST /repos/{owner}/{repo}/pulls`, GitLab API `POST /projects/:id/merge_requests` with the URL-encoded project path as the id) when credentials are available in the environment.

#### Scenario: GitHub API
- **WHEN** `GH_TOKEN` or `GITHUB_TOKEN` env var is set and the repo is on GitHub
- **THEN** a PR is created via the GitHub API and the PR URL is printed

#### Scenario: GitLab API
- **WHEN** `GITLAB_TOKEN` or `GL_TOKEN` env var is set and the repo is on GitLab
- **THEN** a merge request is created via the GitLab API, including for projects in subgroups, and the MR URL is printed

#### Scenario: Fallback to URL
- **WHEN** no valid token is available for the repo's platform
- **THEN** a PR URL pre-filled with the branch and base is constructed from the remote and printed for manual creation

#### Scenario: API failure
- **WHEN** the platform API returns an error (e.g., PR already exists, permission denied)
- **THEN** the error is reported on that repo's line and the fallback URL is printed

### Requirement: Dry run

With `--dry-run`, the command SHALL list the eligible repos, their branches, the PR titles that would be used, and the target URLs, without creating any PRs.

#### Scenario: Dry run
- **WHEN** `--auto --dry-run` or `--all --dry-run` is given
- **THEN** eligible repos are listed with planned titles and no PRs are created

#### Scenario: Dry run in interactive mode
- **WHEN** `--dry-run` is given without `--all` or `--auto`
- **THEN** eligible repos are listed with a `<prompted>` placeholder in place of the title, no prompts are shown, and no PRs are created

### Requirement: Continue on failure per repo

For a repo, the command SHALL attempt PR creation and SHALL report failure on that repo's line without stopping other repos.

#### Scenario: Single repo API failure
- **WHEN** one repo's API call fails
- **THEN** that repo is reported as `failed` with the error, and other repos continue

### Requirement: Common options

The command SHALL accept `--only` and `--jobs` as defined in the cli specification, where `--jobs` applies only to the non-interactive modes (`--all`, `--auto`).

#### Scenario: Platform filter
- **WHEN** `--only github` is given
- **THEN** only GitHub repos are considered for review

#### Scenario: Parallel auto
- **WHEN** `--auto --jobs 4` is given
- **THEN** at most 4 repos are processed concurrently

### Requirement: JSON output

With `--json`, the command SHALL print one array entry per eligible repo with `platform`, `path`, `branch`, `status` (`created` when a PR was created via the API, `manual` when no token was available and only a URL was provided, `planned` under `--dry-run`, or `failed`), `url` when a URL is available, and `error` when failed. `--json` SHALL require `--all` or `--auto`.

#### Scenario: JSON output
- **WHEN** `--auto --json` or `--all --json` is given
- **THEN** stdout is a single JSON array, one entry per eligible repo, and nothing else is printed to stdout

#### Scenario: Nothing to review
- **WHEN** `--json` is given and no repo qualifies
- **THEN** stdout is an empty JSON array

#### Scenario: Abort with JSON
- **WHEN** `--all --json` is given and the title is blank
- **THEN** stdout is an empty JSON array, and the prompt is written to stderr

#### Scenario: JSON with interactive mode
- **WHEN** `--json` is given without `--all` or `--auto`
- **THEN** the CLI prints a usage error to stderr and exits with status 2

# Proposal

## Why

After `pgit commit` and `pgit push` ship the local work, there's no built-in way to open pull/merge requests across multiple repos. Users who push feature branches to many repos must manually open PRs on GitHub/GitLab — a tedious, error-prone step that breaks the bulk workflow. `pgit review` closes this loop: detect repos whose current branch is already pushed and has commits ahead of the default branch, and open PRs via platform APIs or print ready-to-click URLs.

## What Changes

- New command `pgit review` — open PRs for repos whose current branch is not the default branch, tracks a same-named upstream branch, and has pushed commits ahead of the default branch. A PR only contains pushed commits, so if the branch is also ahead of its own upstream the repo is still included but flagged with a warning that those commits will not be in the PR.
- The PR base is the remote's default branch (`origin/HEAD`, falling back to `main` then `master`); `--base <branch>` overrides it.
- Supports three modes: interactive (default, prompts for PR title/body per repo), `--all` (one title/body for all), `--auto` (auto-generate title from branch name, minimal body).
- `--dry-run` shows which repos would get PRs and what the titles would be without creating anything (interactive mode shows a `<prompted>` placeholder, since titles are not yet known).
- `--json` outputs a machine-readable array of results (requires `--all` or `--auto`).
- Follows existing conventions: `--only <platform>`, `--jobs N` (parallelism for non-interactive modes), standard exit codes.
- Uses platform APIs (GitHub/GitLab) when credentials are available; falls back to printing PR URLs for manual creation when not.
- Does not fetch — works from local branch state like `pgit branches`. Whether a PR already exists is only known from the API, so that case is reported as a failure with the fallback URL.

## Capabilities

### New Capabilities

- `review`: Bulk PR creation for pushed branches that are ahead of the default branch. Covers candidate detection, base-branch resolution, platform API integration, interactive/auto modes, dry-run, parallel execution, and JSON output.

### Modified Capabilities

- `cli`: The `review` subcommand must be registered with its options (`--all`, `--auto`, `--base`, `--dry-run`, `--only`, `--jobs`, `--json`), mirroring `push`/`commit` conventions. The shared `--only`, `--jobs`, `--dry-run`, `--json` requirements already apply generically.

## Impact

- `src/polygit/cli.py`: register the `review` subcommand with its options.
- `src/polygit/repo.py`: new `cmd_review` and supporting functions (detect pushed branches ahead of the default branch, resolve the base branch, call platform APIs, handle auth fallback).
- `src/polygit/config.py`: potentially add platform API endpoint/token config helpers (or use existing env vars like `GH_TOKEN`, `GITLAB_TOKEN`).
- Tests in `tests/test_polygit.py` using real temporary git repos and mocked API calls.
- Documentation updates in `README.md`.
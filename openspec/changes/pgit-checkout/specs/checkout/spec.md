# Spec Delta

## Purpose

Switch every cloned repo to a local branch, or create that branch in every cloned repo, without overwriting local work and without contacting any remote.

## ADDED Requirements

### Requirement: Branch argument

`pgit checkout` SHALL require a single positional argument naming a branch. Without `-b` the branch SHALL be an existing local branch to switch to; with `-b` it SHALL be a new branch to create. Only local refs are read and nothing is fetched.

#### Scenario: Missing argument
- **WHEN** no branch argument is given
- **THEN** the CLI prints a usage error to stderr and exits with status 2

#### Scenario: Invalid branch name
- **WHEN** the argument is not a valid git branch name (e.g. `bad..name`)
- **THEN** the CLI prints an error to stderr and exits with status 2, before looking up the config

#### Scenario: Remote-only branch
- **WHEN** a branch exists as `origin/feat` in a repo but not as a local branch, and `pgit checkout feat` is run
- **THEN** that repo is reported as `skipped: branch 'feat' not found` and no local branch is created

### Requirement: Switch to an existing branch

Without `-b`, the command SHALL switch each eligible repo to the named local branch.

#### Scenario: Switch
- **WHEN** `pgit checkout main` is run and a clean repo is on another branch
- **THEN** the repo is switched to `main` and reported as `switched` with the previous branch

#### Scenario: Already on the branch
- **WHEN** a repo's current branch is already the named branch
- **THEN** the repo is reported as `up to date` and nothing changes, even if the working tree is dirty

#### Scenario: Branch missing
- **WHEN** the named branch does not exist as a local branch in a repo
- **THEN** that repo is reported as `skipped: branch 'main' not found`

### Requirement: Create a branch

With `-b`, the command SHALL create the named branch in each eligible repo and switch to it. The start point SHALL be the repo's current HEAD, or `--from <ref>` when given. `--from` SHALL accept any local ref or commit, including remote-tracking refs and tags, and SHALL be valid only with `-b`.

#### Scenario: Create from current HEAD
- **WHEN** `pgit checkout -b feat` is run in a clean repo on `main`
- **THEN** `feat` is created at the same commit as `main`, the repo is switched to it, and it is reported as `created`

#### Scenario: Create from a ref
- **WHEN** `pgit checkout -b feat --from origin/main` is run
- **THEN** `feat` is created at `origin/main` in each eligible repo

#### Scenario: Branch already exists
- **WHEN** `-b feat` is given and a repo already has a local `feat` that is not its current branch
- **THEN** that repo is reported as `skipped: branch 'feat' already exists` and is not changed

#### Scenario: Already on the new branch
- **WHEN** `-b feat` is given and a repo's current branch is already `feat`
- **THEN** that repo is reported as `up to date`

#### Scenario: Start point missing
- **WHEN** `--from release` is given and a repo has no such ref
- **THEN** that repo is reported as `skipped: start point 'release' not found`

#### Scenario: From without create
- **WHEN** `--from` is given without `-b`
- **THEN** the CLI prints a usage error to stderr and exits with status 2

### Requirement: Never overwrite local changes

The command SHALL skip, rather than force, any repo whose working tree could be changed by the operation while it has uncommitted changes. Uncommitted changes include untracked files. Creating a branch from the current HEAD does not change the working tree and SHALL be allowed on a dirty repo.

#### Scenario: Dirty repo on switch
- **WHEN** a repo has uncommitted changes and an existing branch is being switched to
- **THEN** the repo is reported as `skipped: dirty working tree` and is not changed

#### Scenario: Dirty repo on create from a ref
- **WHEN** a repo has uncommitted changes and `-b feat --from <ref>` is given
- **THEN** the repo is reported as `skipped: dirty working tree` and is not changed

#### Scenario: Dirty repo on create from HEAD
- **WHEN** a repo has uncommitted changes and `-b feat` is given without `--from`
- **THEN** `feat` is created and checked out, the uncommitted changes remain in the working tree, and the repo is reported as `created`

### Requirement: Skip ineligible repos

The command SHALL skip, with a reason, repos where switching would be unsafe or meaningless, and SHALL report them without stopping other repos.

#### Scenario: Detached HEAD
- **WHEN** a repo is in detached HEAD state
- **THEN** the repo is reported as `skipped: detached HEAD` and is not changed

#### Scenario: Unborn repo
- **WHEN** a repo has no commits yet
- **THEN** the repo is reported as `skipped: no commits yet` and is not changed

#### Scenario: Operation in progress
- **WHEN** a repo has a merge, rebase or cherry-pick in progress
- **THEN** the repo is reported as `skipped: operation in progress` and is not changed

### Requirement: Continue on failure per repo

If git fails for a repo after the checks pass, the command SHALL report that repo as `failed` with git's last error line and SHALL continue with the other repos.

#### Scenario: Git error
- **WHEN** git exits with an error for one repo
- **THEN** that repo is reported as `failed` with the error line, and the other repos are still processed

### Requirement: Dry run

With `--dry-run`, the command SHALL list the repos it would switch or create the branch in, and the repos it would skip with reasons, without changing any branch, ref or working tree.

#### Scenario: Dry run
- **WHEN** `--dry-run` is given
- **THEN** eligible repos are reported as `planned`, skipped repos show their reasons, and no repo is modified

### Requirement: Common options

The command SHALL accept `--only` and `--jobs` as defined in the cli specification.

#### Scenario: Platform filter
- **WHEN** `--only github` is given
- **THEN** only GitHub repos are processed or printed

#### Scenario: Parallel checkout
- **WHEN** `--jobs 4` is given
- **THEN** at most 4 repos are processed at once

#### Scenario: No cloned repos
- **WHEN** no repo in the config is cloned
- **THEN** the command prints `No cloned repos found.`

### Requirement: JSON output

With `--json`, the command SHALL print one array entry per cloned repo with `platform`, `path`, `status` (`switched`, `created`, `up-to-date`, `skipped`, `failed`, or `planned` under `--dry-run`), `action` (`switch` or `create`), `branch` (the requested branch), `previous` (the branch the repo was on, or `null` when detached or unborn) and `detail` (a skip reason or error line when applicable, otherwise `null`).

#### Scenario: JSON output
- **WHEN** `--json` is given
- **THEN** stdout is a single JSON array sorted by platform and path, and nothing else is printed to stdout

#### Scenario: Nothing to report
- **WHEN** `--json` is given and no repo is cloned
- **THEN** stdout is an empty JSON array

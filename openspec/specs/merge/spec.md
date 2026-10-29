# merge Specification

## Purpose
Merge a local target branch into the current branch of each cloned repo, reporting conflicts and supporting common merge strategies.

## Requirements

### Requirement: Target branch argument
`pgit merge` SHALL require a single positional argument naming the local branch to merge in (e.g., `main`). It SHALL NOT fetch from any remote.

#### Scenario: Missing argument
- **WHEN** no branch argument is given
- **THEN** the CLI prints a usage error to stderr and exits with status 2

#### Scenario: Valid branch argument
- **WHEN** `pgit merge main` is given
- **THEN** the local `main` is the branch merged into each repo's current branch

### Requirement: Skip ineligible repos
`pgit merge` SHALL act only on cloned repos that can be merged safely, and SHALL report every other repo as skipped with a reason.

#### Scenario: Detached HEAD
- **WHEN** a repo is in detached HEAD state
- **THEN** the repo is reported as `skipped: detached HEAD` and not merged

#### Scenario: Target branch missing
- **WHEN** the target branch does not exist as a local branch in a repo
- **THEN** the repo is reported as `skipped: target branch 'main' not found`

#### Scenario: Dirty working tree
- **WHEN** a repo has uncommitted changes
- **THEN** the repo is reported as `skipped: dirty working tree` and not merged

#### Scenario: Merge in progress
- **WHEN** a repo already has a merge in progress
- **THEN** the repo is reported as `skipped: merge in progress` and not merged

#### Scenario: Target is current branch
- **WHEN** the target branch is the repo's current branch
- **THEN** the repo is reported as `up to date`

### Requirement: Merge with conflict reporting
The command SHALL run `git merge <target>` in each eligible repo and report the outcome. Conflicts SHALL be detected from the git exit status and the list of unmerged files, not from git's output text.

#### Scenario: Fast-forward
- **WHEN** the merge is a fast-forward
- **THEN** the repo is reported as `merged (fast-forward)`

#### Scenario: Merge commit created
- **WHEN** a merge commit is created
- **THEN** the repo is reported as `merged (commit <short-sha>)`

#### Scenario: Conflicts
- **WHEN** the merge has conflicts
- **THEN** the repo is reported as `conflict: <N> file(s)` and the working tree is left in conflict state

#### Scenario: Already up to date
- **WHEN** the current branch already contains the target
- **THEN** the repo is reported as `up to date`

#### Scenario: Other git error
- **WHEN** git fails without leaving unmerged files, for example because of unrelated histories
- **THEN** the repo is reported as `failed` with git's last error line

### Requirement: Merge strategy flags
The command SHALL support `--no-ff` to force a merge commit and `--squash` to stage the merged changes without committing and without recording the merge. The two flags SHALL be mutually exclusive.

#### Scenario: No-ff flag
- **WHEN** `--no-ff` is given and the merge could fast-forward
- **THEN** a merge commit is created and the repo is reported as `merged (commit <short-sha>)`

#### Scenario: Squash flag
- **WHEN** `--squash` is given and the target has changes to bring in
- **THEN** the changes are staged, no commit is created, no merge relationship is recorded, and the repo is reported as `squashed (staged)`

#### Scenario: Both flags
- **WHEN** both `--no-ff` and `--squash` are given
- **THEN** the CLI prints a usage error to stderr and exits with status 2

### Requirement: Dry run
With `--dry-run`, the command SHALL list the repos it would merge and the repos it would skip with reasons, and SHALL NOT change any repo. It SHALL NOT predict the merge outcome.

#### Scenario: Dry run
- **WHEN** `--dry-run` is given
- **THEN** eligible and skipped repos are listed and no working tree or ref is modified

### Requirement: Common options
The command SHALL accept `--only` and `--jobs` as defined in the cli specification.

#### Scenario: Parallel merge
- **WHEN** `--jobs 4` is given
- **THEN** at most 4 repos are merged at once

### Requirement: JSON output
With `--json`, the command SHALL print one array entry per repo with `platform`, `path`, `status` (merged/up-to-date/conflict/skipped/failed), `strategy` (default/no-ff/squash), `detail` (a skip reason or error line when applicable) and `conflict_files` (a list) when status is conflict. A squash that stages changes SHALL have status `merged` and strategy `squash`. With `--dry-run`, `status` SHALL be `skipped` for repos that would be skipped and `planned` for repos that would be merged.

#### Scenario: JSON output
- **WHEN** `--json` is given
- **THEN** stdout is a single JSON array, one entry per repo, and nothing else is printed to stdout

#### Scenario: Nothing to report
- **WHEN** `--json` is given and there are no cloned repos
- **THEN** stdout is an empty JSON array

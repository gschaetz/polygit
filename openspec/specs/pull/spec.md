# pull Specification

## Purpose
Update every cloned repo from its upstream without losing local changes.

## Requirements

### Requirement: Rebase pull with auto-stash
`pgit pull` SHALL run `git pull --rebase` in each cloned repo, stashing uncommitted changes first and restoring them afterwards.

#### Scenario: Dirty repo
- **WHEN** a repo has uncommitted changes
- **THEN** they are stashed before the pull and popped after it

#### Scenario: Stash pop conflicts
- **WHEN** restoring the stash conflicts
- **THEN** a warning naming the repo is printed

#### Scenario: No upstream
- **WHEN** the branch has no upstream
- **THEN** the repo is reported with `⚠ no upstream branch set` rather than as a failure

### Requirement: Dry run
With `--dry-run`, the command SHALL report ahead and behind counts against the last-fetched upstream and SHALL NOT change any repo, including a dirty working tree.

#### Scenario: Behind upstream
- **WHEN** `--dry-run` is given and a repo is behind
- **THEN** its ahead and behind counts are printed and nothing is pulled or stashed

### Requirement: Common options
The command SHALL accept `--only` and `--jobs` as defined in the cli specification.

#### Scenario: Platform filter
- **WHEN** `--only github` is given
- **THEN** only github repos are pulled

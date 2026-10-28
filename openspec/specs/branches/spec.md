# branches Specification

## Purpose
Show the current branch and upstream tracking status of every cloned repo.

## Requirements

### Requirement: Local-only status
`pgit branches` SHALL report ahead and behind counts from local refs, as of each repo's last fetch, and SHALL NOT fetch.

#### Scenario: Stale remote
- **WHEN** the remote has new commits that were never fetched
- **THEN** the repo is reported as it was at the last fetch

### Requirement: One line per cloned repo
The command SHALL print one line per cloned repo, sorted by platform and path, naming the branch, its upstream and the state. Repos listed in `.pgit` but not cloned SHALL be skipped.

#### Scenario: Up to date
- **WHEN** the branch matches its upstream
- **THEN** the line shows `✓` and `(up to date)`

#### Scenario: Ahead only
- **WHEN** the branch has unpushed commits and none to pull
- **THEN** the line shows `↑` and `(N ahead)`

#### Scenario: Behind only
- **WHEN** the upstream has commits the branch lacks
- **THEN** the line shows `↓` and `(N behind)`

#### Scenario: Diverged
- **WHEN** the branch is both ahead and behind
- **THEN** the line shows `⚠` with both counts

#### Scenario: No upstream
- **WHEN** the branch has no upstream configured, including an empty repo with no commits
- **THEN** the line shows `~` and `(no upstream)`

#### Scenario: Upstream gone
- **WHEN** the configured upstream branch no longer exists on the remote and the deletion was fetched
- **THEN** the line shows `⚠` and `(upstream gone)`, not `(no upstream)`

#### Scenario: Detached HEAD
- **WHEN** no branch is checked out
- **THEN** the line shows `⚠` and `detached HEAD at <short sha>`

#### Scenario: No cloned repos
- **WHEN** no configured repo is cloned
- **THEN** the command prints `No cloned repos found.`

### Requirement: JSON output
With `--json`, the command SHALL print one array entry per cloned repo, including clean ones, with `platform`, `path`, `branch`, `sha`, `upstream`, `ahead`, `behind` and `state`.

#### Scenario: Detached HEAD in JSON
- **WHEN** HEAD is detached
- **THEN** `state` is `detached`, `branch` is null and `sha` holds the short hash

#### Scenario: State values
- **WHEN** an entry is emitted
- **THEN** `state` is one of `tracking`, `none`, `gone` or `detached`

### Requirement: Common options
The command SHALL accept `--only` and `--jobs` as defined in the cli specification.

#### Scenario: Platform filter
- **WHEN** `--only github` is given
- **THEN** only github repos are listed

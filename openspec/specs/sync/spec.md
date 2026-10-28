# sync Specification

## Purpose
Clone repos that are configured but missing, and fetch the rest.

## Requirements

### Requirement: Clone or fetch every configured repo
`pgit sync` SHALL clone each configured repo that is not yet on disk and run a fetch of all remotes on each repo that is.

#### Scenario: Missing repo
- **WHEN** a configured repo has no `.git` directory
- **THEN** it is cloned to `<root>/<platform>/<path>` and reported as cloned

#### Scenario: Existing repo
- **WHEN** a configured repo is already cloned
- **THEN** all remotes are fetched and the working tree is not changed

### Requirement: Retry transient network errors
Git operations SHALL be retried when they fail with a known transient SSH or network error, and a partial clone SHALL be removed before each retry.

#### Scenario: Connection reset
- **WHEN** a clone fails with a connection reset
- **THEN** it is retried with a growing delay before being reported as failed

### Requirement: Failures do not stop the run
A failure in one repo SHALL be reported on that repo's line and SHALL NOT prevent the others from being processed.

#### Scenario: One remote unreachable
- **WHEN** one repo fails to fetch
- **THEN** it is reported with `✗` and the other repos still sync

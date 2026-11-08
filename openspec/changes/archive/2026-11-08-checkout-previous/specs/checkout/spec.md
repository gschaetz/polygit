# Spec Delta

## ADDED Requirements

### Requirement: Switch to the previous branch

`pgit checkout -` SHALL switch each eligible repo to the branch that repo was on before its most recent switch, resolved separately per repo from its local reflog. Nothing is fetched. The resolved branch is then handled exactly as a branch named explicitly, including every skip rule for switching.

#### Scenario: Restore a mixed tree
- **WHEN** `pgit checkout -b feat` was run in repos on `main` and on `master`, then `pgit checkout -` is run
- **THEN** the `main` repos are switched back to `main` and the `master` repos to `master`, each reported as `switched`

#### Scenario: Toggle
- **WHEN** `pgit checkout -` is run twice in a row
- **THEN** each repo ends on the branch it started on, as with `git checkout -`

#### Scenario: No previous branch
- **WHEN** a repo has no recorded previous branch, the previous state was a detached HEAD, or the previous branch no longer exists
- **THEN** that repo is reported as `skipped: no previous branch` and is not changed

#### Scenario: Dirty repo
- **WHEN** a repo has uncommitted changes and `pgit checkout -` is run
- **THEN** that repo is reported as `skipped: dirty working tree` and is not changed

#### Scenario: Dry run
- **WHEN** `pgit checkout - --dry-run` is run
- **THEN** each eligible repo is reported as `planned` with its resolved branch, and no repo is modified

#### Scenario: JSON output
- **WHEN** `pgit checkout - --json` is run
- **THEN** each entry has `action` `switch` and `branch` set to the repo's resolved branch, or `null` when the repo was skipped for having no previous branch

### Requirement: Previous branch needs no create

The `-` argument SHALL be valid only for switching. Combining it with `-b` SHALL be rejected.

#### Scenario: Create with dash
- **WHEN** `pgit checkout -b -` is run
- **THEN** the CLI prints an error to stderr and exits with status 2, before looking up the config

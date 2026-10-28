# push Specification

## Purpose
Commit and push every dirty repo, interactively, with one shared message, or with an automatic WIP message.

## Requirements

### Requirement: Only dirty repos
`pgit push` SHALL act only on cloned repos with uncommitted changes.

#### Scenario: Nothing dirty
- **WHEN** no repo is dirty
- **THEN** the command prints `No dirty repos to commit.`

### Requirement: Commit modes
The command SHALL support three mutually exclusive modes: interactive (default), `--all` and `--wip`.

#### Scenario: Interactive
- **WHEN** no mode is given
- **THEN** each dirty repo's changes are shown in turn and a message is prompted, a blank message skips the repo, and repos are handled sequentially

#### Scenario: All
- **WHEN** `--all` is given
- **THEN** one commit message is prompted for, a blank message aborts, and every dirty repo is committed with it

#### Scenario: WIP
- **WHEN** `--wip` is given
- **THEN** every dirty repo is committed with the message `WIP <YYYY-MM-DD HH:MM>`, with no prompt

### Requirement: Stop on failure
For a repo, the command SHALL run add, then commit, then push, and SHALL stop at the first step that fails and report it on that repo's line without pushing.

#### Scenario: Commit fails
- **WHEN** the commit step fails, for example a pre-commit hook
- **THEN** the repo is reported as `commit failed` and no push is attempted

### Requirement: Dry run
With `--dry-run`, the command SHALL list the dirty repos it would commit and SHALL NOT commit or push.

#### Scenario: Dry run
- **WHEN** `--dry-run` is given
- **THEN** dirty repos are listed and their working trees are unchanged

### Requirement: Common options
The command SHALL accept `--only` and `--jobs`, where `--jobs` applies only to the non-interactive modes.

#### Scenario: Parallel WIP
- **WHEN** `--wip --jobs 3` is given
- **THEN** at most 3 repos are pushed at once

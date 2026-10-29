# Spec Delta

## Purpose

Commit uncommitted changes in every dirty repo with a shared or automatic message, without pushing.

## ADDED Requirements

### Requirement: Only dirty repos
`pgit commit` SHALL act only on cloned repos with uncommitted changes.

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

### Requirement: Stage everything
For each repo the command SHALL stage all changes with `git add -A` before committing, as `pgit push` does. Selective staging is not supported.

#### Scenario: Untracked files
- **WHEN** a dirty repo has untracked files
- **THEN** they are included in the commit

### Requirement: Stop on failure
For a repo, the command SHALL run add then commit, and SHALL stop at the first step that fails and report it on that repo's line.

#### Scenario: Commit fails
- **WHEN** the commit step fails, for example a pre-commit hook
- **THEN** the repo is reported as `commit failed`

#### Scenario: Add fails
- **WHEN** the add step fails
- **THEN** the repo is reported as `add failed` and no commit is attempted

### Requirement: No push
The command SHALL NOT push.

#### Scenario: Remote unchanged
- **WHEN** a repo is committed
- **THEN** no push is attempted and the remote is unchanged

### Requirement: Dry run
With `--dry-run`, the command SHALL list the dirty repos it would commit and SHALL NOT commit.

#### Scenario: Dry run
- **WHEN** `--dry-run` is given
- **THEN** dirty repos are listed and their working trees are unchanged

### Requirement: Common options
The command SHALL accept `--only` and `--jobs` as defined in the cli specification, where `--jobs` applies only to the non-interactive modes.

#### Scenario: Parallel WIP
- **WHEN** `--wip --jobs 3` is given
- **THEN** at most 3 repos are committed at once

### Requirement: JSON output
With `--json`, the command SHALL print one array entry per dirty repo with `platform`, `path`, `status` (committed/failed, or `planned` under `--dry-run`), `message`, `sha` when committed, and `error` when failed. `--json` SHALL require `--all` or `--wip`.

#### Scenario: JSON output
- **WHEN** `--wip --json` or `--all --json` is given
- **THEN** stdout is a single JSON array, one entry per dirty repo, and nothing else is printed to stdout

#### Scenario: Nothing dirty
- **WHEN** `--json` is given and no repo is dirty
- **THEN** stdout is an empty JSON array

#### Scenario: Abort with JSON
- **WHEN** `--all --json` is given and the message is blank
- **THEN** stdout is an empty JSON array, and the prompt is written to stderr

#### Scenario: JSON with interactive mode
- **WHEN** `--json` is given without `--all` or `--wip`
- **THEN** the CLI prints a usage error to stderr and exits with status 2

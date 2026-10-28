# status Specification

## Purpose
Show which cloned repos have uncommitted changes, as text or as JSON for scripts.

## Requirements

### Requirement: List dirty repos
`pgit status` SHALL list each cloned repo with uncommitted changes, with its `git status --short` lines, and omit clean repos.

#### Scenario: Some repos dirty
- **WHEN** a cloned repo has uncommitted changes
- **THEN** it is listed under its `platform/path` with its changed files

#### Scenario: All clean
- **WHEN** no cloned repo has uncommitted changes
- **THEN** the command prints `All repos are clean.`

### Requirement: JSON output
With `--json`, the command SHALL print an array with `platform`, `path` and `changed_files` for each dirty repo only.

#### Scenario: Clean repos omitted
- **WHEN** `--json` is given and no repo is dirty
- **THEN** stdout is an empty array

### Requirement: Common options
The command SHALL accept `--only` and `--jobs` as defined in the cli specification.

#### Scenario: Platform filter
- **WHEN** `--only gitlab` is given
- **THEN** only gitlab repos are checked

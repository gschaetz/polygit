# cli Specification

## Purpose
Behavior shared by every `pgit` command: config discovery and the `--only` and `--jobs` options.

## Requirements

### Requirement: Config discovery
The CLI SHALL locate the `.pgit` config by walking up from the current directory, and SHALL treat the directory containing it as the repos root.

#### Scenario: Run from a subdirectory
- **WHEN** a command runs inside a repo below the directory holding `.pgit`
- **THEN** it operates on the repos configured in that `.pgit`

#### Scenario: No config
- **WHEN** no `.pgit` exists in the current directory or any parent
- **THEN** the CLI prints an error to stderr and exits with status 1

### Requirement: Platform filter
Commands that accept `--only <platform>` SHALL limit work to repos under that platform.

#### Scenario: Known platform
- **WHEN** `--only github` is given
- **THEN** repos under other platforms are not processed or printed

#### Scenario: Unknown platform
- **WHEN** `--only` names a platform that is not a known host
- **THEN** the CLI prints an error listing the available platforms to stderr and exits with status 1

### Requirement: Parallelism
Commands that accept `--jobs N` SHALL process up to N repos in parallel, defaulting to 8 when omitted.

#### Scenario: Invalid value
- **WHEN** `--jobs` is not a positive integer
- **THEN** the CLI prints an error and exits with status 2 before looking up the config

### Requirement: Machine-readable output
When `--json` is given, a command SHALL print a single JSON value on stdout and nothing else.

#### Scenario: Nothing to report
- **WHEN** `--json` is given and there are no entries
- **THEN** stdout is an empty JSON array

### Requirement: Review subcommand

The CLI SHALL provide a `review` subcommand accepting `--all`, `--auto`, `--base <branch>`, `--dry-run`, `--only <platform>`, `--jobs N` and `--json`, with `--only`, `--jobs` and `--json` behaving as defined by the shared requirements above.

#### Scenario: Listed in help
- **WHEN** `pgit --help` is run
- **THEN** `review` appears among the subcommands

#### Scenario: Mutually exclusive modes
- **WHEN** both `--all` and `--auto` are given
- **THEN** the CLI prints a usage error to stderr and exits with status 2

#### Scenario: JSON needs a non-interactive mode
- **WHEN** `--json` is given without `--all` or `--auto`
- **THEN** the CLI prints a usage error to stderr and exits with status 2

### Requirement: Checkout subcommand

The CLI SHALL provide a `checkout` subcommand taking one branch argument and accepting `-b`, `--from <ref>`, `--dry-run`, `--only <platform>`, `--jobs N` and `--json`, with `--only`, `--jobs` and `--json` behaving as defined by the shared requirements above. Argument errors SHALL be reported before the config is looked up.

#### Scenario: Listed in help
- **WHEN** `pgit --help` is run
- **THEN** `checkout` appears among the subcommands

#### Scenario: From requires create
- **WHEN** `--from` is given without `-b`
- **THEN** the CLI prints a usage error to stderr and exits with status 2

#### Scenario: Invalid branch name
- **WHEN** the branch argument is not a valid git branch name
- **THEN** the CLI prints an error to stderr and exits with status 2 without looking up the config

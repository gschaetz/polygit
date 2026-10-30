# Spec Delta

## ADDED Requirements

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

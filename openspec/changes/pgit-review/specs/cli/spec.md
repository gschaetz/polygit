# Spec Delta

## ADDED Requirements

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

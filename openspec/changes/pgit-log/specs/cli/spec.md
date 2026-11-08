# Spec Delta

## ADDED Requirements

### Requirement: Log subcommand

The CLI SHALL provide a `log` subcommand accepting `--limit N`, `--since <value>`, `--author <text>`, `--only <platform>`, `--jobs N` and `--json`, with `--only`, `--jobs` and `--json` behaving as defined by the shared requirements above. Argument errors SHALL be reported before the config is looked up.

#### Scenario: Listed in help
- **WHEN** `pgit --help` is run
- **THEN** `log` appears among the subcommands

#### Scenario: Invalid limit
- **WHEN** `--limit` is not an integer greater than or equal to 0
- **THEN** the CLI prints a usage error to stderr and exits with status 2 without looking up the config

#### Scenario: Invalid since
- **WHEN** `--since` is not a `YYYY-MM-DD` date or an `N.unit` / `N unit` span
- **THEN** the CLI prints a usage error to stderr and exits with status 2 without looking up the config

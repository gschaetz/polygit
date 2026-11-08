# Spec Delta

## ADDED Requirements

### Requirement: Search subcommand

The CLI SHALL provide a `search` subcommand taking one search term argument and accepting `--limit N`, `--only <platform>`, `--jobs N` and `--json`, with `--only`, `--jobs` and `--json` behaving as defined by the shared requirements above. Argument errors SHALL be reported before the config is looked up.

#### Scenario: Listed in help
- **WHEN** `pgit --help` is run
- **THEN** `search` appears among the subcommands

#### Scenario: Missing or empty term
- **WHEN** the search term is omitted, empty, or whitespace-only
- **THEN** the CLI prints a usage error to stderr and exits with status 2 without looking up the config

#### Scenario: Invalid limit
- **WHEN** `--limit` is not an integer greater than or equal to 0
- **THEN** the CLI prints a usage error to stderr and exits with status 2 without looking up the config

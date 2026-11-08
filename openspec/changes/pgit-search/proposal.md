# Proposal

## Why

The `pgit` CLI currently lacks a way to quickly discover and filter repos by name, path, or remote URL. Users managing many repositories have no convenient way to find specific repos without manually scanning status output or using shell tools outside of `pgit`.

## What Changes

- New `pgit search <term>` command that searches repos by name/path/remote
- `--json` flag for machine-readable output suitable for scripting
- `--limit N` option to restrict results (default: show all; `0` yields an empty result)
- Case-insensitive matching with ranking by relevance score
- Support for prefix, substring, and word-boundary matches (no typo tolerance in v1)

## Capabilities

### New Capabilities
- `search`: Search functionality for discovering repos across name, path, and remote attributes, including matching, ranking, `--limit`, and JSON output.

### Modified Capabilities
- `cli`: Add the `search` subcommand (arguments, `--limit`, and argument-error handling) alongside `review` and `checkout`. The shared `--only`/`--jobs`/`--json` requirements are unchanged.

## Impact

- New module for search logic and ranking
- User-facing command documentation updates in README.md
- No breaking changes to existing commands or output formats

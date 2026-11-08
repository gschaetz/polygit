# Proposal

## Why

`pgit` shows where repos stand (`status`, `branches`) but not what happened in them. To answer "what did I change this week?" across many repos, users have to `cd` into each one and run `git log`. `pgit log` fills that gap from the same `.pgit` config.

## What Changes

- New `pgit log` command listing recent commits across all cloned repos, newest first
- `--limit N` caps the total number of commits (default 20; `0` returns nothing)
- `--since <date|relative>` and `--author <text>` filters
- `--only`, `--jobs` and `--json`, as on other commands
- Reads local refs only (the current `HEAD` of each repo); never fetches
- Moves `pgit search` to "Shipped" in `docs/roadmap.md` and `pgit log` after this ships

## Capabilities

### New Capabilities
- `log`: Listing recent commits across cloned repos, with ordering, filtering and output formats

### Modified Capabilities
- `cli`: Add the `log` subcommand (arguments, `--limit`, `--since` validation, and argument-error handling) alongside `search`, `review` and `checkout`

## Impact

- New `src/polygit/log.py` module and `cmd_log` in `src/polygit/repo.py`
- `src/polygit/cli.py`: new subparser and two argument validators
- Tests in `tests/test_polygit.py`; README and roadmap updates
- No changes to existing commands or output formats

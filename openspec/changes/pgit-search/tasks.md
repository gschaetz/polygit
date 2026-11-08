# Tasks

## 1. CLI Argument Parser Setup

- [ ] 1.1 Add search subparser with positional term argument in `src/polygit/cli.py` (after branches parser)
   Verify: `pgit search --help` displays the new command with correct arguments

- [ ] 1.2 Reject a missing, empty, or whitespace-only term before config lookup in `cli.py` main()
   Verify: Running `pgit search` or `pgit search ""` exits with status 2 and prints usage error

- [ ] 1.3 Add --limit N argument validation (integer >= 0) using a new `_non_negative_int` helper alongside `_positive_int`
   Verify: `--limit -1` and `--limit abc` print error and exit status 2 before config lookup; `--limit 0` is accepted

- [ ] 1.4 Wire up search command in commands dict: `"search": lambda: cmd_search(...)`
   Verify: Command is dispatched correctly without import errors

## 2. Search Module Implementation

- [ ] 2.1 Create `src/polygit/search.py` with empty module structure
   Verify: Module can be imported without errors

- [ ] 2.2 Implement `build_search_index(config, base, jobs)` that returns list of repo dicts (name, path, platform, remote) for repos cloned on disk, reading `git remote get-url origin` in parallel under `jobs` (empty string if no origin)
   Verify: Called once at command start; returns correct metadata for sample config; a repo without origin has `remote == ""`

- [ ] 2.3 Implement `_compute_relevance_term(term, name)` helper with case-insensitive prefix / word-boundary / substring scoring and position bonus
   Verify: Running `pgit search poly` ranks `polygit` (prefix) above `my-poly` (word boundary)

- [ ] 2.4 Implement `_compute_relevance_path(term, path)` with similar scoring for filesystem paths
   Verify: Searching `dev` matches `/home/user/development/*` repos and not `/home/user/docs/*`

- [ ] 2.5 Implement `_compute_relevance_remote(term, remote_url)` helper matching against the URL as-is
   Verify: Searching an owner name finds repos with that owner in their remote URLs

- [ ] 2.6 Implement `rank_search_results(results)` that takes each repo's score as the max of its name, path, and remote scores, drops zero-score repos, and sorts by descending score then alphabetically by path
   Verify: Results ordered correctly when multiple repos match the same term at different priorities; a name match outranks a path-only match

- [ ] 2.7 Implement `cmd_search(config, base, term, limit, only_platform, jobs, json_output)` in `src/polygit/repo.py` that orchestrates `search.py` and prints the results
   Verify: Returns/prints repos matching the term with optional platform filtering

## 3. Integration & Filtering

- [ ] 3.1 Apply --only <platform> filtering to the index before ranking
   Verify: `pgit search polygit --only github` excludes GitLab repos even if they match

- [ ] 3.2 Apply --limit N truncation to ranked results list (`0` yields no results)
   Verify: `pgit search term --limit 5` returns at most 5 entries; `--limit 0` returns none

- [ ] 3.3 Handle edge case where no repos are cloned/configured (return empty list/array)
   Verify: Searching with no configured repos outputs `[]` in JSON mode and nothing in text mode

## 4. Output Formatting

- [ ] 4.1 Implement text output format: one line per result showing name, path, platform (similar to branches output style)
   Verify: Running `pgit search test` shows formatted lines like `test-repo (/path/to/repo) [github]`

- [ ] 4.2 Implement JSON output format with fields: name, path, platform, remote, score
   Verify: `pgit search term --json` produces valid JSON array `[{"name":"...", "score":...}]` that parses correctly

- [ ] 4.3 Ensure stdout is clean when --json used (no extra print statements or debug output)
   Verify: Pipe JSON through jq and confirm no parsing errors occur

## 5. Tests

- [ ] 5.1 Add test for search command in `tests/test_polygit.py` covering basic name matching (prefix before word-boundary)
   Verify: Test runs successfully and asserts correct ranking behavior for named repos

- [ ] 5.2 Add test for path-based matching using sample path entries
   Verify: Test verifies repo detection based on filesystem path substrings

- [ ] 5.3 Add test for remote URL matching, including a repo with no origin
   Verify: Test confirms owner matching on remote URLs and that a repo without origin has `remote == ""` and is not an error

- [ ] 5.4 Add tests for --limit flag limiting result count, including `--limit 0`
   Verify: Tests confirm truncated output respects the limit and `0` returns no results

- [ ] 5.5 Add tests for --only platform filtering in search context
   Verify: Platform filtering test validates correct repos selected per platform constraint

- [ ] 5.6 Add test for case-insensitive matching behavior
   Verify: Searching `POLYGIT` returns same results as `polygit` or `PolyGit`

- [ ] 5.7 Add test for JSON output format validation (valid JSON, expected fields present)
   Verify: JSON output parses and contains required fields: name, path, platform, remote, score

- [ ] 5.8 Add tests for argument errors: missing term, empty term, invalid `--limit`
   Verify: Each exits with status 2 and prints a usage error to stderr

## 6. Documentation

- [ ] 6.1 Update README.md with `pgit search` documentation section (usage examples, flags, and a note that typo-tolerant matching is not supported)
   Verify: README documents how to use search command with concrete examples

- [ ] 6.2 Add inline docstrings to `cmd_search()` and all helper functions for API documentation
   Verify: Docstrings follow existing module style and describe parameters/return values

## Workflow follow-up

- Archive the change after review requirements are satisfied using `/opsx:archive pgit-search --yes`
- Verify the archived result by running `openspec show search --type spec --no-scenarios` to confirm merged specs

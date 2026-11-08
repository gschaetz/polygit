# search Specification

## Purpose
Enable search across all cloned git repositories by name, path, and remote URL.

## Requirements

### Requirement: Search command invocation
The CLI SHALL provide a `search` subcommand that accepts a positional search term argument and optional flags `--limit`, `--json`, `--only`, and `--jobs`. Only repositories cloned on disk are searched.

#### Scenario: Basic search invocation
- **WHEN** user runs `pgit search <term>` with a search term
- **THEN** command executes and returns matching repos

Argument errors (missing or empty term, invalid `--limit`) are specified in the `cli` spec.

### Requirement: Name-based matching
The search SHALL match repository names (the final path component) using case-insensitive prefix, substring, or word-boundary matching. A word boundary is the start of the name or any position following a non-alphanumeric character.

#### Scenario: Prefix and word-boundary match
- **WHEN** searching for term `poly` against repos named `polygit`, `my-poly`, `other`
- **THEN** command returns `polygit` first (prefix match), then `my-poly` (word-boundary match), and not `other`

#### Scenario: Case insensitivity
- **WHEN** searching for `POLYGIT` or `polyGit`
- **THEN** command returns same results as for `polygit`

#### Scenario: No matches
- **WHEN** search term has no matches in any repo name, path, or remote
- **THEN** command outputs empty result (empty array with --json)

### Requirement: Path-based matching
The search SHALL match against the full filesystem path of each repository.

#### Scenario: Substring path match
- **WHEN** searching for `dev` against repos at `/home/user/development/myproject`, `/home/user/docs/readme`
- **THEN** command returns only `/home/user/development/myproject`

#### Scenario: Priority of name over path
- **WHEN** a search term matches the name of one repo and only the path of another
- **THEN** the name match is ranked higher than the path-only match

### Requirement: Remote-based matching
The search SHALL match against each repo's `origin` remote URL (as returned by `git remote get-url origin`). A repo with no `origin` remote has an empty remote and can still match on name and path.

#### Scenario: Owner match
- **WHEN** searching for `example` and repos have remotes `https://github.com/example/a.git` and `https://gitlab.com/example/b.git`
- **THEN** command returns both repos, from GitHub and GitLab

#### Scenario: Full URL match
- **WHEN** searching for a full remote URL
- **THEN** command returns repos with that remote URL

#### Scenario: No origin remote
- **WHEN** a repo has no `origin` remote
- **THEN** the repo is not an error; it is matched on name and path only and its `remote` is `""`

### Requirement: Relevance ranking
Each repo's score SHALL be the maximum of its name, path, and remote scores, where:
- Name matches weigh more than path matches, which weigh more than remote matches
- Within a field, prefix matches weigh more than word-boundary matches, which weigh more than substring matches
- Results are sorted descending by score

#### Scenario: Mixed match types
- **WHEN** search term `poly` appears in a repo's name, path, and remote
- **THEN** the repo's score equals its name score, because that is the highest of the three

#### Scenario: Tie-breaking
- **WHEN** two repos have identical scores
- **THEN** results are sorted alphabetically by full path

### Requirement: Limit parameter
The search SHALL accept a `--limit N` option (N is an integer >= 0; default: unlimited) that restricts output to the top N results. Invalid values are rejected as specified in the `cli` spec.

#### Scenario: Applied limit
- **WHEN** searching with `--limit 5` and 20 matches exist
- **THEN** exactly 5 results are returned in rank order

#### Scenario: Zero limit
- **WHEN** searching with `--limit 0`
- **THEN** command outputs empty result

### Requirement: JSON output format
With `--json`, the search SHALL print an array of objects, each containing:
- `name`: The repository's short name (final path component)
- `path`: Full filesystem path to the repo
- `platform`: GitHub or GitLab
- `remote`: The origin remote URL (`""` if none)
- `score`: Numeric relevance score

#### Scenario: Empty result JSON
- **WHEN** search finds no matches with --json flag
- **THEN** stdout is an empty JSON array `[]`

#### Scenario: Limited results JSON
- **WHEN** search with --limit returns results with --json
- **THEN** only the limited number of entries appear in the array

### Requirement: No typo tolerance
Matching SHALL be exact apart from case: the search does not match terms that differ from the text by misspelling.

#### Scenario: Misspelled term
- **WHEN** searching for `polgyit` and a repo is named `polygit`
- **THEN** the repo is not returned

### Requirement: Combined filtering
When using `--only <platform>` with search, results SHALL be filtered to only that platform before ranking.

#### Scenario: Platform filter with search
- **WHEN** user runs `pgit search term --only github`
- **THEN** only GitHub repos are returned, even if GitLab has matches

### Requirement: Integration with existing options
The search command SHALL honor the shared CLI options (`--jobs`, `--only`) as other commands do.

#### Scenario: Jobs limit applies
- **WHEN** search reads remotes for many repos with --jobs 4
- **THEN** at most 4 `git remote get-url` calls run at the same time

# Spec Delta

## Purpose

List recent commits across all cloned repos in one view.

## ADDED Requirements

### Requirement: Cross-repo commit listing
`pgit log` SHALL list commits reachable from the current `HEAD` of every cloned repo, newest commit date first, using local refs only and SHALL NOT fetch. Repos listed in `.pgit` but not cloned SHALL be skipped.

#### Scenario: Commits from several repos
- **WHEN** repo `a` has commits `a1` (Jan 1) and `a2` (Jan 3) and repo `b` has `b1` (Jan 2)
- **THEN** the commits are listed in the order `a2`, `b1`, `a1`

#### Scenario: Stale remote
- **WHEN** a remote has commits that were never fetched
- **THEN** those commits are not listed

#### Scenario: Repo with no commits
- **WHEN** a cloned repo has no commits
- **THEN** it is skipped without an error and the other repos are still listed

#### Scenario: Equal commit dates
- **WHEN** two commits have the same commit date
- **THEN** they are ordered by repo path and then by hash

### Requirement: Commit fields
Each listed commit SHALL carry the repo `name` (final path component), the repo `path` (full filesystem path), the `platform`, the short `hash`, the `author` name, the commit `date` in ISO 8601 with its UTC offset, and the `subject` line.

#### Scenario: Text line
- **WHEN** a commit is printed without `--json`
- **THEN** it is one line in the form `<hash> <date> <name> (<author>) <subject>`

### Requirement: Limit
`pgit log` SHALL accept `--limit N` (integer >= 0, default 20) that caps the total number of commits across all repos, taken from the newest. `--limit 0` SHALL produce no output commits.

#### Scenario: Applied limit
- **WHEN** `--limit 2` is given and three commits exist across the repos
- **THEN** only the two newest are listed

#### Scenario: Default limit
- **WHEN** `--limit` is omitted and more than 20 commits exist
- **THEN** exactly the 20 newest are listed

#### Scenario: Zero limit
- **WHEN** `--limit 0` is given
- **THEN** no commits are listed

### Requirement: Since filter
`pgit log` SHALL accept `--since <value>` and list only commits made at or after that time. The value is either a calendar date `YYYY-MM-DD` (start of that day) or a relative span written `N.unit` or `N unit` where N is an integer and unit is one of `minute`, `hour`, `day`, `week`, `month`, `year` (plural allowed).

#### Scenario: Date filter
- **WHEN** `--since 2026-01-02` is given
- **THEN** commits made before 2026-01-02 are not listed

#### Scenario: Relative filter
- **WHEN** `--since 2.weeks` is given
- **THEN** only commits from the last two weeks are listed

### Requirement: Author filter
`pgit log` SHALL accept `--author <text>` and list only commits whose author name or email contains the text, ignoring case. The text is matched literally, not as a pattern.

#### Scenario: Name match
- **WHEN** `--author ann` is given and a commit is by `Ann`
- **THEN** the commit is listed and commits by other authors are not

#### Scenario: Literal text
- **WHEN** `--author "a.n"` is given and the only author is `Ann`
- **THEN** no commits are listed

### Requirement: JSON output
With `--json`, `pgit log` SHALL print one JSON array of objects with the keys `name`, `path`, `platform`, `hash`, `author`, `date` and `subject`, and nothing else on stdout.

#### Scenario: No commits
- **WHEN** no commits match with `--json`
- **THEN** stdout is `[]`

#### Scenario: No commits as text
- **WHEN** no commits match without `--json`
- **THEN** nothing is printed

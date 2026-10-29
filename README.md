# polygit

Manage multiple git repos from a single `.pgit` config file.

```bash
uv tool install polygit
```

## Usage

```bash
pgit sync      # clone missing repos, fetch all
pgit status    # show repos with uncommitted changes
pgit pull      # pull all repos, auto-stashing local changes
pgit commit    # commit dirty repos without pushing
pgit push      # interactively commit and push dirty repos
pgit merge     # merge a target branch into each repo
pgit repos     # discover drift between .pgit and the filesystem
pgit branches  # show current branch and tracking status per repo
```

`status`, `pull`, `push` *and* `sync` accept `--jobs N` to control how many
repositories are processed in parallel. The default (when omitted) is 8.

```bash
pgit sync --jobs 4
pgit status --jobs 1
pgit pull   --only github --dry-run --jobs 4
pgit branches --only github --jobs 4
```

`N` must be a positive integer; otherwise the command prints a clear error and
exits with status 2.

`status`, `pull` and `push` accept `--only <platform>` to operate on a single platform
(e.g. `github`) instead of all of them. `branches` also accepts `--only`:

```bash
pgit status --only gitlab
pgit pull   --only github --dry-run
pgit push   --only gitlab --all
pgit branches --only github
```

Passing an unknown platform prints an error to stderr and exits 1.


## commit

`pgit commit` commits dirty repos without pushing to remotes:

```bash
pgit commit                # prompt for a message per repo (default)
pgit commit --all          # one message for all dirty repos
pgit commit --wip          # auto-commit with "WIP <timestamp>"
pgit commit --dry-run      # list dirty repos that would be committed
pgit commit --wip --json   # emit JSON array of commit results
```

Note: `--json` is available with `--all` or `--wip` modes.

## merge

`pgit merge <branch>` merges a target branch into the current branch of each cloned repo:

```bash
pgit merge main            # merge local 'main' into current branch of each repo
pgit merge main --no-ff    # force a merge commit
pgit merge main --squash   # stage the merged changes without committing
pgit merge main --dry-run  # list repos that would be merged or skipped; changes nothing
pgit merge main --json     # emit JSON array of merge results
```

`pgit merge` acts on local branches and does not fetch from remotes — run `pgit sync` first if you need updated remote branches. Repos with dirty working trees, detached HEADs, or missing target branches are skipped safely with a clear reason.

## Configuration

Create a `.pgit` file in the root directory that contains your repos:

```yaml
github:
  your-username:
    repo-one:
    repo-two:
  some-org:
    their-repo: {remote: "some-org/their-repo"}

gitlab:
  your-namespace/group:
    private-repo:
    another-repo:
```

`pgit` discovers this file by walking up from the current directory — so running `pgit status` anywhere inside your repos root just works.

### Remote overrides

If a repo is cloned to a local path that differs from its remote path, use the `remote` key:

```yaml
github:
  my-local-name:
    project: {remote: "upstream-org/project"}
```

## push modes

```bash
pgit push                # prompt for a message per repo (default)
pgit push --all          # one message for all dirty repos
pgit push --wip          # auto-commit with "WIP <timestamp>"
```

## dry run

```bash
pgit pull --dry-run      # show ahead/behind per repo; changes nothing
pgit push --dry-run      # list dirty repos that would be committed and pushed
```

`pull --dry-run` compares against the last fetched state of each upstream, so run `pgit sync` first for current numbers.

## branches

`pgit branches` shows the current branch and upstream tracking status for each cloned repository:

```bash
pgit branches
```

Output shows one line per repo:

- **✓** — up to date with upstream
- **↑** — ahead of upstream (needs a push)
- **↓** — behind upstream (needs a pull)
- **⚠** — diverged (both ahead and behind), upstream deleted on the remote, or detached HEAD
- **~** — branch has no upstream configured (also an empty repo)

```text
✓ github/gschaetz/polygit: main -> origin/main (up to date)
↑ github/gschaetz/tools: main -> origin/main (2 ahead)
↓ github/gschaetz/notes: main -> origin/main (3 behind)
⚠ github/gschaetz/dotfiles: main -> origin/main (3 ahead, 1 behind)
⚠ github/gschaetz/old: feat -> origin/feat (upstream gone)
⚠ github/gschaetz/lib: detached HEAD at a1b2c3d
~ github/gschaetz/experiment: feature-xyz (no upstream)
```

Like `pull --dry-run`, this reads the last fetched state of each upstream, so run `pgit sync` first for current numbers.

Use `--only <platform>` to filter by platform (e.g. `pgit branches --only gitlab`).
Use `--jobs N` to control parallelism (default: 8).

### branches --json

```bash
pgit branches --json   # machine-readable status for every cloned repo
```

Prints a single JSON array on stdout and nothing else. Unlike `status --json`, clean repos are included:

```json
[{"platform": "github", "path": "gschaetz/polygit", "branch": "main", "sha": null,
  "upstream": "origin/main", "ahead": 0, "behind": 0, "state": "tracking"}]
```

`state` is `tracking`, `none` (no upstream), `gone` (upstream deleted on the remote) or `detached`. When detached, `branch` is `null` and `sha` holds the short commit hash. `upstream` is `null` when there is none.

## review

`pgit review` opens a PR/MR for every cloned repo whose current branch has been pushed and is ahead of the default branch:

```bash
pgit review                # prompt per repo (default)
pgit review --all          # one PR title/body for all eligible repos
pgit review --auto         # auto-generate title from branch name, minimal body
pgit review --auto --dry-run
pgit review --base release
pgit review --json
```

Detection: a repo qualifies when it is tracking the same-named upstream branch (`feat/x` → `origin/feat/x`), that branch is ahead of the base, and it is not itself the base branch. Only local refs are read; run `pgit sync` first if you want current numbers.

The PR base is the remote's default branch (`origin/HEAD`, falling back to `main` then `master`). Pass `--base <branch>` to override it (e.g. for release branches).

With `--auto`, PR titles are generated from branch names (`feat/auth` → `feat: auth`). With `--all`, one title/body is prompted for and shared. In interactive mode you get a per-repo prompt with a diff summary and a blank title skips the repo.

`review` creates PRs via the GitHub/GitLab API when a token is available:

```bash
GH_TOKEN=<token> pgit review --auto     # GitHub
GITLAB_TOKEN=<token> pgit review --auto # GitLab
```

Token scopes: GitHub needs `repo`; GitLab needs `api`. Without a token, `pgit review` prints ready-to-click PR/MR URLs for manual creation.

```bash
pgit review --auto --dry-run   # list candidates with planned titles/URLs; creates nothing
pgit review --only github      # review only GitHub repos
pgit review --jobs 4            # parallelism for non-interactive modes (default: 8)
```

`--json` (with `--all` or `--auto`) prints a single JSON array on stdout and nothing else.

```json
[{"platform": "github", "path": "r", "branch": "feat/x", "status": "created", "url": "https://...", "error": null}]
```

`status` is `created` (PR created via API), `manual` (no token — URL only), `planned` (`--dry-run`), or `failed`.

Branches must be pushed first — run `pgit push` before `pgit review`.

## status --json

```bash
pgit status --json   # machine-readable list of dirty repos
```

Prints a single JSON array on stdout and nothing else:

```json
[{"platform": "github", "path": "gschaetz/mousehat", "changed_files": 2}]
```

`changed_files` is the number of entries in `git status --short`. Clean repos are omitted, so the array is empty when there is nothing to commit.

## repos — drift detection

`pgit repos` compares what's actually on disk against your `.pgit` config and reports:

- **Remote mismatch** — repo is at the right path but the git remote differs (e.g. SSH vs HTTPS)
- **Wrong location** — remote is tracked in `.pgit` but cloned to a different directory
- **Untracked** — repo on disk not referenced in `.pgit` at all
- **Missing** — in `.pgit` but not yet cloned (run `pgit sync`)

It then offers to update `.pgit` or rename directories interactively.

## Migrating from repos.yaml

If you were using the `sync.sh` predecessor, rename your `repos.yaml` to `.pgit` — the format is identical.

## Requirements

- Python 3.10+
- git

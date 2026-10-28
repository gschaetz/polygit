# Repo context for AI agents

Published Python package (`pip install polygit`, installed via `uv tool install` per the
user's `setup-new-machine.sh` bootstrap docs — see project memory) providing the `pgit` CLI:
manages multiple git repos (across GitHub/GitLab, multiple orgs/namespaces) from a single
`.pgit` config file. `.pgit` is discovered by walking up from the current directory, so
`pgit` commands work from anywhere inside the repos root — this is in fact what manages the
very `~/development/gitlab` tree these AGENTS.md files live in.

Standard `src`-layout Python package (`pyproject.toml`, `uv.lock` — uses `uv`, not
pip/poetry, for dev dependency management). Hosted on GitHub (moved from GitLab); CI is
`.github/workflows/ci.yml` — test on every push/PR, build+publish to PyPI on `v*.*.*` tags.

Replaced an older `sync.sh` script (see recent commit history) — if you find references to
`sync.sh` elsewhere in the user's dotfiles/bootstrap scripts, they're stale.

## Workflow
- Spec-driven with **OpenSpec** (`openspec/`, default `spec-driven` schema: proposal → specs → design → tasks).
  Propose a change with `/opsx:propose` (Claude Code) or `$openspec-propose` (Codex) and write the spec
  scenarios before the code. Living specs are in `openspec/specs/`, active changes in `openspec/changes/`.
  Project constraints for OpenSpec artifacts are in `openspec/config.yaml`.
- Bug fixes and one-line tweaks don't need a change; a new command, flag, output format or behavior does.
- **Archive a change when it is done.** The PR that finishes its last task runs
  `openspec archive <name> --yes`, which merges its spec deltas into `openspec/specs/`.
- No ADRs: tactical choices go in the change's `design.md`. Revisit if lasting architectural
  commitments start to pile up.
- Ideas not yet proposed live in [docs/roadmap.md](docs/roadmap.md); move an item when it ships.
- Every new scenario gets a test in `tests/test_polygit.py`, and user-visible changes update `README.md`.
- Work on a branch, not directly on `main`.

## Releases
- Version bumps are their own commit ("Bump version to X.Y.Z").
- Tags `v*.*.*` build and publish to PyPI (`.github/workflows/ci.yml`), so never create or push a
  release tag unless the user explicitly asks for that release.

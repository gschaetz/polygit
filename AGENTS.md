# Repo context for AI agents

Published Python package (`pip install polygit`, installed via `uv tool install` per the
user's `setup-new-machine.sh` bootstrap docs — see project memory) providing the `pgit` CLI:
manages multiple git repos (across GitHub/GitLab, multiple orgs/namespaces) from a single
`.pgit` config file. `.pgit` is discovered by walking up from the current directory, so
`pgit` commands work from anywhere inside the repos root — this is in fact what manages the
very `~/development/gitlab` tree these AGENTS.md files live in.

Standard `src`-layout Python package (`pyproject.toml`, `uv.lock` — uses `uv`, not
pip/poetry, for dev dependency management). `.gitlab-ci.yml` presumably builds/publishes on
tag, mirroring `gitlab-ci-generator`'s pattern.

Replaced an older `sync.sh` script (see recent commit history) — if you find references to
`sync.sh` elsewhere in the user's dotfiles/bootstrap scripts, they're stale.

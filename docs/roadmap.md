# Roadmap

Ideas for future enhancements to `pgit`. Work through these one by one; each becomes an OpenSpec change (`/opsx:propose`) before any code.

Shipped: `pgit branches` (see `openspec/specs/branches/`).

## Hosts & remotes
- Support additional hosts (Bitbucket, Azure DevOps, generic SSH) beyond GitHub/GitLab.
- Smarter remote URL parsing for non-standard hosts.

## Repo discovery & navigation
- `pgit diff` — aggregate diff across dirty repos.
- `pgit search <term>` — fuzzy search repos by name/path/remote.
- `pgit log` — recent commits across repos.

## Workflow & automation
- `pgit review` — open PRs for all dirty repos (or mock locally).
- Pre-commit hook integration (`pgit integrate-hooks`).
- Repo tagging/grouping via `.pgit` or a sidecar tags file; filter commands by tag.
- Auto-cleanup / prune command (`pgit clean`).

## UX & reporting
- `pgit status --tag frontend` and similar filters.
- Summary metrics: commit counts, last push dates.
- `pgit export` / `pgit import` for config portability.
- Web UI for visual repo graph and heat-map.

## Misc
- Submodule awareness (detect & report).
- Smarter clone-missing (branch-per-repo tracking).
- Caching layer for faster repeated operations.

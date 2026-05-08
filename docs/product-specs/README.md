# Product Specs

This directory is the canonical home for Coke's product, route, and API surface
index.

`FEATURE_TREE.md` is the entry point for route and endpoint discovery. It is a
repo-local map, not a product roadmap and not a replacement for
`docs/roadmap.md`.

## Rules

- Update `FEATURE_TREE.md` when adding, removing, or renaming user-visible
  routes, bridge endpoints, gateway APIs, worker-triggered product surfaces, or
  deployment entrypoints.
- Keep behavioral intent in specs, ADRs, or architecture docs. Keep this
  directory focused on discoverability.
- If this file becomes generated, the generator command must be documented here
  and wired into repo-OS checks before the generated status is claimed.

# 2026-04-23 Poke Reconstruction Archive

## Goal

Produce a single task-local archive that reconstructs Poke's public
architecture, leaked-prompt signals, third-party reverse-engineering, and the
implications for Coke's upcoming agent refactor.

## Scope

- In scope:
  - official Poke docs, status pages, release notes, FAQs, SDKs, CLI bundles,
    and public package metadata
  - publicly mirrored leaked prompt text and third-party reverse-engineering
    material
  - direct comparison against Coke's current Phase 1 runtime and Phase 2
    direction
- Out of scope:
  - building a runnable OpenPoke clone inside this repository
  - private/internal Poke data or unverifiable claims without public evidence
  - broad consumer-product strategy outside what affects Coke refactor work

## Inputs

- Related task: `tasks/2026-04-23-poke-architecture-reconstruction.md`
- Related ADRs: none
- Related references:
  - `docs/architecture.md`
  - `docs/roadmap.md`
  - `tasks/2026-04-22-poke-competitive-analysis.md`

## Touched Surfaces

- repo-os

## Work Breakdown

1. Collect remaining official Poke evidence, especially MCP, API, CLI, status,
   and release material.
2. Cross-check public leaked prompt mirrors and third-party architecture
   writeups against official artifacts.
3. Write one task-local archive with confidence grading, reconstructed
   architecture, prompt findings, timeline, and Coke-specific recommendations.
4. Run repo-OS verification for the new task and plan files.

## Verification

- Command: `pytest tests/unit/test_repo_os_structure.py -v`
- Expected evidence: repo-OS task/plan structure test passes.
- Command: `zsh scripts/check`
- Expected evidence: repository routing and structure checks pass.

## Notes

The main deliverable is intentionally a single task file because the user wants
one document they can read during the refactor and then stop using.

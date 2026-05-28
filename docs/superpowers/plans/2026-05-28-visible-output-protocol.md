# Visible Output Protocol Plan

> Superseded on 2026-05-29 by the current architecture cut line in
> `docs/ARCHITECTURE.md`.

Do not execute the old protocol-repair plan. The previous version proposed a
second model call to repair malformed or blocked output. That is no longer an
active product or architecture contract.

Current implementation rule:

- The Interaction Agent is the only producer of final assistant chat prose.
- Runtime validation parses the returned `MultiModalResponses` envelope once.
- Malformed, empty, timed-out, blocked, or contract-violating output fails
  closed with structured error disposition and no visible chat message.
- The worker must not ask the model to rewrite bad output.
- The worker must not synthesize template fallback prose.
- The worker must not replace model prose with domain or capability summaries.

Use focused tests that prove strict parsing and fail-closed disposition. Do not
add tests that assert protocol-repair prompts, second-pass visible-content
rewrites, domain-summary replacement, or fallback chat text.

---
kind: plan
status: active
date: 2026-06-02
topic: email-delivery-port
design: docs/superpowers/specs/2026-06-02-email-delivery-port-design.md
---

# Plan: Port Resend email delivery into Python identity_access

Restore the email-send path that was dropped with the `gateway` submodule in
`d1e05b97`. Decisions (locked, do not re-litigate): **synchronous send**,
**all three emails** (verification / password reset / claim), **reuse the
existing Resend account + key**. Behavioral reference: recovered old source at
`.worktrees/worker-d-interface-alias-cleanup/gateway/packages/api/src/lib/email.ts`
and `customer-email.ts`.

Use TDD. Write failing tests first for each task, then implement. Keep commits
small and coherent. Specs/plans/comments/code in English.

## Task 1 — Email sender module (backend)

- Create `coke/domains/identity_access/email.py`:
  - `CustomerEmailSender` Protocol: `send_verification(to, token, email)`,
    `send_password_reset(to, token)`, `send_claim(to, token)`.
  - `ResendEmailSender(api_key, email_from, email_from_name, public_base_url)`:
    builds links (`{web}/auth/verify-email?token=&email=`,
    `{web}/auth/reset-password?token=`, `{web}/auth/claim?token=`) and POSTs to
    `https://api.resend.com/emails` with `httpx`, `Authorization: Bearer <key>`,
    JSON `{from, to, subject, html}`. Raise a clear error on non-2xx / missing id.
  - `NullEmailSender`: logs and no-ops (used without an API key).
- Tests: link shapes, From header formatting (`"Name" <addr>` when name set),
  httpx call asserted via a mock transport, error raised on Resend failure.

## Task 2 — Config

- Add `resend_api_key`, `email_from` (default `noreply@keep4oforever.com`),
  `email_from_name` to `coke/config.py` `Settings` + `from_env`
  (`RESEND_API_KEY` / `EMAIL_FROM` / `EMAIL_FROM_NAME`).
- Production guard: raise `ConfigurationError` if `app_env == "production"` and
  `RESEND_API_KEY` unset (mirror the SiliconFlow guard). Allow `COKE_LLM_FAKE`-style
  bypass only if an existing test bypass pattern applies; otherwise no bypass.
- Tests in the config test module: prod-missing-key raises; local falls back.

## Task 3 — Service wiring

- `IdentityAccessService.__init__`: add `email_sender: CustomerEmailSender | None`
  (default `NullEmailSender()`) and `public_base_url: str = "http://localhost:4040"`.
- Send points:
  - `register_web_account`: after issuing the verification artifact, call
    `email_sender.send_verification(to=email, token=<artifact code>, email=email)`.
  - `issue_password_reset`: after issuing, `send_password_reset`.
  - `resend_artifact`: after marking pending, re-send by artifact type
    (verification vs password reset).
  - Claim: find the claim issuance path in `coke/api/claim_routes.py` and its
    service method; when the claim targets an email address, call `send_claim`.
    Leave channel-only claim flows unchanged.
- Confirm the `<token>` embedded in links is exactly what `verify_email` /
  `reset_password` / claim redemption look up (artifact `code`; check
  `_consume_artifact` and `get_artifact_by_code`). Add a test that the emitted
  link's token round-trips through `verify_email`.
- Tests use a fake sender capturing calls; assert each flow sends once with the
  right recipient/token.

## Task 4 — Resend route + frontend

- Backend: add `POST /api/auth/email-verification/resend` `{email}` in
  `coke/api/auth_routes.py`. Resolve the account's current active verification
  artifact and re-send; if none active, issue a fresh one and send. Return
  `{"accepted": true}`, 202. Avoid account enumeration (generic accepted even for
  unknown email, matching password-reset request behavior).
- Frontend: replace the `unsupported_operation` stub in
  `web/lib/customer-auth.ts:resendCustomerVerification` with a real
  `customerApi.post('/api/auth/email-verification/resend', { email })`, returning
  success/error consistently with `requestCustomerPasswordReset`.
- Tests: backend route test (active artifact re-sent; unknown email still 202);
  update `web` `customer-auth` test for the new call.

## Task 5 — Composition

- `coke/composition.py` (`IdentityAccessService(...)` near line 1222): pass
  `public_base_url=public_base_url` and `email_sender=` built from settings —
  `ResendEmailSender` when `resend_api_key` is set, else `NullEmailSender`.
- Ensure the email_from/name/public_base_url thread through from `Settings`.

## Task 6 — Docs + verification

- Update `docs/deploy.md` Clean Production Environment section: document
  `RESEND_API_KEY`, `EMAIL_FROM` (`noreply@keep4oforever.com`), `EMAIL_FROM_NAME`
  on `coke-api`, and that production startup requires `RESEND_API_KEY`.
- Update `docs/product-specs/FEATURE_TREE.md` if it indexes the auth/email routes
  (add the resend route).
- Run: `black . && isort .`; `zsh scripts/suggest-verification --base HEAD~1`;
  the suggested surfaces; `.venv/bin/python -m pytest tests/unit/coke -q`
  (identity_access + config + auth route tests); `cd web && pnpm test` for the
  customer-auth change; `zsh scripts/check`.
- Do NOT claim done without pasting fresh test output.

## Notes for the executor

- Do not introduce an async/outbox path. Do not add compatibility shims for the
  removed gateway. Do not weaken verify/reset/claim redemption to make a test pass.
- If any send point's email target is genuinely unavailable (e.g. claim has no
  email), document it in the plan rather than inventing one.

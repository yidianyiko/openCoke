# Resend Email Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Coke's Mailgun/SMTP email delivery path with direct Resend SDK sending, then roll the new configuration out to `gcp-coke` and verify a real auth email send.

**Architecture:** Keep `gateway/packages/api/src/lib/email.ts` as the single delivery boundary used by Coke auth routes, but swap its internals to Resend's Node SDK. Remove obsolete Mailgun/SMTP dependencies and env documentation so repository configuration matches the new production-only provider contract.

**Tech Stack:** TypeScript, Hono, Vitest, pnpm, Resend Node SDK, Docker Compose, SSH

---

## Scope Check

This is one vertical migration slice: provider implementation, config/docs, and
deployment validation for the same email path. Keep route behavior and frontend
flow unchanged.

## File Structure

### Modified files

- `gateway/packages/api/package.json`
  Replace `nodemailer` deps with `resend`.
- `gateway/packages/api/src/lib/email.ts`
  Remove Mailgun/SMTP logic and implement direct Resend sending.
- `gateway/packages/api/src/lib/email.test.ts`
  Replace nodemailer-based tests with Resend SDK tests.
- `deploy/env/coke.env.example`
  Document the new `RESEND_API_KEY` contract and delete obsolete vars.
- `docs/deploy.md`
  Update deploy guidance to the Resend-only configuration contract.
- `gateway/pnpm-lock.yaml`
  Record the dependency change.

### Unchanged-but-verified files

- `gateway/packages/api/src/routes/coke-auth-routes.ts`
  Continue calling `sendCokeEmail()` with the existing payload shape.
- `gateway/packages/api/src/routes/coke-auth-routes.test.ts`
  Existing route coverage should keep passing after the provider swap.

---

## Task 1: Replace the API email helper with Resend SDK

**Files:**
- Modify: `gateway/packages/api/package.json`
- Modify: `gateway/packages/api/src/lib/email.ts`
- Modify: `gateway/packages/api/src/lib/email.test.ts`
- Modify: `gateway/pnpm-lock.yaml`

- [ ] **Step 1: Write the failing Resend helper tests**

Replace the nodemailer-centric test setup in
`gateway/packages/api/src/lib/email.test.ts` with a Resend mock:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  sendMock: vi.fn(),
  resendCtorMock: vi.fn(() => ({
    emails: {
      send: mocks.sendMock,
    },
  })),
}));

vi.mock('resend', () => ({
  Resend: mocks.resendCtorMock,
}));

import { sendCokeEmail } from './email.js';

describe('sendCokeEmail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.RESEND_API_KEY = 're_test_key';
    process.env.EMAIL_FROM = 'noreply@keep4oforever.com';
    process.env.EMAIL_FROM_NAME = 'Coke';
    mocks.sendMock.mockResolvedValue({ data: { id: 'email_123' }, error: null });
  });

  afterEach(() => {
    delete process.env.RESEND_API_KEY;
    delete process.env.EMAIL_FROM;
    delete process.env.EMAIL_FROM_NAME;
  });

  it('sends through Resend with the formatted sender name', async () => {
    await expect(
      sendCokeEmail({
        to: 'alice@example.com',
        subject: 'Verify your Coke email',
        html: '<p>hello</p>',
      }),
    ).resolves.toBeUndefined();

    expect(mocks.resendCtorMock).toHaveBeenCalledWith('re_test_key');
    expect(mocks.sendMock).toHaveBeenCalledWith({
      from: '"Coke" <noreply@keep4oforever.com>',
      to: 'alice@example.com',
      subject: 'Verify your Coke email',
      html: '<p>hello</p>',
    });
  });

  it('throws when RESEND_API_KEY is missing', async () => {
    delete process.env.RESEND_API_KEY;

    await expect(
      sendCokeEmail({
        to: 'alice@example.com',
        subject: 'Verify your Coke email',
        html: '<p>hello</p>',
      }),
    ).rejects.toThrow('resend_config_missing');
  });

  it('throws when Resend returns an API error', async () => {
    mocks.sendMock.mockResolvedValue({ data: null, error: { message: 'invalid from' } });

    await expect(
      sendCokeEmail({
        to: 'alice@example.com',
        subject: 'Verify your Coke email',
        html: '<p>hello</p>',
      }),
    ).rejects.toThrow('resend_send_failed:invalid from');
  });
});
```

- [ ] **Step 2: Run the focused helper test to verify the red state**

Run: `pnpm --dir gateway/packages/api test -- src/lib/email.test.ts`

Expected: FAIL because the repository still imports `nodemailer` and does not
call the Resend SDK.

- [ ] **Step 3: Add the Resend dependency and remove nodemailer**

Update `gateway/packages/api/package.json`:

```json
{
  "dependencies": {
    "resend": "^4.6.0"
  },
  "devDependencies": {}
}
```

Delete these entries:

```json
"nodemailer": "^8.0.5"
"@types/nodemailer": "^8.0.0"
```

Then refresh the lockfile:

Run: `pnpm --dir gateway add --filter @clawscale/api resend`

Run: `pnpm --dir gateway remove --filter @clawscale/api nodemailer @types/nodemailer`

Expected: `gateway/pnpm-lock.yaml` updates to include `resend` and remove
`nodemailer`.

- [ ] **Step 4: Implement the minimal Resend-backed helper**

Replace `gateway/packages/api/src/lib/email.ts` with a Resend-only sender:

```ts
import { Resend } from 'resend';

export interface SendCokeEmailInput {
  to: string;
  subject: string;
  html: string;
}

function getResendApiKey(): string {
  const apiKey = process.env['RESEND_API_KEY']?.trim();
  if (!apiKey) {
    throw new Error('resend_config_missing');
  }
  return apiKey;
}

function getEmailFromAddress(): string {
  return process.env['EMAIL_FROM']?.trim() || 'noreply@keep4oforever.com';
}

function getEmailFrom(): string {
  const fromAddress = getEmailFromAddress();
  const fromName = process.env['EMAIL_FROM_NAME']?.trim();
  return fromName ? '"' + fromName + '" <' + fromAddress + '>' : fromAddress;
}

export async function sendCokeEmail(input: SendCokeEmailInput): Promise<void> {
  const resend = new Resend(getResendApiKey());
  const { data, error } = await resend.emails.send({
    from: getEmailFrom(),
    to: input.to,
    subject: input.subject,
    html: input.html,
  });

  if (error) {
    throw new Error('resend_send_failed:' + error.message);
  }

  if (!data?.id) {
    throw new Error('resend_send_failed:missing_id');
  }
}
```

- [ ] **Step 5: Run the focused helper test to verify green**

Run: `pnpm --dir gateway/packages/api test -- src/lib/email.test.ts`

Expected: PASS with 3 passing tests in `src/lib/email.test.ts`.

- [ ] **Step 6: Run auth route regression coverage**

Run: `pnpm --dir gateway/packages/api test -- src/routes/coke-auth-routes.test.ts`

Expected: PASS with the existing Coke auth route tests still green.

---

## Task 2: Remove obsolete Mailgun/SMTP configuration from docs and env templates

**Files:**
- Modify: `deploy/env/coke.env.example`
- Modify: `docs/deploy.md`

- [ ] **Step 1: Update the env template to the Resend-only contract**

Replace the email section in `deploy/env/coke.env.example` with:

```dotenv
# Email delivery
RESEND_API_KEY=replace-me
EMAIL_FROM=noreply@keep4oforever.com
EMAIL_FROM_NAME=Coke
```

Delete these keys from the file:

```dotenv
MAILGUN_API_KEY=
MAILGUN_DOMAIN=
EMAIL_SERVICE=
EMAIL_HOST=
EMAIL_PORT=
EMAIL_ENCRYPTION=
EMAIL_ENCRYPTION_HOSTNAME=
EMAIL_USERNAME=
EMAIL_PASSWORD=
EMAIL_ALLOW_SELFSIGNED=
```

- [ ] **Step 2: Update deploy docs to match the new contract**

In `docs/deploy.md`, replace the current email variable guidance with:

```md
- `RESEND_API_KEY`: required for verification and password-reset email sending
- `EMAIL_FROM`: sender address, recommended `noreply@keep4oforever.com`
- `EMAIL_FROM_NAME`: optional sender display name, for example `Coke`
```

Remove the old Mailgun/SMTP wording so the docs no longer suggest fallback
providers.

- [ ] **Step 3: Verify there are no stale Mailgun/SMTP references in deploy docs**

Run: `rg -n "MAILGUN_|EMAIL_HOST|EMAIL_PORT|EMAIL_USERNAME|EMAIL_PASSWORD|EMAIL_ENCRYPTION|nodemailer" deploy docs gateway/packages/api/src/lib/email.ts`

Expected: only intentional historical references remain outside the migrated
files; the env example, deploy doc, and current email helper no longer mention
Mailgun/SMTP or `nodemailer`.

---

## Task 3: Verify locally, roll out to gcp-coke, and prove a real send

**Files:**
- Modify remotely: `~/coke/.env` on `gcp-coke`

- [ ] **Step 1: Run the complete local verification set**

Run: `pnpm --dir gateway/packages/api test -- src/lib/email.test.ts src/routes/coke-auth-routes.test.ts`

Expected: PASS with zero failing tests.

Run: `pnpm --dir gateway/packages/api build`

Expected: PASS with TypeScript build exit code `0`.

- [ ] **Step 2: Update the remote env to the new contract**

On `gcp-coke`, set:

```dotenv
RESEND_API_KEY=<provided secret>
EMAIL_FROM=noreply@keep4oforever.com
EMAIL_FROM_NAME=Coke
```

Delete these keys from `~/coke/.env` if present:

```dotenv
MAILGUN_API_KEY
MAILGUN_DOMAIN
EMAIL_SERVICE
EMAIL_HOST
EMAIL_PORT
EMAIL_ENCRYPTION
EMAIL_ENCRYPTION_HOSTNAME
EMAIL_USERNAME
EMAIL_PASSWORD
EMAIL_ALLOW_SELFSIGNED
```

- [ ] **Step 3: Restart the deployed stack**

Run: `ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml up -d --build --remove-orphans'`

Expected: `gateway`, `coke-bridge`, and `coke-agent` come up without restart
loops.

- [ ] **Step 4: Verify service health after restart**

Run: `ssh gcp-coke 'curl -sS http://127.0.0.1:4041/health'`

Expected: health response from Gateway.

Run: `ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml logs --tail=50 gateway'`

Expected: no startup errors about missing `RESEND_API_KEY`.

- [ ] **Step 5: Trigger a real auth email send**

Use the existing Coke auth flow against production for
`yidianyiko@foxmail.com`. The simplest path is forgot-password:

Run:

```bash
curl -sS -X POST 'https://coke.keep4oforever.com/api/coke/forgot-password' \
  -H 'content-type: application/json' \
  --data '{"email":"yidianyiko@foxmail.com"}'
```

Expected: JSON response with
`"Password reset instructions were sent if the account exists."`

- [ ] **Step 6: Confirm the provider send path**

Run: `ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml logs --tail=100 gateway'`

Expected: no send exceptions after the request in Step 5.

Then confirm manually that the email arrived at `yidianyiko@foxmail.com` and
the message contains the `/coke/reset-password?token=...` link.

# Kap User Surface Priority Design

## Goal

Shift the Kap redesign so the pages users actually operate inside become the primary visual focus, and bring `/global` onto the same warm homepage language instead of leaving it as a separate dark landing page.

## Problem Statement

The previous redesign over-indexed on `/` as the main stage.

That left two gaps:

- `/auth/*`, `/channels/*`, and `/account/*` are still functional shells with lighter theming instead of feeling like the real Kap product surface.
- `/global` still lives in a separate dark visual world and does not feel like part of the same homepage family.

The correction is not about behavior. It is about where the design energy sits.

## Scope

### In Scope

- `gateway/packages/web/components/customer-auth-shell.tsx`
- `gateway/packages/web/components/customer-shell.tsx`
- customer-facing `/auth/*`, `/channels/*`, and `/account/*` shell styling and page-stage styling
- `gateway/packages/web/components/global-homepage.tsx`
- `gateway/packages/web/app/public-site.css`
- targeted tests covering the revised shells and `/global`

### Out Of Scope

- route changes
- API or state-machine changes
- admin redesign
- homepage information architecture changes beyond keeping visual consistency

## Desired Outcome

### User-Facing Surfaces

The primary user journey should feel like:

1. homepage introduces Kap
2. auth/account/channel pages become the actual product stage
3. the same mascot, typography, sticker-card rhythm, and warm palette continue throughout

That means `/auth/*`, `/channels/*`, and `/account/*` should no longer feel like toned-down support pages.

They should feel like the main product environment users inhabit after the public pitch.

### Global Page

`/global` should remain a WhatsApp-focused funnel, but visually it should read as a specialized Kap entry page built from the same design language as `/`.

It should no longer rely on the separate dark-theme atmosphere as its core identity.

## Visual Direction

### Shared Principles

- warm cream and paper backgrounds
- olive and burnt-orange accents
- thick borders, stamped shadows, and sticker-like CTA treatment
- visible mascot presence, not just a small logo swap
- larger editorial hero moments on user-facing shells
- page content framed as the main stage, not a dashboard card dropped into a shell

### Auth Surfaces

The auth shell should become a stronger branded stage:

- include koala presence inside the auth hero
- add supporting sticker cards / trust notes rather than plain copy blocks
- make the auth form card feel like the main interactive card in a branded scene

### Account And Channel Surfaces

The customer shell should become a warmer, more intentional workspace:

- stronger hero card or spotlight region beside the content
- more obvious connection between shell hero and content stage
- content panels should feel like homepage-grade cards, not neutral utility blocks

### Global Page

The global page should adopt:

- warm Kap background treatment
- sticker CTA language
- mascot presence
- section rhythm closer to homepage blocks and ticker bands

It can keep WhatsApp-specific copy and CTA behavior, but not a separate visual identity.

## Component Strategy

### CustomerAuthShell

Extend the auth hero into a proper branded spotlight with:

- koala hero asset
- short supporting stage card / reassurance card
- stronger headline framing around login / verification / account access

### CustomerShell

Upgrade the shell from "sticky header plus side card" to a clearer product stage:

- keep current navigation and routes
- add mascot / spotlight detail to the hero
- introduce a more deliberate wrapper around the main content region
- preserve readability for operational pages

### GlobalHomepage

Keep the WhatsApp CTA contract intact, but recompose the page around the homepage family:

- same warm atmosphere
- same sticker card conventions
- same mascot language
- same CTA personality

## Testing Strategy

Targeted tests should verify:

- auth shell renders the stronger branded spotlight structure
- customer shell renders the stronger workspace / spotlight structure
- global homepage renders the shared warm Kap structure and mascot presence

Full verification remains:

- `pnpm --dir gateway/packages/web test`
- `pnpm --dir gateway/packages/web build`

## Risks

- stronger visual framing can make user-facing forms and operational content harder to scan if the shell becomes too decorative
- `/global` must stay CTA-focused, so syncing style cannot dilute the WhatsApp conversion path
- customer pages contain real state and alert surfaces, so the warmer design must still preserve contrast and hierarchy

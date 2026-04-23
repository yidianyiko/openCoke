# Kap Public UI Redesign Design

## Goal

Rebuild the gateway web public presentation around the `index (1)(1).html` reference so the site feels like one coherent Kap-branded product while keeping all current outward-facing routes and behaviors intact.

## Recommended Approach

Use a shared visual-system migration rather than a homepage-only reskin.

Why this approach:

- the reference is a full marketing language, not just a hero treatment
- the user explicitly wants outward-facing pages branded as `kap`
- leaving auth, customer account, and customer channel pages on the current style would make the redesign feel partial and inconsistent

Rejected alternatives:

1. Homepage-only reskin
   - fastest
   - fails the "all UI according to this style" requirement
2. Full web-package reskin including `/admin/*`
   - visually complete
   - expands risk into internal admin tooling that the user did not prioritize

## Scope

### In Scope

- `/`
- `/global`
- `/auth/*`
- `/account/*`
- `/channels/*`
- outward-facing metadata and visible brand copy in `gateway/packages/web`
- the shared public shell and customer-facing shell styling
- bilingual copy and locale switching

### Out Of Scope

- `/admin/*`
- backend APIs, schemas, auth behavior, account logic, or route paths
- local storage and cookie key renames unless required for visible UI behavior
- large-scale file or symbol renames across the repository

## Product And UX Constraints

- no functional behavior changes
- keep locale switching on outward-facing pages
- keep existing entry points for sign-in, registration, subscription, and personal WeChat setup
- keep the global WhatsApp page purpose intact while moving it onto the Kap visual system
- preserve mobile usability and desktop polish

## Visual Direction

The new Kap system should directly borrow the reference page's design language:

- warm cream background with olive and burnt-orange accents
- expressive display typography instead of the current clean editorial look
- thick borders, stamped shadows, rounded sticker-like buttons, and card stacks
- playful, bold section rhythm with ticker bands, block sections, and alternating surface colors
- whimsical hero illustration language inspired by the reference mascots
- more opinionated marketing composition instead of the current restrained product-site layout

The implementation should adapt those motifs to Kap instead of literally cloning every PsyGo-specific detail.

## Information Architecture

### Homepage `/`

Replace the current homepage structure with a landing-page structure closer to the reference:

1. sticky marketing header with Kap wordmark, locale switch, sign-in, and primary CTA
2. hero with bold three-line value proposition, dual CTA, proof stats, and playful illustration/chat stage
3. ticker band reinforcing the operating idea
4. capability grid that maps existing Coke/Kap product ideas into the reference's large card rhythm
5. scenario grid showing concrete use cases and file-like outcomes
6. social proof / quote band
7. close CTA block that still routes users into registration or setup
8. footer

Functional preservation:

- header sign-in/register links stay live
- locale switch stays in header
- CTA destinations still use current routes
- no forms or flows are removed; they are repositioned into the new structure

### Global Page `/global`

Keep the WhatsApp-specific funnel, but restyle it to match the same Kap visual language instead of the current separate "global" style.

### Auth Pages `/auth/*`

Keep current forms and validation flows, but move them into the Kap marketing shell so login/register/claim/reset feel like part of the same brand.

### Customer Account And Channel Pages `/account/*`, `/channels/*`

Keep current data-driven and stateful behavior, but replace the current dark customer shell and neutral channel styling with the shared Kap surface system, buttons, type, and cards.

## Branding Strategy

Visible brand should change from `coke` / `Coke AI` to `kap` / `Kap AI` across outward-facing pages.

That includes:

- shell wordmarks
- metadata titles and descriptions where outward-facing
- visible copy in homepage, global page, auth hero copy, customer layout copy, channel/account page copy, and footer copy

It does not require:

- internal component/file names to be renamed immediately
- storage keys such as locale or auth legacy keys to change in this task
- API route names to change

## Component Strategy

### Shared Styling

Refactor `gateway/packages/web/app/public-site.css` into the canonical Kap public visual system and extend it to support:

- new homepage sections
- shared sticker/button styles
- global page alignment
- auth shell alignment
- customer account/channel alignment

### Shell Reuse

Keep the shared shell model instead of hardcoding headers per page. Update:

- `CokePublicShell` to present Kap branding and the new header treatment
- `CustomerAuthShell` to inherit the new marketing shell styling
- `CustomerShell` to move off the current dark dashboard look and onto the Kap system where appropriate

### Homepage Composition

Rework `coke-homepage.tsx` around the new marketing structure rather than patching the existing sections in place. Reuse existing i18n-driven content where it still fits, but prefer a reference-aligned section rhythm.

### Copy Source

Continue using `lib/i18n.ts` as the source of truth for visible copy. Introduce or reshape message groups as needed to support:

- new homepage section labels
- Kap brand name/tagline
- outward-facing brand consistency

## Data And Behavior Boundaries

No new backend data is needed.

Existing client behavior must remain untouched:

- locale persistence continues working
- form submissions stay the same
- customer setup state machines stay the same
- all route-level guards and redirects stay the same

This is a presentation-layer redesign plus outward-facing brand rename.

## Error Handling

Because behavior stays intact, error handling should follow current code paths.

UI-specific expectations:

- existing error banners and inline form errors remain visible and readable in the new theme
- channel/account warning states get the same severity semantics under the new design language
- no decorative styling should reduce contrast or hide operational states

## Testing Strategy

### Automated

Primary verification uses gateway web tests, focused on:

- homepage rendering
- global page rendering
- root metadata
- auth pages that depend on shared shell branding
- customer-facing pages most affected by shell/theme changes

Targeted files should be updated first, with a broader `pnpm --dir gateway/packages/web test` run if the shared-shell changes create wider fallout.

### Manual Smoke

If local rendering is practical during implementation, manually inspect:

- `/`
- `/global`
- `/auth/login`
- `/auth/register`
- `/account/subscription`
- `/channels/wechat-personal`

Focus on mobile layout, CTA visibility, locale switch behavior, and visual consistency.

## Risks

- `lib/i18n.ts` currently carries a large amount of page copy; homepage restructuring may require careful message reshaping without breaking existing tests.
- `public-site.css` already styles multiple outward-facing surfaces; broad replacement can cause regressions if selectors are not scoped carefully.
- customer-facing pages are not pure marketing pages, so the reference style needs to be adapted without hurting operational clarity.

## Implementation Units

1. Kap branding and shared visual tokens
2. Homepage restructure to the reference-style landing page
3. Shared auth/global/customer shell convergence onto the Kap system
4. Targeted test and metadata updates

# Kap Koala Mascot Design

## Goal

Replace the current letter-based Kap mascot and outward-facing brand icon treatment with a hand-drawn sticker-style koala that matches the homepage visual language and can also work at small icon sizes.

## Recommended Approach

Use a two-asset mascot system built from the same visual character:

1. a full-body hand-drawn koala illustration for the homepage hero
2. a simplified koala head badge for navigation, splash, footer, and icon surfaces

Why this approach:

- the homepage needs a larger, expressive mascot instead of the current `K` / `AI` blocks
- favicon and small navigation marks need a cleaner silhouette than a full illustration
- one shared character keeps the Kap brand coherent across homepage, auth, account, channel, and global entrypoints

Rejected alternatives:

1. one large PNG reused everywhere
   - fastest
   - becomes muddy at favicon and header sizes
2. keep the current wordmark and only add a koala in the hero
   - lower risk
   - does not satisfy the request to use the koala where brand icons are needed

## Scope

### In Scope

- homepage hero mascot
- outward-facing public and customer-facing brand marks in `gateway/packages/web`
- `logo.png` / public metadata icon usage
- favicon replacement
- targeted tests that assert koala assets are mounted on brand entrypoints

### Out Of Scope

- route changes
- backend behavior
- admin information architecture or copy rewrites
- a full multi-pose mascot library beyond the hero + badge pair

## Visual Direction

The koala should fit the current Kap homepage style:

- hand-drawn sticker feel, not corporate flat iconography
- warm grey fur, cream belly/muzzle, charcoal nose, and subtle olive / burnt-orange accent details
- soft uneven outlines and slight paper-cut sticker edge feel
- friendly and calm expression rather than cartoon chaos
- readable silhouette at small sizes, especially the head badge

The character should be a pure koala shape, with no embedded `K`, no letter mascot behavior, and no text inside the illustration.

## Asset Strategy

### Hero Asset

- file under `gateway/packages/web/public/`
- transparent background
- full-body or bust-plus-paws composition that still reads on the cream hero background
- used in place of the current `K` and `AI` badge blocks in the homepage hero illustration area

### Badge Asset

- file under `gateway/packages/web/public/`
- transparent background
- face-forward or slightly angled koala head optimized for 24px to 48px usage
- used for brand marks in the public shell, customer shell, global page brand, splash card, footer, and metadata icon path

### Icon Path

- the shared outward-facing icon should point to the koala badge asset instead of the current text-like logo treatment
- `favicon.ico` should be refreshed from the badge asset so the browser tab matches the new brand

## Component Strategy

### Homepage

Replace the current hero mascot blocks in `coke-homepage.tsx` with the new koala hero asset while keeping the surrounding stage card, chips, stickers, and CTA structure intact.

### Shared Brand Entrypoints

Update outward-facing brand anchors and splash surfaces to render:

- koala badge image
- `kap` wordmark text beside it where layout has enough space

This keeps accessibility and brand readability without using text as the mascot itself.

### Global Page

Update the `/global` brand anchor to use the koala badge so the WhatsApp-focused page feels like part of the same Kap identity.

## CSS Expectations

- add explicit styles for a reusable brand image wrapper and wordmark pairing
- preserve current header height and mobile breakpoints
- hero mascot styling should support a larger image instead of the current pill-like blocks
- small icon styling should avoid distortion and keep crisp edges

## Testing Strategy

Targeted tests should assert:

- homepage hero renders a koala mascot image
- public shell brand renders a koala badge image
- global homepage brand renders a koala badge image
- outward-facing metadata still points to a brand icon path that exists

Manual smoke should verify:

- homepage hero looks intentional on desktop and mobile
- header brand remains balanced and readable
- favicon/browser tab reflects the koala badge

## Risks

- a detailed generated illustration may look good in the hero but fail at 24px sizes, which is why the badge asset needs to be separately optimized
- replacing wordmark-only anchors with image-plus-wordmark needs careful CSS updates to avoid breaking compact layouts
- favicon generation can lag behind in browser caches, so local verification should use hard refresh or a new browser session

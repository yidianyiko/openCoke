# Kap Homepage Content Reset Implementation Plan

## Goal

Turn the homepage back into product-facing Kap messaging and simplify the `/global` hero into one clean WhatsApp entry illustration.

## Steps

1. Write failing tests for homepage copy removal and global hero simplification.
2. Update shared customer shell copy so it speaks to users instead of internal route structure.
3. Replace homepage capability, scenario, quote, and proof content with real product messaging.
4. Recompose `/global` hero to keep one koala-led scene and remove the floating-note clutter.
5. Run targeted tests, full web tests, and a production build.

## Verification

- `pnpm --dir gateway/packages/web test -- components/coke-homepage.test.tsx components/global-homepage.test.tsx 'app/(customer)/auth/layout.test.tsx' 'app/(customer)/channels/layout.test.tsx' 'app/(customer)/account/layout.test.tsx'`
- `pnpm --dir gateway/packages/web test`
- `pnpm --dir gateway/packages/web build`


# Kap Homepage Content Reset Design

## Goal

Remove internal "redesign explanation" copy from the public Kap experience and simplify the `/global` hero so it reads like a clean product entry page instead of an over-stacked illustration.

## Problem Statement

The current homepage explains the redesign itself instead of presenting Kap to end users.

That creates two visible problems:

- homepage capability, scenario, quote, and proof sections read like internal rollout notes
- `/global` uses too many competing hero elements, so the koala, chat card, stickers, and floating notes fight each other instead of forming one clear visual

## Scope

### In Scope

- `gateway/packages/web/components/coke-homepage.tsx`
- `gateway/packages/web/components/global-homepage.tsx`
- `gateway/packages/web/lib/i18n.ts`
- `gateway/packages/web/app/public-site.css`
- homepage and global-page tests
- customer shell copy where it still reads like internal route language

### Out Of Scope

- route changes
- API changes
- auth and customer page business logic
- mascot asset generation

## Desired Outcome

### Homepage

The homepage should describe Kap as a product:

- what Kap helps you do
- what real tasks it can move forward
- where to start next

It should not describe the redesign, route strategy, or brand migration to end users.

### Global Page

`/global` should stay WhatsApp-only, but the hero should become a simpler product scene:

- one clear koala-led hero illustration
- one supporting WhatsApp conversation element
- no extra floating notes competing with the main visual
- direct copy focused on starting the conversation

### Shared User-Facing Copy

Customer-facing shell copy should stay product-facing:

- continue your Kap flow
- verify and reconnect in one place
- keep the next step visible

It should avoid internal phrases about neutral route structure or system migration.

## Testing Strategy

Tests should prove:

- homepage no longer renders the redesign-explanation phrases
- homepage renders product-facing replacement copy
- global hero renders the simplified scene and removes floating-note clutter
- shared customer shells still render correctly with more user-facing copy


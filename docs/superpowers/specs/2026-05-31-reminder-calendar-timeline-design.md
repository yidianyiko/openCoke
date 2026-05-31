---
kind: design_spec
status: draft
authors:
  - Codex
created: 2026-05-31
related:
  - docs/product-specs/FEATURE_TREE.md
  - docs/ARCHITECTURE.md
  - web/app/(customer)/account/reminders/page.tsx
  - web/lib/customer-reminders.ts
---

# Reminder Calendar Timeline Design

## 1. Problem statement

The customer reminders page at `/account/reminders` currently behaves like a
weekly card board: seven day columns, active reminders grouped by local date,
and a drawer for create/edit actions. This is useful for inventory, but it does
not feel like a calendar. Users cannot read the week as time, choose a time slot
directly, or quickly understand where the next reminder sits in the day.

The current product contract says users can create, view, edit, complete,
delete, schedule, unschedule, and manage reminders through conversation and the
calendar page. The web calendar should therefore optimize for planning reminder
time, not only listing reminders.

The target experience is a weekly planning calendar inspired by proven task
calendar patterns:

- TickTick uses multiple calendar views and its week calendar centers planning
  on a timeline; its help docs describe arranging tasks by dragging them into
  the calendar and moving all-day tasks onto timeline points.
- Todoist's calendar layout offers week/month grids, click-to-create tasks on a
  date, no-date scheduling, drag rescheduling, and optional future occurrence
  visibility.
- Google Calendar Tasks lets users create and manage tasks inside Calendar, so
  a task can be placed directly in calendar context.
- Notion Calendar emphasizes fast calendar navigation and shortcuts; the useful
  lesson for Coke is not feature parity, but keeping common calendar movement
  cheap.

## 2. Goals

- Replace the current weekly board with a week timeline that shows time of day.
- Let users create a reminder by selecting a day/time slot in the calendar.
- Keep completion and deletion fast from reminder cards.
- Preserve the current customer reminder API contract for this iteration.
- Keep the implementation small enough to verify through focused web tests.
- Avoid introducing a full third-party calendar engine before Coke needs
  drag-drop, external calendar overlays, or complex recurrence expansion.

## 3. Non-goals

- Drag-and-drop reminder rescheduling.
- Month view, agenda view, or multi-view switching.
- Unscheduled reminder pools.
- Shared-reminder or imported-calendar visual overlays.
- Backend API changes or reminder domain behavior changes.
- Recurrence expansion beyond what the current list API already returns.

These are intentionally deferred. The first iteration should make the existing
week page feel like a real planning surface without changing the domain
contract.

## 4. Proposed experience

### Page frame

`/account/reminders` remains the primary customer reminder calendar page. The
page title changes from `Weekly reminder board` to `Reminder calendar`.

The page has three visible regions:

1. A calendar toolbar with previous week, today, next week, current week range,
   and `New reminder`.
2. A compact week summary showing total active reminders in the selected week,
   remaining reminders today, and the next upcoming reminder if one exists.
3. A week timeline with seven day columns and hourly rows.

### Timeline

The default visible range is hour slots `06:00` through `22:00`, inclusive.
This means reminders from `06:00` through `22:59` are shown in the main
timeline. This matches the common planning window and follows the same product
lesson as TickTick's hidden overnight hours: the calendar should not spend most
of the screen on low-value time.

Each day column has:

- A day header with weekday, date, and a visual today marker.
- An `Outside visible hours` strip when that day has reminders before `06:00`
  or at/after `23:00`.
- Hour slots from `06:00` to `22:00`, inclusive.

Clicking an hour slot opens the existing reminder drawer in create mode and
prefills `localDate` plus the clicked `localTime`. Clicking the top-level `New
reminder` button keeps the current behavior: default to today and the next
future quarter-hour slot when applicable.

### Reminder items

Reminder cards in the timeline show:

- local time
- title
- repeat badge when the reminder is daily or weekly
- timezone only when the reminder is non-repeating or when timezone context is
  otherwise more useful than a repeat badge

Clicking the card body opens the edit drawer. Inline card actions remain
available:

- `Edit`
- `Complete`
- `Delete`

The UI should use `Delete` for personal reminders, matching the current Coke
terminology that cancellation of a personal reminder means deletion. The
existing frontend helper can keep calling the current cancel endpoint until the
API is renamed; this design does not require a backend rename.

Multiple reminders at the same hour stack vertically inside the hour slot. This
avoids a first-iteration collision layout and keeps dense days readable.

## 5. Component design

The implementation can stay inside
`web/app/(customer)/account/reminders/page.tsx` for the first pass, but the page
should be organized around clear local units:

- `CalendarToolbar`: previous/today/next navigation, week label, and new
  reminder action.
- `WeekSummary`: derived reminder counts and next reminder display.
- `WeekTimeline`: seven day columns, visible hours, outside-hours strips, and
  empty-slot click handling.
- `ReminderCalendarItem`: timeline card and lifecycle actions.
- `ReminderForm`: existing drawer form, extended only to accept a day/time
  initial value.

Helper functions should remain deterministic and testable:

- `buildHourSlots(startHour, endHourInclusive)`
- `isOutsideVisibleHours(reminder, startHour, endHourInclusive)`
- `hourSlotForReminder(reminder)`
- `summarizeWeek(reminders, now)`

No third-party calendar package is needed in this iteration.

## 6. Data flow

The page continues to load reminders with:

```ts
listCustomerReminders({ from, to, states: ['active'] })
```

The selected week continues to be Monday through Sunday using the existing
`startOfLocalWeek` behavior. Reminders are grouped by `localDate`, then split
into outside-visible-hours and visible-hour buckets.

Create, update, complete, and delete continue to use the existing helper
functions from `web/lib/customer-reminders.ts`:

- `createCustomerReminder`
- `updateCustomerReminder`
- `completeCustomerReminder`
- `cancelCustomerReminder`

After successful mutations, the page reloads the selected week as it does now.
Stale list response protection stays in place.

## 7. Error and empty states

Existing authentication and conversation-required behavior remains unchanged.

Loading state should appear above the timeline and should not erase the current
calendar structure unless there is no data yet. This prevents week navigation
from feeling like a full page reset.

Empty week:

- Show the timeline grid.
- Show low-emphasis empty copy inside day columns or slots only where needed.
- Do not replace the calendar with a large empty-state panel.

Save and lifecycle errors keep the existing inline error pattern. Past-time
creation should continue to surface the existing `invalid_schedule` message
instead of silently changing the selected time.

## 8. Responsive behavior

Desktop:

- The timeline uses a fixed left time gutter and seven flexible day columns.
- The timeline scrolls horizontally if the viewport cannot support seven
  columns without cramped text.
- Hour rows have stable height so cards and empty slots do not shift layout.

Mobile:

- Keep the same week timeline model, but allow horizontal scrolling across day
  columns.
- Keep action buttons compact and avoid text overflow.
- The drawer remains below the calendar in the DOM as it does now unless a
  later implementation chooses a modal pattern.

The design should not use oversized marketing composition. This is an account
management tool, so density and scanability matter more than decorative layout.

## 9. Accessibility

- The timeline region has an explicit label such as `Selected week reminder
  timeline`.
- Each time slot button includes the day and hour in its accessible name.
- Reminder cards expose the reminder title and local time.
- Inline actions remain real buttons and do not depend on hover-only affordance.
- Focus outlines must be visible on slots, cards, and action buttons.

## 10. Verification

The focused implementation should update the existing reminders page tests and
cover:

- Loads active reminders for the selected Monday-Sunday week.
- Shows the new `Reminder calendar` title and week summary.
- Places visible-hour reminders inside the matching day/hour slot.
- Places before-06:00 or at/after-23:00 reminders in the outside-hours strip.
- Opens create drawer from an empty slot with the selected date and time.
- Keeps top-level `New reminder` defaulting to the next future slot for today.
- Keeps edit, complete, and delete/cancel actions working.
- Preserves auth redirect and conversation-required behavior.
- Ignores stale list responses after week navigation.

Run:

```sh
cd web && pnpm test -- app/\(customer\)/account/reminders/page.test.tsx
```

Then run diff-aware repository verification:

```sh
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

If only the web reminders page and its tests change, the expected broader check
is the web test/build surface suggested by the verification router.

## 11. References

- TickTick Calendar: https://help.ticktick.com/articles/7055782166172532736
- TickTick Calendar FAQ: https://help.ticktick.com/articles/7063851189372190720
- TickTick Calendar View Options:
  https://help.ticktick.com/articles/7055782085826445312
- Todoist Calendar Layout:
  https://www.todoist.com/help/articles/use-the-calendar-layout-in-todoist-lPHRQTu0o
- Google Calendar Tasks:
  https://support.google.com/calendar/answer/9901136?co=GENIE.Platform%3DDesktop&hl=en
- Notion Calendar Shortcuts:
  https://www.notion.com/help/notion-calendar-keyboard-shortcuts

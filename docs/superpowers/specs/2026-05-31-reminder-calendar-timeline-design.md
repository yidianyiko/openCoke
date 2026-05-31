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

The summary uses browser-local `now` only to decide which reminders are still
upcoming. `Remaining today` counts active reminders whose `localDate` equals the
browser-local current date and whose `localTime` is greater than or equal to the
current `HH:mm`. `Next` is the first active reminder in the selected week whose
`localDate` is after today or whose `localDate` is today and `localTime` has not
passed. The summary does not exclude outside-visible-hours reminders.

### Timeline

The default visible range is hour slots `06:00` through `22:00`, inclusive.
This means reminders from `06:00` through `22:59` are shown in the main
timeline. This matches the common planning window and follows the same product
lesson as TickTick's hidden overnight hours: the calendar should not spend most
of the screen on low-value time.

Slot placement uses reminder-local values exactly as returned by the customer
reminders API:

- `localDate` chooses the day column. The frontend must not convert the reminder
  through UTC before choosing a column.
- `localTime.slice(0, 2)` chooses the hour slot for reminders in the visible
  range.
- Cards inside a day/hour slot are sorted by full `localTime` ascending, then
  by title, then by id for deterministic ordering.
- Cards preserve the full minute display, so `06:15` and `06:45` both appear in
  the `06:00` slot but still render their exact times.

Timezone and daylight-saving behavior stays reminder-local for this iteration.
The page treats `localDate`, `localTime`, and `timezone` as display/read-model
facts from the Reminder domain; it does not recompute the local occurrence from
UTC in the browser. A reminder on a daylight-saving boundary still renders in
the day/hour given by its own local fields.

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

Outside-hours reminders use the same card component and the same `Edit`,
`Complete`, and `Delete` actions as visible-hour reminders. The strip appears
below the day header and above the `06:00` slot. Items are sorted by full
`localTime` ascending. Show at most three outside-hours cards by default; if
more exist, show a passive `+N more outside visible hours` line after the third
card. The first iteration does not need to expand that collapsed count because
editing those hidden cards would require a secondary interaction model.

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

The grouping logic must not parse `timezone` to shift reminder placement. It
uses `timezone` only for display and for the existing create/edit form value.
This keeps the web page aligned with the Reminder domain's calendar read model.

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

- The timeline uses seven flexible day columns, with each hour slot showing its
  own time label. Per-day labels keep the visible time axis accurate when only
  some days need an outside-visible-hours strip.
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
- The first iteration uses ordinary document tab order rather than custom grid
  keyboard handling. Users can tab through toolbar controls, time-slot buttons,
  reminder cards, and inline actions in visual order.
- Arrow-key navigation is out of scope unless the implementation chooses
  semantic grid roles. If semantic grid roles are used, arrow keys must move
  between adjacent day/hour cells without trapping focus.

## 10. Verification

The focused implementation should update the existing reminders page tests and
cover:

- Loads active reminders for the selected Monday-Sunday week.
- Shows the new `Reminder calendar` title and week summary.
- Places visible-hour reminders inside the matching day/hour slot.
- Places non-hour reminders by hour bucket and sorts them by full local time.
- Places before-06:00 or at/after-23:00 reminders in the outside-hours strip.
- Keeps reminder placement based on `localDate` and `localTime` without
  UTC-shifting across timezones or daylight-saving boundary dates.
- Shows at most three outside-hours reminders and a passive overflow count when
  a day has more than three.
- Opens create drawer from an empty slot with the selected date and time.
- Keeps top-level `New reminder` defaulting to the next future slot for today.
- Keeps edit, complete, and visible `Delete` actions working while the delete
  action continues calling `cancelCustomerReminder`.
- Preserves auth redirect and conversation-required behavior.
- Ignores stale list responses after week navigation.

Run:

```sh
cd web && pnpm test -- app/\(customer\)/account/reminders/page.test.tsx
cd web && pnpm build
```

Then run diff-aware repository verification:

```sh
zsh scripts/suggest-verification --base HEAD
zsh scripts/review-trigger --base HEAD
```

If the router suggests a web surface, run that surface rather than relying only
on the focused test file. If the router suggests additional repo-OS checks
because the spec or plan changed, run those checks too.

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

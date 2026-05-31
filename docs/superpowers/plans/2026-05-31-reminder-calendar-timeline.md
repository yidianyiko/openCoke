# Reminder Calendar Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the customer reminders weekly card board with a weekly time-axis planning calendar that supports click-to-create slots, reminder-local placement, outside-hours handling, and fast edit/complete/delete actions.

**Architecture:** Keep the implementation inside the existing customer reminders page for this iteration. Add deterministic local helpers for hour slots, reminder bucketing, and week summary; render those helpers through small local components; keep the current customer reminder API helpers unchanged.

**Tech Stack:** Next.js app router, React 19 client component, TypeScript, Vitest jsdom tests, existing `web/app/public-site.css` styles.

---

**Plan Status:** draft
**Status Date:** 2026-05-31
**Freshness Check:** Verify against current `main`, `docs/ARCHITECTURE.md`, `docs/product-specs/FEATURE_TREE.md`, `docs/superpowers/specs/2026-05-31-reminder-calendar-timeline-design.md`, and the touched web files before execution.

## Scope

In scope:

- `web/app/(customer)/account/reminders/page.tsx`
- `web/app/(customer)/account/reminders/page.test.tsx`
- `web/app/public-site.css`

Out of scope:

- `web/lib/customer-reminders.ts`
- backend API changes
- drag-and-drop rescheduling
- month or agenda view
- unscheduled reminder pool
- shared/imported calendar overlays
- recurrence expansion beyond records returned by the current list API

Execution note: if the main worktree contains unrelated dirty files, do not edit or stage them. Use an isolated worktree for implementation if needed.

## Task 1: Timeline Data Helpers And Summary

**Files:**

- Modify: `web/app/(customer)/account/reminders/page.test.tsx`
- Modify: `web/app/(customer)/account/reminders/page.tsx`

- [ ] **Step 1: Write failing tests for the calendar title and summary**

In `web/app/(customer)/account/reminders/page.test.tsx`, update the default reminders in `beforeEach` to include same-hour non-hour reminders, an outside-hours reminder, and a different timezone reminder that must stay on its own `localDate`:

```ts
listMock.mockResolvedValue({
  ok: true,
  data: {
    reminders: [
      makeReminder({ durationMinutes: 60, localTime: '09:30' }),
      makeReminder({ id: 'rem-2', title: 'Call mom', localDate: '2026-05-15', localTime: '20:00' }),
      makeReminder({ id: 'rem-3', title: 'Early flight', localDate: '2026-05-13', localTime: '05:45' }),
      makeReminder({ id: 'rem-4', title: 'Standup prep', localDate: '2026-05-13', localTime: '09:05' }),
      makeReminder({
        id: 'rem-5',
        title: 'DST local check',
        localDate: '2026-05-14',
        localTime: '06:15',
        timezone: 'America/Los_Angeles',
      }),
    ],
  },
});
```

Replace the first test body with assertions for the new title and summary:

```ts
it('loads active reminders for the selected Monday-Sunday week and shows a calendar summary', async () => {
  renderPage();
  await flushTicks(3);

  expect(listMock).toHaveBeenCalledWith({
    from: '2026-05-11',
    to: '2026-05-17',
    states: ['active'],
  });
  expect(container.textContent).toContain('Reminder calendar');
  expect(container.textContent).toContain('May 11 - May 17, 2026');
  expect(container.textContent).toContain('5 active this week');
  expect(container.textContent).toContain('0 remaining today');
  expect(container.textContent).toContain('Next: Thu 06:15 - DST local check');
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```sh
cd web && pnpm test -- app/\(customer\)/account/reminders/page.test.tsx
```

Expected: FAIL because `Reminder calendar` and summary text do not exist yet.

- [ ] **Step 3: Add local constants and helper functions**

In `web/app/(customer)/account/reminders/page.tsx`, add these constants and helper types after `AUTH_ERRORS`:

```ts
const VISIBLE_START_HOUR = 6;
const VISIBLE_END_HOUR = 22;
const MAX_OUTSIDE_HOURS_ITEMS = 3;

interface WeekSummary {
  total: number;
  remainingToday: number;
  nextReminder: CustomerReminder | null;
}

interface DayReminderBuckets {
  outside: CustomerReminder[];
  byHour: Map<number, CustomerReminder[]>;
}
```

Add these helpers after `addDays`:

```ts
function buildHourSlots(startHour: number, endHourInclusive: number): number[] {
  return Array.from({ length: endHourInclusive - startHour + 1 }, (_, index) => startHour + index);
}

function formatHour(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`;
}

function reminderHour(reminder: CustomerReminder): number {
  return Number(reminder.localTime.slice(0, 2));
}

function compareReminders(a: CustomerReminder, b: CustomerReminder): number {
  return (
    a.localTime.localeCompare(b.localTime) ||
    a.title.localeCompare(b.title) ||
    a.id.localeCompare(b.id)
  );
}

function isOutsideVisibleHours(
  reminder: CustomerReminder,
  startHour: number,
  endHourInclusive: number,
): boolean {
  const hour = reminderHour(reminder);
  return Number.isNaN(hour) || hour < startHour || hour > endHourInclusive;
}

function buildDayBuckets(
  reminders: CustomerReminder[],
  startHour: number,
  endHourInclusive: number,
): DayReminderBuckets {
  const byHour = new Map<number, CustomerReminder[]>();
  for (const hour of buildHourSlots(startHour, endHourInclusive)) {
    byHour.set(hour, []);
  }
  const outside: CustomerReminder[] = [];

  for (const reminder of [...reminders].sort(compareReminders)) {
    if (isOutsideVisibleHours(reminder, startHour, endHourInclusive)) {
      outside.push(reminder);
      continue;
    }
    byHour.get(reminderHour(reminder))?.push(reminder);
  }

  return { outside, byHour };
}

function nowLocalTime(now: Date): string {
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
}

function summarizeWeek(reminders: CustomerReminder[], now: Date): WeekSummary {
  const today = toLocalDate(now);
  const currentTime = nowLocalTime(now);
  const upcoming = [...reminders]
    .filter((reminder) => reminder.localDate > today || (reminder.localDate === today && reminder.localTime >= currentTime))
    .sort((a, b) => a.localDate.localeCompare(b.localDate) || compareReminders(a, b));

  return {
    total: reminders.length,
    remainingToday: reminders.filter((reminder) => reminder.localDate === today && reminder.localTime >= currentTime).length,
    nextReminder: upcoming[0] ?? null,
  };
}
```

- [ ] **Step 4: Render the new title and summary while keeping the existing board body temporarily**

In `CustomerRemindersPage`, add:

```ts
const summary = useMemo(() => summarizeWeek(reminders, new Date()), [reminders]);
```

Change the `h1` and body copy:

```tsx
<h1 className="customer-panel__title">Reminder calendar</h1>
<p className="customer-panel__body">Plan active reminders by day and time for the selected Monday-Sunday week.</p>
```

Add this summary block after the weekbar and before loading/error notes:

```tsx
<div className="customer-reminder-summary" aria-label="Selected week reminder summary">
  <span>
    <strong>{summary.total}</strong>
    {summary.total === 1 ? ' active this week' : ' active this week'}
  </span>
  <span>
    <strong>{summary.remainingToday}</strong>
    {summary.remainingToday === 1 ? ' remaining today' : ' remaining today'}
  </span>
  <span>
    {summary.nextReminder ? (
      <>
        Next:{' '}
        {new Date(`${summary.nextReminder.localDate}T00:00:00`).toLocaleDateString('en-US', {
          weekday: 'short',
        })}{' '}
        {summary.nextReminder.localTime} - {summary.nextReminder.title}
      </>
    ) : (
      'No upcoming reminders this week'
    )}
  </span>
</div>
```

- [ ] **Step 5: Run the focused test and commit this slice**

Run:

```sh
cd web && pnpm test -- app/\(customer\)/account/reminders/page.test.tsx
```

Expected: PASS. Commit:

```sh
git add web/app/\(customer\)/account/reminders/page.tsx web/app/\(customer\)/account/reminders/page.test.tsx
git commit -m "feat: add reminder calendar summary"
```

## Task 2: Week Timeline Rendering And Slot Creation

**Files:**

- Modify: `web/app/(customer)/account/reminders/page.test.tsx`
- Modify: `web/app/(customer)/account/reminders/page.tsx`
- Modify: `web/app/public-site.css`

- [ ] **Step 1: Add failing tests for reminder-local timeline slots, time-slot click creation, and existing top-level New reminder behavior**

In `web/app/(customer)/account/reminders/page.test.tsx`, add this test after the summary test:

```ts
it('places reminders in reminder-local timeline hour slots and sorts by full local time', async () => {
  renderPage();
  await flushTicks(3);

  const wed0900Slot = container.querySelector('[data-testid="slot-2026-05-13-09"]') as HTMLElement | null;
  expect(wed0900Slot?.textContent).toContain('Standup prep');
  expect(wed0900Slot?.textContent).toContain('09:05');
  expect(wed0900Slot?.textContent).toContain('Pay rent');
  expect(wed0900Slot?.textContent).toContain('09:30');
  expect(wed0900Slot?.textContent?.indexOf('Standup prep')).toBeLessThan(
    wed0900Slot?.textContent?.indexOf('Pay rent') ?? -1,
  );

  const thu0600Slot = container.querySelector('[data-testid="slot-2026-05-14-06"]') as HTMLElement | null;
  expect(thu0600Slot?.textContent).toContain('DST local check');
  expect(thu0600Slot?.textContent).toContain('06:15');
});
```

Add this test after the default-create test:

```ts
it('opens create drawer from an empty timeline slot with the selected local date and hour', async () => {
  renderPage();
  await flushTicks(3);

  const slotButton = container.querySelector('[data-testid="slot-button-2026-05-16-14"]') as HTMLButtonElement | null;
  slotButton?.click();
  await flushTicks(1);

  expect((container.querySelector('input[name="localDate"]') as HTMLInputElement | null)?.value).toBe('2026-05-16');
  expect((container.querySelector('input[name="localTime"]') as HTMLInputElement | null)?.value).toBe('14:00');
});
```

Keep the existing `defaults a new reminder for today to a future time slot` test unchanged. It proves top-level `New reminder` still uses `nextFutureTimeSlot()`.

- [ ] **Step 2: Update `DrawerState` and form initialization for slot-specific time**

In `page.tsx`, change `DrawerState` and `emptyForm`:

```ts
type DrawerState =
  | { mode: 'closed' }
  | { mode: 'create'; initialDate: string; initialTime?: string }
  | { mode: 'edit'; reminder: CustomerReminder };
```

```ts
function emptyForm(localDate: string, localTime?: string): CustomerReminderFormInput {
  const today = toLocalDate(new Date());
  const defaultSlot = localTime
    ? { localDate, localTime }
    : localDate <= today
      ? nextFutureTimeSlot()
      : { localDate, localTime: '09:00' };
  return {
    title: '',
    localDate: defaultSlot.localDate,
    localTime: defaultSlot.localTime,
    timezone: getDefaultTimezone(),
    repeat: 'none',
  };
}
```

In `ReminderForm`, initialize create mode with:

```ts
const form = drawer.mode === 'edit' ? formFromReminder(drawer.reminder) : emptyForm(drawer.initialDate, drawer.initialTime);
```

Change the form key so two create slots on the same day remount correctly:

```tsx
key={drawer.mode === 'edit' ? drawer.reminder.id : `${drawer.initialDate}-${drawer.initialTime ?? 'default'}`}
```

- [ ] **Step 3: Replace the old day board with the timeline render**

In `CustomerRemindersPage`, add:

```ts
const hourSlots = useMemo(() => buildHourSlots(VISIBLE_START_HOUR, VISIBLE_END_HOUR), []);
const bucketsByDate = useMemo(() => {
  const map = new Map<string, DayReminderBuckets>();
  for (const day of days) {
    const localDate = toLocalDate(day);
    map.set(localDate, buildDayBuckets(grouped.get(localDate) ?? [], VISIBLE_START_HOUR, VISIBLE_END_HOUR));
  }
  return map;
}, [days, grouped]);
```

Replace the old `.customer-reminder-week` body with:

```tsx
<div className="customer-reminder-timeline" aria-label="Selected week reminder timeline">
  <div className="customer-reminder-time-gutter" aria-hidden="true">
    <div className="customer-reminder-time-gutter__spacer" />
    {hourSlots.map((hour) => (
      <span key={hour}>{formatHour(hour)}</span>
    ))}
  </div>
  <div className="customer-reminder-days">
    {days.map((day) => {
      const localDate = toLocalDate(day);
      const dayBuckets = bucketsByDate.get(localDate) ?? buildDayBuckets([], VISIBLE_START_HOUR, VISIBLE_END_HOUR);
      const isToday = localDate === toLocalDate(new Date());
      return (
        <section key={localDate} className="customer-reminder-day" data-today={isToday ? 'true' : undefined}>
          <div className="customer-reminder-day__head">
            <strong>{day.toLocaleDateString('en-US', { weekday: 'short' })}</strong>
            <span>{day.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
          </div>
          {dayBuckets.outside.length > 0 ? (
            <div className="customer-reminder-outside" data-testid={`outside-${localDate}`}>
              <span className="customer-reminder-outside__label">Outside visible hours</span>
              {dayBuckets.outside.slice(0, MAX_OUTSIDE_HOURS_ITEMS).map((reminder) => (
                <ReminderCalendarItem key={reminder.id} reminder={reminder} onEdit={() => setDrawer({ mode: 'edit', reminder })} onAction={runAction} />
              ))}
              {dayBuckets.outside.length > MAX_OUTSIDE_HOURS_ITEMS ? (
                <p className="customer-reminder-outside__more">
                  +{dayBuckets.outside.length - MAX_OUTSIDE_HOURS_ITEMS} more outside visible hours
                </p>
              ) : null}
            </div>
          ) : null}
          <div className="customer-reminder-day__hours">
            {hourSlots.map((hour) => {
              const slotReminders = dayBuckets.byHour.get(hour) ?? [];
              return (
                <div key={hour} className="customer-reminder-hour" data-testid={`slot-${localDate}-${String(hour).padStart(2, '0')}`}>
                  <button
                    type="button"
                    className="customer-reminder-slot-button"
                    data-testid={`slot-button-${localDate}-${String(hour).padStart(2, '0')}`}
                    aria-label={`Create reminder on ${localDate} at ${formatHour(hour)}`}
                    onClick={() => setDrawer({ mode: 'create', initialDate: localDate, initialTime: formatHour(hour) })}
                  />
                  <div className="customer-reminder-hour__items">
                    {slotReminders.map((reminder) => (
                      <ReminderCalendarItem key={reminder.id} reminder={reminder} onEdit={() => setDrawer({ mode: 'edit', reminder })} onAction={runAction} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      );
    })}
  </div>
</div>
```

- [ ] **Step 4: Add `ReminderCalendarItem` component**

Add this component above `CustomerRemindersPage`:

```tsx
function ReminderCalendarItem({
  reminder,
  onEdit,
  onAction,
}: {
  reminder: CustomerReminder;
  onEdit: () => void;
  onAction: (action: 'complete' | 'cancel', reminderId: string) => void;
}) {
  const repeat = repeatFromRrule(reminder.rrule);
  const meta = repeat === 'none' ? reminder.timezone : repeat;
  return (
    <article className="customer-reminder-card">
      <button type="button" className="customer-reminder-card__open" onClick={onEdit}>
        <time>{reminder.localTime}</time>
        <h2>{reminder.title}</h2>
        <p>{meta}</p>
      </button>
      <div className="customer-reminder-card__actions">
        <button type="button" onClick={onEdit}>
          Edit
        </button>
        <button type="button" onClick={() => void onAction('complete', reminder.id)}>
          Complete
        </button>
        <button type="button" onClick={() => void onAction('cancel', reminder.id)}>
          Delete
        </button>
      </div>
    </article>
  );
}
```

- [ ] **Step 5: Add minimal timeline CSS**

In `web/app/public-site.css`, replace the old `.customer-reminder-week`/day board styles with timeline styles. Keep `.customer-reminder-card`, `.customer-reminder-card__open`, and action styles usable.

Add:

```css
.coke-site .customer-reminder-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 0 0 18px;
}

.coke-site .customer-reminder-summary span {
  min-width: 0;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(27, 20, 16, 0.08);
  background: rgba(255, 255, 255, 0.72);
  color: var(--ink-700);
  font-size: 13px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.coke-site .customer-reminder-summary strong {
  color: var(--ink-1000);
}

.coke-site .customer-reminder-timeline {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr);
  overflow-x: auto;
  padding-bottom: 4px;
}

.coke-site .customer-reminder-time-gutter {
  display: grid;
  grid-template-rows: auto repeat(17, minmax(74px, auto));
  color: var(--ink-500);
  font-size: 11px;
  font-weight: 700;
}

.coke-site .customer-reminder-time-gutter span {
  padding-top: 8px;
}

.coke-site .customer-reminder-days {
  display: grid;
  grid-template-columns: repeat(7, minmax(148px, 1fr));
  gap: 8px;
  min-width: 1036px;
}

.coke-site .customer-reminder-day[data-today='true'] .customer-reminder-day__head {
  background: rgba(126, 144, 87, 0.14);
}

.coke-site .customer-reminder-outside {
  display: grid;
  gap: 8px;
  padding: 8px;
  border-bottom: 1px solid rgba(27, 20, 16, 0.08);
}

.coke-site .customer-reminder-outside__label,
.coke-site .customer-reminder-outside__more {
  margin: 0;
  color: var(--ink-500);
  font-size: 11px;
  font-weight: 800;
}

.coke-site .customer-reminder-day__hours {
  display: grid;
  grid-template-rows: repeat(17, minmax(74px, auto));
}

.coke-site .customer-reminder-hour {
  position: relative;
  min-height: 74px;
  border-bottom: 1px solid rgba(27, 20, 16, 0.08);
  padding: 6px;
}

.coke-site .customer-reminder-slot-button {
  position: absolute;
  inset: 0;
  width: 100%;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.coke-site .customer-reminder-slot-button:focus-visible {
  outline: 2px solid var(--claw-500);
  outline-offset: -3px;
}

.coke-site .customer-reminder-hour__items {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 6px;
  pointer-events: none;
}

.coke-site .customer-reminder-hour__items .customer-reminder-card {
  pointer-events: auto;
}
```

- [ ] **Step 6: Run focused tests and commit this slice if green**

Run:

```sh
cd web && pnpm test -- app/\(customer\)/account/reminders/page.test.tsx
```

Expected: PASS for the updated title, summary, slot placement, and slot-create tests. Commit:

```sh
git add web/app/\(customer\)/account/reminders/page.tsx web/app/\(customer\)/account/reminders/page.test.tsx web/app/public-site.css
git commit -m "feat: render reminder calendar timeline"
```

## Task 3: Outside-Hours Overflow, Delete Terminology, And Lifecycle Coverage

**Files:**

- Modify: `web/app/(customer)/account/reminders/page.test.tsx`
- Modify: `web/app/(customer)/account/reminders/page.tsx`
- Modify: `web/app/public-site.css`

- [ ] **Step 1: Add failing tests for outside-hours overflow and visible Delete action**

In the test file, add:

```ts
it('limits outside-hours reminders and shows a passive overflow count', async () => {
  listMock.mockResolvedValueOnce({
    ok: true,
    data: {
      reminders: [
        makeReminder({ id: 'early-1', title: 'Early one', localDate: '2026-05-13', localTime: '01:00' }),
        makeReminder({ id: 'early-2', title: 'Early two', localDate: '2026-05-13', localTime: '02:00' }),
        makeReminder({ id: 'early-3', title: 'Early three', localDate: '2026-05-13', localTime: '03:00' }),
        makeReminder({ id: 'early-4', title: 'Early four', localDate: '2026-05-13', localTime: '04:00' }),
      ],
    },
  });

  renderPage();
  await flushTicks(3);

  const outside = container.querySelector('[data-testid="outside-2026-05-13"]') as HTMLElement | null;
  expect(outside?.textContent).toContain('Outside visible hours');
  expect(outside?.textContent).toContain('Early one');
  expect(outside?.textContent).toContain('Early three');
  expect(outside?.textContent).not.toContain('Early four');
  expect(outside?.textContent).toContain('+1 more outside visible hours');
});
```

Update action tests to assert the visible label is `Delete` and still calls `cancelCustomerReminder`:

```ts
const deleteButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Delete');
deleteButton?.click();
await flushTicks(3);
expect(cancelMock).toHaveBeenCalledWith('rem-1');
```

Also update drawer expectations:

```ts
expect(drawer?.textContent).toContain('Delete');
const drawerDeleteButton = [...(reopenedDrawer?.querySelectorAll('button') ?? [])].find(
  (button) => button.textContent === 'Delete',
);
drawerDeleteButton?.click();
await flushTicks(3);
expect(cancelMock).toHaveBeenCalledWith('rem-1');
```

- [ ] **Step 2: Run focused tests and verify failures**

Run:

```sh
cd web && pnpm test -- app/\(customer\)/account/reminders/page.test.tsx
```

Expected: FAIL if any visible `Cancel` label remains or outside-hours overflow is not implemented correctly.

- [ ] **Step 3: Change visible personal reminder cancellation labels to Delete**

In `ReminderForm`, change the edit drawer cancel button text from `Cancel` to `Delete` while keeping the action value:

```tsx
<button
  type="button"
  className="customer-action customer-action--secondary"
  onClick={() => onAction('cancel', drawer.reminder.id)}
>
  Delete
</button>
```

In `runAction`, keep the action key as `cancel` but make user-visible errors say delete:

```ts
const actionLabel = action === 'cancel' ? 'delete' : action;
```

Use `actionLabel` in both error paths:

```ts
setError(`Unable to ${actionLabel} this reminder right now.`);
```

- [ ] **Step 4: Verify overflow and card action parity**

Confirm the `dayBuckets.outside.slice(0, MAX_OUTSIDE_HOURS_ITEMS)` render path uses `ReminderCalendarItem`, and confirm the overflow count expression is:

```tsx
{dayBuckets.outside.length > MAX_OUTSIDE_HOURS_ITEMS ? (
  <p className="customer-reminder-outside__more">
    +{dayBuckets.outside.length - MAX_OUTSIDE_HOURS_ITEMS} more outside visible hours
  </p>
) : null}
```

- [ ] **Step 5: Run focused tests and commit**

Run:

```sh
cd web && pnpm test -- app/\(customer\)/account/reminders/page.test.tsx
```

Expected: PASS. Commit:

```sh
git add web/app/\(customer\)/account/reminders/page.tsx web/app/\(customer\)/account/reminders/page.test.tsx web/app/public-site.css
git commit -m "fix: align reminder calendar delete actions"
```

## Task 4: Responsive Polish And Full Verification

**Files:**

- Modify: `web/app/public-site.css`
- Modify: `web/app/(customer)/account/reminders/page.test.tsx` only if a failing assertion exposes a real accessibility or layout state gap

- [ ] **Step 1: Add responsive CSS for summary and timeline controls**

In `web/app/public-site.css`, add:

```css
@media (max-width: 760px) {
  .coke-site .customer-reminder-board__head,
  .coke-site .customer-reminder-weekbar {
    align-items: stretch;
    flex-direction: column;
  }

  .coke-site .customer-reminder-summary {
    grid-template-columns: 1fr;
  }

  .coke-site .customer-reminder-timeline {
    grid-template-columns: 46px minmax(0, 1fr);
  }

  .coke-site .customer-reminder-days {
    grid-template-columns: repeat(7, minmax(136px, 1fr));
    min-width: 952px;
  }

  .coke-site .customer-reminder-card__actions button {
    padding: 6px 8px;
  }
}
```

- [ ] **Step 2: Run focused page tests**

Run:

```sh
cd web && pnpm test -- app/\(customer\)/account/reminders/page.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run web build**

Run:

```sh
cd web && pnpm build
```

Expected: PASS with a successful Next build.

- [ ] **Step 4: Run diff-aware verification routing**

Run:

```sh
zsh scripts/suggest-verification --base HEAD
zsh scripts/review-trigger --base HEAD
```

Expected: routes include the changed web surface and any repo-OS docs surface if the plan file is still in the current diff. Run any suggested `zsh scripts/verify-surface ...` command that applies to the current diff.

- [ ] **Step 5: Commit verification/polish changes**

Commit only files owned by this plan:

```sh
git add web/app/public-site.css web/app/\(customer\)/account/reminders/page.test.tsx
git commit -m "style: polish reminder calendar timeline"
```

If Step 1 produced no diff because earlier tasks already covered the responsive rules, skip this commit and record that in the handoff.

## Final Review

After all implementation tasks are committed:

- Run a final code review subagent over the implementation commit range.
- Fix any Critical or Important findings.
- Re-run:

```sh
cd web && pnpm test -- app/\(customer\)/account/reminders/page.test.tsx
cd web && pnpm build
zsh scripts/suggest-verification --base HEAD
zsh scripts/review-trigger --base HEAD
```

- Report final commit SHAs, verification commands, and any verification gaps.

# Coke Public Homepage — Warm Editorial Redesign (Implementation Plan)

**Spec:** `docs/superpowers/specs/2026-04-21-coke-public-homepage-warm-redesign-design.md`
**Reference bundle:** `/tmp/design_bundle/coke-ai-design-system/project/ui_kits/public_site/`
**Scoped stylesheet (already authored, do not re-author):** `gateway/packages/web/app/public-site.css`
**Working dir for all edits:** `gateway/packages/web/`

## Ground Rules

- **Do not touch `app/globals.css`**. Admin + customer shells depend on its Tailwind tokens.
- **Do not touch `app/(admin)`, `app/(customer)`, `app/(coke-user)` routes**.
- All new visual styling must live inside the `.coke-site` scope in `app/public-site.css` (already in place — only the splash block is added by this plan).
- Use `lucide-react` React components for icons (not `data-lucide` HTML attributes).
- **The `gateway/` directory is a git submodule.** All code edits must be committed inside the submodule, then the outer repo pointer must be bumped in a second commit. Follow the existing pattern used by prior plans (e.g. `2026-04-20-whatsapp-public-checkout.md`).
- Next.js 16 + React 19. Follow `node_modules/next/dist/docs/` guidance — specifically do not re-introduce `pages/` patterns. `app/` router only. Client components keep `'use client'`.
- All user-visible strings come from `lib/i18n.ts` except the decorative `ChatPeek` thread lines (small bilingual table kept local to the component, explicitly documented in the spec).
- No `README.md` edits, no new docs, no scaffolding files.

## Verification Commands (run after each milestone)

```bash
cd gateway/packages/web
npx vitest run components/coke-public-shell.test.tsx
npx vitest run components/coke-homepage.test.tsx
npx vitest run app/layout.metadata.test.ts app/page.test.tsx app/dashboard-removal.test.ts
npx next lint
npx next build
```

Use `pnpm` equivalents if the workspace is pnpm-driven (check `pnpm-lock.yaml` in the monorepo root). If neither is configured locally, call `node_modules/.bin/vitest` / `node_modules/.bin/next` directly.

## Step 1 — Extend i18n with new homepage keys

**File:** `gateway/packages/web/lib/i18n.ts`

1. Extend the `LocaleMessages['homepage']` type:
   - `hero.titleLine1: string`
   - `hero.titleItalicMiddle: string`
   - `hero.titleLine3: string`
   - `hero.foot: string`
   - `contact.placeholder: string`
   - `contact.note: string`
   - `contact.thanks: string`
   - `footer: { productHeading: string; accountHeading: string; companyHeading: string; copyright: string; tagline: string; productLinks: string[]; accountLinks: string[]; companyLinks: string[] }`
2. Populate `en`:
   - `titleLine1: 'An AI partner'`
   - `titleItalicMiddle: 'that grows'`
   - `titleLine3: 'with you.'`
   - `foot: 'Six platforms · 99.9% uptime · <100ms latency'`
   - `placeholder: 'your email'`
   - `note: "We won't share your email with anyone else."`
   - `thanks: "Thanks. We'll be in touch within 24 hours."`
   - `footer.productHeading: 'Product'`, `accountHeading: 'Account'`, `companyHeading: 'Company'`, `copyright: '© 2026 Coke AI'`, `tagline: 'Built to grow with you.'`
   - `productLinks: ['Platforms', 'Features', 'Architecture']`
   - `accountLinks: ['Sign in', 'Register', 'Renew']`
   - `companyLinks: ['About', 'Contact', 'Privacy']`
3. Populate `zh`:
   - `titleLine1: '会随着使用'`
   - `titleItalicMiddle: '不断进化的'`
   - `titleLine3: 'AI 助手。'`
   - `foot: '六个平台 · 99.9% 可用性 · <100ms 响应'`
   - `placeholder: '你的邮箱'`
   - `note: '我们不会把你的邮箱分享给第三方。'`
   - `thanks: '谢谢。我们会在 24 小时内联系你。'`
   - `footer.productHeading: '产品'`, `accountHeading: '账号'`, `companyHeading: '公司'`, `copyright: '© 2026 Coke AI'`, `tagline: '与你一起慢慢变好。'`
   - `productLinks: ['平台', '功能', '架构']`
   - `accountLinks: ['登录', '注册', '续费']`
   - `companyLinks: ['关于', '联系', '隐私']`
4. Do **not** remove `homepage.stats` or `homepage.spotlight` keys — they're unused by the new layout but kept for future variants. Leaving them avoids bigger diffs in consumers.
5. Run `npx vitest run lib/i18n.test.ts`. Fix any shape drift caught by `i18n.test.ts`.

Do not skip: if `i18n.test.ts` asserts key parity between `en` and `zh`, both locales must stay shape-compatible.

## Step 2 — Wire `next/font` + replace splash in `app/layout.tsx`

**File:** `gateway/packages/web/app/layout.tsx`

1. Import fonts:
   ```ts
   import { Fraunces, Inter, JetBrains_Mono } from 'next/font/google';
   const fraunces = Fraunces({
     subsets: ['latin'],
     variable: '--font-fraunces',
     axes: ['SOFT', 'opsz'],
     display: 'swap',
   });
   const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' });
   const jetbrainsMono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono', display: 'swap' });
   ```
2. Apply the font variables to `<body>`:
   ```tsx
   <body className={`${fraunces.variable} ${inter.variable} ${jetbrainsMono.variable}`}>
   ```
3. Import `./public-site.css` after `./globals.css`.
4. Replace the current `<div id="locale-splash" className="flex min-h-screen …">` block with:
   ```tsx
   <div id="locale-splash" className="coke-site-splash">
     <div className="coke-site-splash__card">
       <span className="coke-site-splash__mark">coke</span>
       <span className="coke-site-splash__dot" aria-hidden="true" />
       <p className="coke-site-splash__body">Preparing your workspace…</p>
     </div>
   </div>
   ```
   The `LocaleProvider` effect still removes `#locale-splash` on mount.
5. Keep `<Script id="locale-bootstrap" strategy="beforeInteractive" …>` unchanged.
6. `metadata` stays unchanged.

Run `npx vitest run app/layout.metadata.test.ts`. Verify metadata stays identical.

## Step 3 — Append splash styles to `public-site.css`

**File:** `gateway/packages/web/app/public-site.css`

Append to the bottom of the file (new block, still in the same file):

```css
/* ---------------- Locale splash (pre-mount, outside .coke-site scope) ---------------- */
.coke-site-splash {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(ellipse 900px 420px at 20% -12%, rgba(232, 105, 60, 0.12), transparent 60%),
    radial-gradient(ellipse 700px 360px at 92% -6%, rgba(63, 123, 117, 0.08), transparent 60%),
    #F6F1E8;
  z-index: 100;
  font-family: var(--font-inter, 'Inter', system-ui, sans-serif);
}
.coke-site-splash__card {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(27, 20, 16, 0.08);
  box-shadow: 0 8px 24px -8px rgba(27, 20, 16, 0.12);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.coke-site-splash__mark {
  font-family: var(--font-fraunces, 'Fraunces', Georgia, serif);
  font-style: italic;
  font-weight: 600;
  font-size: 22px;
  letter-spacing: -0.03em;
  color: #1B1410;
}
.coke-site-splash__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #E8693C;
  transform: translateY(-4px);
}
.coke-site-splash__body {
  margin: 0 0 0 4px;
  font-size: 13px;
  color: #7A6B62;
}
```

Do not change existing selectors above.

## Step 4 — Rewrite `CokePublicShell`

**File:** `gateway/packages/web/components/coke-public-shell.tsx`

1. Delete the current Tailwind-based markup inside `return (...)`.
2. New structure:
   ```tsx
   return (
     <div className="coke-site">
       <header className="site-header">
         <div className="site-header__inner">
           <Link href="/" className="brand" aria-label="Coke AI">
             <span className="brand__mark">coke</span>
             <span className="brand__dot" aria-hidden="true" />
           </Link>
           <nav className="site-nav">
             {messages.publicShell.nav.map((item) => (
               <Link key={item.href} href={item.href} className="site-nav__link">
                 {item.label}
               </Link>
             ))}
           </nav>
           <div className="site-header__actions">
             <LocaleSwitch />
             <Link href="/auth/login" className="header-signin">
               {messages.publicShell.cta.signIn}
             </Link>
             <Link href="/auth/register" className="header-cta">
               {messages.publicShell.cta.register}
               <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
             </Link>
           </div>
         </div>
       </header>
       <main>{children}</main>
     </div>
   );
   ```
3. Import `ArrowRight` from `lucide-react`.
4. Drop `CokePublicShellProps['contentClassName']` and `className`? — keep both props in the signature (other callers may pass them; forward `className` onto the root `.coke-site` via `cn('coke-site', className)` and forward `contentClassName` onto `<main>`). This preserves the current API surface.
5. The footer is **not** rendered by the shell anymore. The homepage renders its own `<Footer />`. Document this with a top-of-file comment? **No** — inferrable from the code.

## Step 5 — Rewrite `coke-homepage.tsx`

**File:** `gateway/packages/web/components/coke-homepage.tsx`

Replace the entire file. Keep it a single-file module to match the existing layout. Structure:

```tsx
'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Bird,
  Briefcase,
  CalendarCheck,
  Check,
  CheckCheck,
  Gamepad2,
  Hash,
  MessageCircle,
  Route,
  Send,
  Sparkles,
  Workflow as WorkflowIcon,
} from 'lucide-react';

import { CokePublicShell } from './coke-public-shell';
import { useLocale } from './locale-provider';

export function CokeHomepage() {
  const { locale, messages } = useLocale();
  return (
    <CokePublicShell>
      <Hero locale={locale} />
      <Platforms />
      <Features />
      <Architecture />
      <Contact />
      <Footer />
    </CokePublicShell>
  );
}
```

Then define these components in the same file (lightweight, each pulls copy from `messages = useLocale().messages.homepage`):

- `Hero({ locale })` — `.hero` + `.hero__grid`.
  - Left: `.hero__eyebrow` with `.hero__eyebrow-dot`, `.hero__title` with italic `<em className="hero__title-em">{titleItalicMiddle}</em>` between two plain `<span>` lines separated by `<br />`, `.hero__lede`, `.hero__ctas` with two buttons (`.btn.btn--primary` → `/auth/register`, `.btn.btn--link` → `/auth/login`), `.hero__foot`.
  - Right: `<ChatPeek locale={locale} />`.
- `ChatPeek({ locale })` — static bilingual thread (local, as spec allows). Matches `/tmp/design_bundle/coke-ai-design-system/project/ui_kits/public_site/Hero.jsx` lines 1–63 but renders `<MessageCircle />` and `<CheckCheck />` in place of the `<i data-lucide>` tags.
- `Platforms()` — `.section` with `.section__head`, `.platforms` grid. Platforms array local:
  ```ts
  const PLATFORMS = [
    { name: 'WeChat',   Icon: MessageCircle, noteEn: 'Personal · QR login', noteZh: '个人号 · 扫码上线' },
    { name: 'Telegram', Icon: Send,          noteEn: 'Bot token',           noteZh: 'Bot token' },
    { name: 'DingTalk', Icon: Briefcase,     noteEn: 'Enterprise',          noteZh: '企业协作' },
    { name: 'Lark',     Icon: Bird,          noteEn: 'Group bot',           noteZh: '飞书 · 群机器人' },
    { name: 'Slack',    Icon: Hash,          noteEn: 'Socket Mode',         noteZh: 'Socket Mode' },
    { name: 'Discord',  Icon: Gamepad2,      noteEn: 'Community',           noteZh: '社区' },
  ] as const;
  ```
  Each `.platform` ends with `<ArrowUpRight className="platform__arrow" />`. Section eyebrow `01 · {messages.platforms.eyebrow}`.
- `Features()` — `.section#features` with 2-col `.features` grid. Use 4-entry array derived from `messages.homepage.features.items` (existing shape provides `title`, `subtitle`, `body`). Use `messages.homepage.features.items[i].subtitle` as the `.feature__kicker` and `.items[i].title` as the `.feature__title`. Icon sequence: `CalendarCheck`, `Route`, `Activity`, `WorkflowIcon`. Section eyebrow `02`.
- `Architecture()` — `.section#architecture.section--invert` with `.arch` two-column grid. Use `messages.homepage.architecture`: render the `.points` list as `.arch__point` items numbered `01..04`. The diagram chips are static (`WeChat`, `Telegram`, `Slack` top; `Coke gateway` middle; `openCoke`, `GPT`, `Claude`, `CLI bridge` bottom). Eyebrow `03` with `section__eyebrow--invert`.
- `Contact()` — `.section.section--flush` with `.contact` + `.contact__mark` watermark.
  - Controlled `useState('')` for email.
  - `useState(false)` for `submitted`.
  - On submit: `preventDefault`, trim, set submitted=true. No network call.
  - Show `<Check />` inside `.contact__thanks` when submitted.
  - Primary button `.btn.btn--primary.btn--lg` with `<ArrowRight />`; secondary `.contact__alt` → `/auth/login`.
  - Eyebrow `04 · {messages.homepage.contact.eyebrow}`.
- `Footer()` — `.site-footer` reproducing the reference Footer.jsx (`Contact.jsx` lines 87–123). Columns come from `messages.homepage.footer.productLinks` / `accountLinks` / `companyLinks`. Bottom bar shows `messages.homepage.footer.copyright` and `.tagline`.

Exports: `export function CokeHomepage()` (same named export as before so `app/page.tsx` continues to work without change).

## Step 6 — Restyle `LocaleSwitch`

**File:** `gateway/packages/web/components/locale-switch.tsx`

Replace the current toggle with the new pill pattern:

```tsx
'use client';
import { useLocale } from './locale-provider';

export function LocaleSwitch() {
  const { locale, setLocale, messages } = useLocale();
  return (
    <div
      className="locale-switch"
      role="group"
      aria-label={messages.publicShell.languageSwitchLabel}
    >
      <button
        type="button"
        className="locale-switch__opt"
        aria-pressed={locale === 'en'}
        onClick={() => setLocale('en')}
      >
        EN
      </button>
      <button
        type="button"
        className="locale-switch__opt"
        aria-pressed={locale === 'zh'}
        onClick={() => setLocale('zh')}
      >
        中
      </button>
    </div>
  );
}
```

If the existing component exports differently, preserve the export name (`LocaleSwitch`). If there was a locale label longer than `中` (e.g. `中文`), the test must be updated to match the new `中` label; do so in Step 7.

Check `public-site.css` to ensure `.locale-switch` and `.locale-switch__opt` rules exist. If the current version of `public-site.css` only includes one `.locale-switch` variant, append rules inside the `.coke-site .locale-switch` scope to cover both buttons using `aria-pressed="true"` as shown in `/tmp/design_bundle/coke-ai-design-system/project/ui_kits/public_site/styles.css` around the header section.

## Step 7 — Rewrite `coke-public-shell.test.tsx`

**File:** `gateway/packages/web/components/coke-public-shell.test.tsx`

Replace the class-name assertions with a minimal contract that survives warm redesign:

- `container.querySelector('.coke-site')` is truthy.
- `container.querySelector('a[href="/auth/login"]')` and `a[href="/auth/register"]` both truthy.
- English render contains `Platforms`, `Features`, `Architecture`, `Contact`, `Sign in`, `Register`, brand mark `coke` (lowercased, text content check: `container.textContent?.toLowerCase()` contains `coke`).
- Chinese render contains `平台`, `功能`, `架构`, `联系`, `登录`, `注册`.
- Both renders show `EN` and `中`.
- Neither render contains `Register / 注册` nor `Platforms / 平台` (preserves existing mixed-label guard).
- Drop assertions for `An AI Partner That Grows With You` / `与您共同成长的 AI 助手` (tagline no longer in shell).

Keep the `vi.mock('next/link', …)` stub, `LocaleProvider` wrapper, and `flushSync` usage unchanged.

## Step 8 — Add `coke-homepage.test.tsx`

**File (new):** `gateway/packages/web/components/coke-homepage.test.tsx`

Minimal smoke test:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import type { ReactNode } from 'react';

import { LocaleProvider } from './locale-provider';

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

import { CokeHomepage } from './coke-homepage';

describe('CokeHomepage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('renders all editorial sections in English', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="en">
          <CokeHomepage />
        </LocaleProvider>,
      );
    });
    expect(container.querySelector('.coke-site')).toBeTruthy();
    expect(container.querySelector('#platforms')).toBeTruthy();
    expect(container.querySelector('#features')).toBeTruthy();
    expect(container.querySelector('#architecture')).toBeTruthy();
    expect(container.querySelector('#contact')).toBeTruthy();
    expect(container.querySelector('.hero__title em')).toBeTruthy();
    expect(container.textContent).toContain('WeChat');
    expect(container.textContent).toContain('Telegram');
  });

  it('renders Chinese hero copy', () => {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale="zh">
          <CokeHomepage />
        </LocaleProvider>,
      );
    });
    expect(container.textContent).toContain('AI 助手');
    expect(container.textContent).toContain('不断进化的');
  });
});
```

## Step 9 — Verification Gate

Inside `gateway/packages/web`:

```bash
node_modules/.bin/vitest run components/coke-public-shell.test.tsx components/coke-homepage.test.tsx lib/i18n.test.ts app/layout.metadata.test.ts app/page.test.tsx app/dashboard-removal.test.ts
node_modules/.bin/next lint
node_modules/.bin/next build
```

All three must pass. If `next build` fails because `next/font` refuses an axis, drop `axes: ['SOFT', 'opsz']` from the `Fraunces` call. The CSS keeps its `font-variation-settings` declarations; they're ignored if the shipped axis is missing.

## Step 10 — Commit inside submodule, then bump pointer

1. Inside `gateway/`:
   ```bash
   git status
   git add packages/web/app/layout.tsx packages/web/app/public-site.css \
           packages/web/components/coke-public-shell.tsx \
           packages/web/components/coke-homepage.tsx \
           packages/web/components/coke-homepage.test.tsx \
           packages/web/components/coke-public-shell.test.tsx \
           packages/web/components/locale-switch.tsx \
           packages/web/lib/i18n.ts
   git commit -m "feat(web): warm editorial redesign of public homepage"
   ```
2. In the outer repo (`/data/projects/coke`):
   ```bash
   git add gateway
   git commit -m "chore(gateway): refresh public homepage warm redesign"
   ```
3. Do not push. Do not amend. Do not force-push.

## Self-Check Before Reporting Done

The handoff back to the dispatcher **must** include:

- Git SHA inside the gateway submodule.
- Git SHA in the outer repo.
- Exit statuses of `vitest`, `next lint`, `next build` (trimmed stdout tails OK, but must include the PASS/FAIL line).
- Confirmation that `app/globals.css` is byte-identical to before the change: `git diff HEAD~1 -- packages/web/app/globals.css` returns empty.
- Confirmation that no file under `app/(admin)`, `app/(customer)`, `app/(coke-user)` was modified: `git diff --name-only HEAD~1 -- 'packages/web/app/(admin)' 'packages/web/app/(customer)' 'packages/web/app/(coke-user)'` returns empty.

If any of these five checks fails, report the failure and stop — do not report success.

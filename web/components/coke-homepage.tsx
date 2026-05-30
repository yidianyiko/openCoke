'use client';

import Link from 'next/link';
import { useState, type CSSProperties, type FormEvent } from 'react';
import {
  Activity,
  ArrowRight,
  CalendarCheck,
  Check,
  CheckCheck,
  MessageCircle,
  Route,
  Smartphone,
  Workflow as WorkflowIcon,
} from 'lucide-react';

import { KapKoalaBadge, KapKoalaHero } from './kap-brand';
import { type Locale } from '../lib/i18n';
import { CokePublicShell } from './coke-public-shell';
import { useLocale } from './locale-provider';

const visuallyHiddenStyle: CSSProperties = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  border: 0,
};

const HERO_DECOR = {
  en: {
    availability: 'Live now · Personal WeChat · WhatsApp · Google Calendar',
    stickerLeft: 'Set the goal once.',
    stickerRight: 'Kap follows up.',
    chipA: 'Reminder set',
    chipB: 'Follow-up active',
  },
  zh: {
    availability: '已上线 · 个人微信 · WhatsApp · Google Calendar',
    stickerLeft: '先把目标说清楚。',
    stickerRight: 'Kap 会继续跟进。',
    chipA: '提醒已创建',
    chipB: '跟进已启用',
  },
} satisfies Record<
  Locale,
  {
    availability: string;
    stickerLeft: string;
    stickerRight: string;
    chipA: string;
    chipB: string;
  }
>;

const HERO_STAGE_COPY = {
  en: {
    label: 'Kap AI',
    body: 'One supervision thread for reminders, check-ins, and follow-up.',
  },
  zh: {
    label: 'Kap AI',
    body: '用一个监督线程，把提醒、检查和跟进接起来。',
  },
} satisfies Record<Locale, { label: string; body: string }>;

const TICKER_ITEMS = {
  en: [
    'Turn goals into reminders',
    'Personal WeChat setup is live',
    'Google Calendar imports become reminders',
    'WhatsApp global entry is live',
  ],
  zh: ['把目标变成提醒', '个人微信设置已上线', 'Google Calendar 可导入成提醒', 'WhatsApp 全球入口已上线'],
} satisfies Record<Locale, readonly string[]>;

const CAPABILITY_CARDS = {
  en: [
    {
      tone: 'c1',
      eyebrow: 'Supervise',
      title: 'Turn goals into reminders, check-ins, and follow-up.',
      body: 'Kap is built around supervision: clarify the goal, set the timing, and keep the next action visible after the first message.',
    },
    {
      tone: 'c2',
      eyebrow: 'Remind',
      title: 'Create and manage visible reminders in chat.',
      body: 'Set, list, update, complete, or delete reminders without leaving the conversation. The runtime schedules them as durable deferred actions.',
    },
    {
      tone: 'c3',
      eyebrow: 'Calendar',
      title: 'Import Google Calendar into Kap reminders.',
      body: 'Connect Google Calendar from the account page and turn scheduled events into reminders attached to the active Kap conversation.',
    },
    {
      tone: 'c4',
      eyebrow: 'Connect',
      title: 'Continue through personal WeChat or WhatsApp.',
      body: 'Domestic users can manage a personal WeChat channel. Global users can start from the focused WhatsApp entry.',
    },
    {
      tone: 'c5',
      eyebrow: 'Access',
      title: 'Keep account access, renewal, and reconnect steps visible.',
      body: 'Email verification, subscription renewal, channel reconnect, and suspended access states are handled in the customer pages.',
    },
  ],
  zh: [
    {
      tone: 'c1',
      eyebrow: '监督',
      title: '把目标变成提醒、检查和后续跟进。',
      body: 'Kap 的核心是监督：先确认目标和时间，再把下一步持续留在对话里，而不是只回答一次。',
    },
    {
      tone: 'c2',
      eyebrow: '提醒',
      title: '在聊天里创建和管理可见提醒。',
      body: '用户可以直接设置、查看、更新、完成或删除提醒；底层会把它们作为持久的延迟动作调度。',
    },
    {
      tone: 'c3',
      eyebrow: '日历',
      title: '把 Google Calendar 导入成 Kap 提醒。',
      body: '从账号页授权 Google Calendar，把日程事件转成当前 Kap 对话里的提醒。',
    },
    {
      tone: 'c4',
      eyebrow: '连接',
      title: '通过个人微信或 WhatsApp 继续使用。',
      body: '国内用户可以管理个人微信通道；海外用户可以从专门的 WhatsApp 入口直接开始。',
    },
    {
      tone: 'c5',
      eyebrow: '访问',
      title: '账号访问、续费和重连步骤保持可见。',
      body: '邮箱验证、订阅续费、通道重连和账号停用状态都已经放进客户页面里处理。',
    },
  ],
} satisfies Record<
  Locale,
  ReadonlyArray<{ tone: 'c1' | 'c2' | 'c3' | 'c4' | 'c5'; eyebrow: string; title: string; body: string }>
>;

const SCENARIOS = {
  en: [
    {
      tag: 'Supervision',
      title: 'Tell Kap what you need to finish today.',
      body: 'Kap asks for timing, turns the goal into a reminder, and keeps checking whether the task actually moved.',
      previewClass: 'o',
      preview: [
        { type: 'me', text: 'I need to finish one IELTS practice set this afternoon.' },
        { type: 'ai', text: 'What time should it be done? I can remind you before you start and check after.' },
        { type: 'file', text: 'visible-reminder', meta: 'Created, scheduled, and ready to follow up' },
      ],
    },
    {
      tag: 'Calendar',
      title: 'Bring Google Calendar into the supervision loop.',
      body: 'If your tasks already live on the calendar, import them once and let Kap convert future events into reminders.',
      previewClass: 'g',
      preview: [
        { type: 'me', text: 'Can I import my Google Calendar?' },
        { type: 'ai', text: 'Open the import page, authorize Google, and I will attach events to this Kap conversation.' },
        { type: 'file', text: 'calendar-import', meta: 'Google events become Kap reminders' },
      ],
    },
    {
      tag: 'WeChat',
      title: 'Connect or recover your personal WeChat channel.',
      body: 'Kap keeps the channel state readable: create, connect, disconnect, archive, renew access, or scan again.',
      previewClass: 'b',
      preview: [
        { type: 'me', text: 'What do I need before I reconnect my WeChat?' },
        { type: 'ai', text: 'Check verification, renew access if needed, then scan to reconnect.' },
        { type: 'file', text: 'wechat-status', meta: 'Connection state, verification, and reconnect action' },
      ],
    },
    {
      tag: 'WhatsApp',
      title: 'Start globally with one WhatsApp message.',
      body: 'The global page has one job: open the WhatsApp thread fast so the next action can keep moving there.',
      previewClass: '',
      preview: [
        { type: 'me', text: 'I want to start from WhatsApp only.' },
        { type: 'ai', text: 'Open the chat, send the task once, and keep the next steps in the same thread.' },
        { type: 'file', text: 'whatsapp-entry', meta: 'Direct chat start and the next action' },
      ],
    },
  ],
  zh: [
    {
      tag: '监督',
      title: '告诉 Kap 今天必须完成什么。',
      body: 'Kap 会追问完成时间，把目标变成提醒，并在之后检查这件事有没有真的推进。',
      previewClass: 'o',
      preview: [
        { type: 'me', text: '我今天下午要做完一套雅思练习。' },
        { type: 'ai', text: '你打算几点完成？我可以开始前提醒你，结束后再来检查。' },
        { type: 'file', text: '可见提醒', meta: '已创建、已调度、会继续跟进' },
      ],
    },
    {
      tag: '日历',
      title: '把 Google Calendar 接进监督流程。',
      body: '如果任务已经在日历里，导入一次后，Kap 会把未来日程转成提醒。',
      previewClass: 'g',
      preview: [
        { type: 'me', text: '我可以导入 Google Calendar 吗？' },
        { type: 'ai', text: '打开导入页，授权 Google 后，我会把事件接到这个 Kap 对话里。' },
        { type: 'file', text: '日历导入', meta: 'Google 事件会变成 Kap 提醒' },
      ],
    },
    {
      tag: '微信',
      title: '连接或恢复你的个人微信通道。',
      body: 'Kap 会把通道状态说清楚：创建、连接、断开、归档、续费访问或重新扫码。',
      previewClass: 'b',
      preview: [
        { type: 'me', text: '重新连微信之前，我还差哪一步？' },
        { type: 'ai', text: '先检查验证状态，需要的话先续费，然后回来扫码重连。' },
        { type: 'file', text: '微信状态', meta: '连接状态、验证状态与重连动作' },
      ],
    },
    {
      tag: 'WhatsApp',
      title: '从一条 WhatsApp 消息开始全球入口。',
      body: '全球页只做一件事：快速打开 WhatsApp 线程，让下一步继续在那里推进。',
      previewClass: '',
      preview: [
        { type: 'me', text: '我就想从 WhatsApp 直接开始。' },
        { type: 'ai', text: '打开聊天，把任务先发出去，后面的下一步都留在同一个线程里。' },
        { type: 'file', text: 'WhatsApp 入口', meta: '直接开聊与后续动作' },
      ],
    },
  ],
} satisfies Record<
  Locale,
  ReadonlyArray<{
    tag: string;
    title: string;
    body: string;
    previewClass: string;
    preview: ReadonlyArray<{ type: 'me' | 'ai' | 'file'; text: string; meta?: string }>;
  }>
>;

const QUOTE_BAND = {
  en: {
    quote: 'Kap is not another place to chat.',
    accent: 'It is the thread that keeps the promise visible.',
    cite: 'Kap',
  },
  zh: {
    quote: 'Kap 不是另一个聊天入口。',
    accent: '它是一条把承诺继续摆在眼前的监督线程。',
    cite: 'Kap',
  },
} satisfies Record<Locale, { quote: string; accent: string; cite: string }>;

const VOICES = {
  en: [
    {
      avatar: 'RM',
      role: 'Reminder runtime',
      quote: 'Visible reminders can be created, listed, updated, completed, and deleted from the conversation.',
    },
    {
      avatar: 'WX',
      role: 'Personal WeChat',
      quote: 'Users can create, connect, disconnect, archive, and recover their personal WeChat channel.',
    },
    {
      avatar: 'GC',
      role: 'Google Calendar',
      quote: 'Calendar import turns future events into Kap-owned reminders in the active conversation.',
    },
  ],
  zh: [
    {
      avatar: '提',
      role: '提醒运行时',
      quote: '用户可以在对话里创建、查看、更新、完成和删除可见提醒。',
    },
    {
      avatar: '微',
      role: '个人微信',
      quote: '用户可以创建、连接、断开、归档和恢复自己的个人微信通道。',
    },
    {
      avatar: '历',
      role: 'Google Calendar',
      quote: '日历导入会把未来事件变成当前 Kap 对话里的提醒。',
    },
  ],
} satisfies Record<Locale, ReadonlyArray<{ avatar: string; role: string; quote: string }>>;

const DEMO_PREVIEWS = {
  en: [
    {
      tag: 'Study',
      title: 'Finish one IELTS practice set',
      body: 'Kap asks for timing, creates a reminder, and checks whether the study block actually happened.',
    },
    {
      tag: 'Life admin',
      title: 'Pay the credit card bill',
      body: 'A small errand becomes visible before the deadline, with the next action kept in the same thread.',
    },
    {
      tag: 'Calendar',
      title: 'Turn Google Calendar events into reminders',
      body: 'Calendar events can become Kap-owned reminders attached to the active conversation.',
    },
  ],
  zh: [
    {
      tag: '学习',
      title: '做完一套雅思练习',
      body: 'Kap 会追问时间，创建提醒，并在结束后检查学习块有没有真的完成。',
    },
    {
      tag: '生活事项',
      title: '还信用卡账单',
      body: '小事项会在截止前被放到眼前，后续动作留在同一个对话线程里。',
    },
    {
      tag: '日历',
      title: '把 Google Calendar 事件变成提醒',
      body: '日历事件可以转成 Kap 拥有的提醒，并接到当前对话里。',
    },
  ],
} satisfies Record<Locale, ReadonlyArray<{ tag: string; title: string; body: string }>>;

const FOOTER_LINKS = {
  product: ['/#capabilities', '/#scenarios', '/demos', '/faqs'],
  account: ['/auth/login', '/auth/register', '/channels/wechat-personal', '/account/subscription'],
  company: ['/', '/terms', '/privacy'],
} as const;

export function CokeHomepage() {
  const { locale } = useLocale();

  return (
    <CokePublicShell>
      <Hero locale={locale} />
      <Ticker locale={locale} />
      <Capabilities locale={locale} />
      <Scenarios locale={locale} />
      <DemoPreview locale={locale} />
      <StartPath locale={locale} />
      <QuoteBand locale={locale} />
      <Voices locale={locale} />
      <DownloadPanel locale={locale} />
      <Footer />
    </CokePublicShell>
  );
}

function Hero({ locale }: { locale: Locale }) {
  const {
    messages: {
      homepage: { hero, stats },
    },
  } = useLocale();
  const decor = HERO_DECOR[locale];
  const stageCopy = HERO_STAGE_COPY[locale];

  return (
    <section className="hero">
      <div className="wrap">
        <div className="hero-grid">
          <div className="hero-copy">
            <span className="hero-tag">
              <span className="dot" />
              {decor.availability}
            </span>

            <h1 className="hero__title">
              <span className="line">{hero.titleLine1}</span>
              <span className="line">
                <em>{hero.titleItalicMiddle}</em>
              </span>
              <span className="line">{hero.titleLine3}</span>
            </h1>
            <p style={visuallyHiddenStyle}>{hero.subtitle}</p>

            <p className="hero-lead">{hero.body}</p>

            <div className="hero-cta-group">
              <Link href="/auth/register" className="btn-sticker">
                {hero.primaryCta}
                <ArrowRight size={15} aria-hidden="true" />
              </Link>
              <Link href="/auth/login" className="btn-ghost">
                {hero.secondaryCta}
              </Link>
            </div>

            <div className="hero-stats">
              {stats.slice(0, 3).map((stat) => (
                <div key={stat.label} className="stat">
                  <strong>{stat.value}</strong>
                  <span>{stat.label}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="hero-stage" aria-hidden="true">
            <div className="chip a">
              <span className="ic">✓</span>
              {decor.chipA}
            </div>
            <div className="chip b">
              <span className="ic alt">~</span>
              {decor.chipB}
            </div>

            <div className="hero-card">
              <div className="hero-sky" />
              <div className="hero-ground" />
              <div className="sun" />
              <div className="cloud c1" />
              <div className="cloud c2" />
              <div className="tag-speech">{decor.stickerLeft}</div>
              <div className="tag-speech r">{decor.stickerRight}</div>

              <div className="hero-mascot-figure">
                <KapKoalaHero />
              </div>

              <div className="hero-stage-card">
                <div className="hero-stage-card__top">
                  <MessageCircle size={15} aria-hidden="true" />
                  <div>
                    <strong>{stageCopy.label}</strong>
                    <p>{stageCopy.body}</p>
                  </div>
                </div>
                <div className="hero-stage-card__thread">
                  <div className="bubble bubble--user">
                    {locale === 'zh' ? '下午提醒我开始，并检查我有没有完成。' : 'Remind me to start this afternoon and check whether I finish.'}
                  </div>
                  <div className="bubble bubble--coke">
                    <span className="bubble__tag">Kap</span>
                    <span className="bubble__text">
                      {locale === 'zh'
                        ? '我会创建提醒，到点叫你，并在结束后回来确认完成情况。'
                        : "I'll create the reminder, nudge you at the time, and check back after."}
                    </span>
                    <span className="bubble__status">
                      <CheckCheck size={11} />
                      {locale === 'zh' ? '已同步' : 'Synced'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Ticker({ locale }: { locale: Locale }) {
  const items = TICKER_ITEMS[locale];

  return (
    <div className="ticker" aria-hidden="true">
      <div className="ticker-track">
        {[...items, ...items].map((item, index) => (
          <span key={`${item}-${index}`}>
            {item}
            <span className="sep">●</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function Capabilities({ locale }: { locale: Locale }) {
  const cards = CAPABILITY_CARDS[locale];

  return (
    <section className="block" id="capabilities">
      <div className="wrap">
        <span className="eyebrow">{locale === 'zh' ? '核心能力' : 'Capabilities'}</span>
        <h2>
          {locale === 'zh' ? 'Kap 已经是一条监督线程，' : 'Kap is already a supervision thread,'}
          <br />
          <em>{locale === 'zh' ? '从提醒到跟进都接起来。' : 'from reminders to follow-up.'}</em>
        </h2>
        <p className="lead">
          {locale === 'zh'
            ? '官网应该展示现在已经能体验到的东西：个人微信、WhatsApp、提醒、日历导入、订阅访问和重连恢复。'
            : 'The homepage should show what users can experience today: personal WeChat, WhatsApp, reminders, calendar import, subscription access, and channel recovery.'}
        </p>

        <div className="caps">
          {cards.map((card, index) => (
            <article key={card.title} className={`cap ${card.tone}`}>
              <span className="num">{String(index + 1).padStart(2, '0')}</span>
              <div className="eyebrow">{card.eyebrow}</div>
              <h3>{card.title}</h3>
              <p>{card.body}</p>
              <div className="illus">
                {index === 0 ? <MessageCircle size={28} /> : null}
                {index === 1 ? <WorkflowIcon size={28} /> : null}
                {index === 2 ? <Route size={28} /> : null}
                {index === 3 ? <CalendarCheck size={28} /> : null}
                {index === 4 ? <Activity size={28} /> : null}
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function Scenarios({ locale }: { locale: Locale }) {
  const scenarios = SCENARIOS[locale];

  return (
    <section className="block scenarios-block" id="scenarios">
      <div className="wrap">
        <span className="eyebrow">{locale === 'zh' ? '真实任务' : 'Real tasks'}</span>
        <h2>
          {locale === 'zh' ? '从一个需要监督的任务开始，' : 'Start from a task that needs supervision,'}
          <br />
          <span className="accent">{locale === 'zh' ? '然后让 Kap 持续跟进。' : 'then let Kap follow up.'}</span>
        </h2>
        <p className="lead">
          {locale === 'zh'
            ? '现在的产品重点不是泛泛地帮你写东西，而是把任务、提醒、通道和账号访问串成可以实际使用的监督闭环。'
            : 'The product is not positioned around generic drafting. It connects tasks, reminders, channels, and account access into a usable supervision loop.'}
        </p>

        <div className="scen-grid">
          {scenarios.map((scenario) => (
            <article key={scenario.title} className="scen">
              <span className="scn-tag">{scenario.tag}</span>
              <h3>{scenario.title}</h3>
              <p>{scenario.body}</p>
              <div className={`preview ${scenario.previewClass}`.trim()}>
                {scenario.preview.map((item) => (
                  <div key={`${scenario.title}-${item.text}`} className={`bubble ${item.type}`}>
                    {item.text}
                    {item.meta ? <small>{item.meta}</small> : null}
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function DemoPreview({ locale }: { locale: Locale }) {
  const isZh = locale === 'zh';
  const demos = DEMO_PREVIEWS[locale];

  return (
    <section className="block demo-preview-block" id="demos">
      <div className="wrap">
        <span className="eyebrow">{isZh ? '对话示例' : 'Conversation demos'}</span>
        <h2>
          {isZh ? '用真实对话看清监督闭环，' : 'See the supervision loop in real conversations,'}
          <br />
          <span className="accent">{isZh ? '再决定从哪里开始。' : 'then choose where to start.'}</span>
        </h2>
        <p className="lead">
          {isZh
            ? '示例展示用户第一句话、Kap 的追问、提醒创建和后续检查，不把产品讲成抽象能力清单。'
            : 'Examples show the first message, Kap clarification, reminder creation, and follow-up instead of another abstract capability list.'}
        </p>

        <div className="demo-preview-grid">
          {demos.map((demo) => (
            <article key={demo.title} className="demo-preview-card">
              <span>{demo.tag}</span>
              <h3>{demo.title}</h3>
              <p>{demo.body}</p>
            </article>
          ))}
        </div>

        <Link href="/demos" className="demo-preview-link">
          {isZh ? '查看全部对话示例' : 'View all conversation demos'}
          <ArrowRight size={15} aria-hidden="true" />
        </Link>
      </div>
    </section>
  );
}

function StartPath({ locale }: { locale: Locale }) {
  const isZh = locale === 'zh';
  const cards = isZh
    ? [
        {
          icon: MessageCircle,
          label: '国内用户',
          title: '先注册账号，再连接个人微信。',
          body: '注册并验证邮箱后，进入个人微信设置页。Kap 会把连接、断开、重连、续费这些下一步放在同一个账号流程里。',
          href: '/auth/register',
          cta: '创建账号',
        },
        {
          icon: Smartphone,
          label: '海外用户',
          title: '直接从 WhatsApp 发出第一条任务。',
          body: '如果你只想马上开始，把真实目标发给 WhatsApp 里的 Kap，让提醒和后续检查留在同一个线程里。',
          href: '/global',
          cta: '打开 WhatsApp',
        },
        {
          icon: CalendarCheck,
          label: '已有日程',
          title: '把 Google Calendar 接进提醒流。',
          body: '如果任务已经在日历里，登录账号后从日历导入页授权，让未来事件变成 Kap 对话里的提醒。',
          href: '/account/calendar-import',
          cta: '导入日历',
        },
      ]
    : [
        {
          icon: MessageCircle,
          label: 'Domestic users',
          title: 'Create an account, then connect Personal WeChat.',
          body: 'Register and verify email first. Kap keeps connect, disconnect, reconnect, and renewal steps visible in the same account flow.',
          href: '/auth/register',
          cta: 'Create account',
        },
        {
          icon: Smartphone,
          label: 'Global users',
          title: 'Send the first real task from WhatsApp.',
          body: 'If you want to start immediately, open the WhatsApp thread and tell Kap the goal. The reminder and follow-up stay in that same chat.',
          href: '/global',
          cta: 'Open WhatsApp',
        },
        {
          icon: CalendarCheck,
          label: 'Existing schedule',
          title: 'Bring Google Calendar into the reminder flow.',
          body: 'If your tasks already live on the calendar, sign in and authorize import so future events become Kap reminders.',
          href: '/account/calendar-import',
          cta: 'Import calendar',
        },
      ];

  return (
    <section className="block start-path-block" id="start-path">
      <div className="wrap">
        <span className="eyebrow">{isZh ? '怎么开始' : 'How to start'}</span>
        <h2>
          {isZh ? '选择最快的开始方式，' : 'Choose the fastest way to start,'}
          <br />
          <span className="accent">{isZh ? '然后把任务留给 Kap 跟进。' : 'then let Kap carry the follow-up.'}</span>
        </h2>
        <p className="lead">
          {isZh
            ? '入口可以不同，但产品目标是一致的：把真实承诺变成提醒、检查和后续动作。'
            : 'The entry can differ by user, but the product goal stays the same: turn a real commitment into a reminder, check-in, and next action.'}
        </p>

        <div className="start-path-grid">
          {cards.map((card) => {
            const Icon = card.icon;
            return (
              <article key={card.label} className="start-path-card">
                <div className="start-path-card__icon">
                  <Icon size={22} aria-hidden="true" />
                </div>
                <span className="start-path-card__label">{card.label}</span>
                <h3>{card.title}</h3>
                <p>{card.body}</p>
                <Link href={card.href} className="start-path-card__link">
                  {card.cta}
                  <ArrowRight size={14} aria-hidden="true" />
                </Link>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function QuoteBand({ locale }: { locale: Locale }) {
  const quote = QUOTE_BAND[locale];

  return (
    <section className="quoteband">
      <div className="inner">
        <blockquote>
          {quote.quote}
          <br />
          <span>{quote.accent}</span>
        </blockquote>
        <div className="cite">— {quote.cite}</div>
      </div>
    </section>
  );
}

function Voices({ locale }: { locale: Locale }) {
  const voices = VOICES[locale];

  return (
    <section className="block" id="voices">
      <div className="wrap">
        <span className="eyebrow">{locale === 'zh' ? '已实现能力' : 'Live capabilities'}</span>
        <h2>{locale === 'zh' ? '官网应该讲已经上线的能力，' : 'The homepage should sell what is live,'} <span className="accent">{locale === 'zh' ? '不是未来想象。' : 'not the future roadmap.'}</span></h2>
        <div className="voices">
          {voices.map((voice) => (
            <div key={`${voice.avatar}-${voice.role}`} className="voice">
              <div className="head">
                <div className="avatar">{voice.avatar}</div>
                <div>
                  <div className="who">Kap</div>
                  <div className="role">{voice.role}</div>
                </div>
              </div>
              <div className="stars">★★★★★</div>
              <blockquote>{voice.quote}</blockquote>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function DownloadPanel({ locale }: { locale: Locale }) {
  const {
    messages: { homepage },
  } = useLocale();
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim()) {
      return;
    }
    setSubmitted(true);
  }

  return (
    <section className="block" id="download">
      <div className="wrap">
        <div className="dl-card">
          <div>
            <span className="eyebrow">{locale === 'zh' ? '开始使用 Kap' : 'Start with Kap'}</span>
            <h2>{locale === 'zh' ? '先创建账号，\n再接入你的监督通道。' : 'Create the account,\nthen connect your supervision channel.'}</h2>
            <p className="lead">
              {homepage.contact.body}
            </p>

            <form className="download-form" onSubmit={handleSubmit}>
              {submitted ? (
                <div className="download-thanks">
                  <Check size={16} aria-hidden="true" />
                  {homepage.contact.thanks}
                </div>
              ) : (
                <>
                  <input
                    className="download-input"
                    type="email"
                    placeholder={homepage.contact.placeholder}
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                  <button type="submit" className="btn-sticker">
                    {homepage.contact.primaryCta}
                    <ArrowRight size={15} aria-hidden="true" />
                  </button>
                  <Link href="/auth/login" className="btn-ghost">
                    {homepage.contact.secondaryCta}
                  </Link>
                </>
              )}
            </form>

            <p className="download-note">{homepage.contact.note}</p>
          </div>

          <div className="plats">
            <Link href="/auth/register" className="plat">
              {locale === 'zh' ? '注册' : 'Register'}
              <small>{locale === 'zh' ? '公开入口' : 'Public entry'}</small>
            </Link>
            <Link href="/auth/login" className="plat">
              {locale === 'zh' ? '登录' : 'Sign in'}
              <small>{locale === 'zh' ? '已有账号' : 'Existing account'}</small>
            </Link>
            <Link href="/channels/wechat-personal" className="plat">
              {locale === 'zh' ? '微信设置' : 'WeChat setup'}
              <small>{locale === 'zh' ? '个人通道' : 'Personal channel'}</small>
            </Link>
            <Link href="/account/subscription" className="plat">
              {locale === 'zh' ? '订阅状态' : 'Renewal'}
              <small>{locale === 'zh' ? '账号访问' : 'Account access'}</small>
            </Link>
            <Link href="/global" className="plat">
              WhatsApp
              <small>{locale === 'zh' ? '全球入口' : 'Global entry'}</small>
            </Link>
            <Link href="/" className="plat">
              Kap AI
              <small>{locale === 'zh' ? '主站首页' : 'Main homepage'}</small>
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  const {
    messages: { homepage },
  } = useLocale();

  return (
    <footer className="site-footer">
      <div className="site-footer__inner">
        <div>
          <Link href="/" className="site-footer__brand brand" aria-label="Kap AI">
            <KapKoalaBadge className="brand__icon" />
            <span className="brand__mark">kap</span>
          </Link>
          <p className="site-footer__copy">{homepage.footer.tagline}</p>
        </div>

        <div className="site-footer__cols">
          <div>
            <div className="site-footer__h">{homepage.footer.productHeading}</div>
            {homepage.footer.productLinks.map((label, index) => (
              <Link key={label} href={FOOTER_LINKS.product[index] ?? '#'}>
                {label}
              </Link>
            ))}
          </div>
          <div>
            <div className="site-footer__h">{homepage.footer.accountHeading}</div>
            {homepage.footer.accountLinks.map((label, index) => (
              <Link key={label} href={FOOTER_LINKS.account[index] ?? '#'}>
                {label}
              </Link>
            ))}
          </div>
          <div>
            <div className="site-footer__h">{homepage.footer.companyHeading}</div>
            {homepage.footer.companyLinks.map((label, index) => (
              <Link key={label} href={FOOTER_LINKS.company[index] ?? '#'}>
                {label}
              </Link>
            ))}
          </div>
        </div>
      </div>

      <div className="site-footer__bar">
        <span>{homepage.footer.copyright}</span>
        <span>Kap AI</span>
      </div>
    </footer>
  );
}

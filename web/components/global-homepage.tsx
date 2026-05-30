import { ArrowRight, CalendarCheck2, CheckCheck, MessageCircle, Sparkles, Waypoints } from 'lucide-react';

import { KapKoalaBadge, KapKoalaHero } from './kap-brand';

export const GLOBAL_WHATSAPP_URL =
  'https://api.whatsapp.com/send/?phone=8619917902815&text=Hi%20Kap%2C%20I%27d%20like%20to%20get%20started.';

const PROMISE_CARDS = [
  {
    title: 'Start where the conversation already lives',
    body: 'If WhatsApp is the fastest way to begin, Kap should meet you there without adding a second product to learn.',
  },
  {
    title: 'Carry the next action in the same thread',
    body: 'Set the goal, choose the time, create the reminder, and keep the check-in visible without resetting context.',
  },
  {
    title: 'Keep the entry simple',
    body: 'Open the chat, send the real task, and keep moving. No dashboard maze, no extra ceremony.',
  },
] as const;

const WORKFLOW_STEPS = [
  {
    label: 'Start with the task',
    title: 'Say what needs to happen next',
    body: 'A goal to finish. A time to start. A reminder to keep. Start with the real thing that needs supervision.',
  },
  {
    label: 'Keep it in one thread',
    title: 'Set the goal and the time',
    body: 'Tell Kap what needs doing and when to check back, then keep the reminder context in the same chat.',
  },
  {
    label: 'Keep momentum',
    title: 'Let Kap carry the open loop forward',
    body: 'Use the same thread for reminders, check-ins, and the next action that still needs attention after the first reply.',
  },
] as const;

type ChatThreadMessage = {
  who: 'user' | 'kap';
  text: string;
  status?: string;
};

const CHAT_THREAD: ReadonlyArray<ChatThreadMessage> = [
  { who: 'user', text: 'I need to finish one focused work block today.' },
  {
    who: 'kap',
    text: 'What time should I remind you to start, and when should I check whether it is done?',
    status: 'Reminder pending',
  },
  { who: 'user', text: 'Remind me at 3pm and check at 4pm.' },
  { who: 'kap', text: 'Set. I will nudge you at 3pm and check back at 4pm.', status: 'Follow-up active' },
] as const;

const GLOBAL_TICKER_ITEMS = [
  'One WhatsApp entry',
  'The next move stays visible',
  'Kap keeps the same thread moving',
  'Start fast, keep context',
] as const;

function WhatsAppButton({ label, className = '' }: { label: string; className?: string }) {
  const resolvedClassName = className ? `global-cta global-cta--primary ${className}` : 'global-cta global-cta--primary';

  return (
    <a href={GLOBAL_WHATSAPP_URL} className={resolvedClassName} target="_blank" rel="noreferrer">
      <span>{label}</span>
      <ArrowRight size={16} aria-hidden="true" />
    </a>
  );
}

export function GlobalHomepage() {
  return (
    <div className="coke-site global-site global-site--kap">
      <header className="global-header">
        <div className="global-header__inner">
          <a href="/global" className="global-brand" aria-label="Kap global">
            <KapKoalaBadge className="global-brand__icon" />
            <span className="global-brand__wordmark">kap</span>
          </a>

          <nav className="global-nav" aria-label="Global page">
            <a href="#promise" className="global-nav__link">
              Why Kap
            </a>
            <a href="#workflow" className="global-nav__link">
              How it works
            </a>
            <a href="#close" className="global-nav__link">
              Start now
            </a>
          </nav>

          <WhatsAppButton label="Open WhatsApp" />
        </div>
      </header>

      <main>
        <section className="global-hero">
          <div className="global-hero__aurora global-hero__aurora--left" aria-hidden="true" />
          <div className="global-hero__aurora global-hero__aurora--right" aria-hidden="true" />
          <div className="global-hero__inner">
            <div className="global-hero__copy">
              <div className="global-kicker">
                <MessageCircle size={14} aria-hidden="true" />
                <span>Available on WhatsApp</span>
              </div>

              <h1 className="global-hero__title">Start with one WhatsApp message.</h1>
              <p className="global-hero__lede">Tell Kap what needs doing and when to check back.</p>
              <p className="global-hero__body">
                Turn one real goal into a reminder and follow-up thread without leaving the chat you already opened.
              </p>

              <div className="global-hero__actions">
                <WhatsAppButton label="Message Kap on WhatsApp" className="global-hero__cta" />
              </div>

              <ul className="global-proof" aria-label="Product promise">
                <li className="global-proof__item">
                  <Sparkles size={14} aria-hidden="true" />
                  <span>Open chat in one tap</span>
                </li>
                <li className="global-proof__item">
                  <Waypoints size={14} aria-hidden="true" />
                  <span>Stay in one thread</span>
                </li>
                <li className="global-proof__item">
                  <CalendarCheck2 size={14} aria-hidden="true" />
                  <span>No extra setup</span>
                </li>
              </ul>
            </div>

            <div className="global-hero__stage" aria-hidden="true">
              <div className="global-hero__scene">
                <div className="global-hero__scene-sticker">WhatsApp first</div>
                <KapKoalaHero className="global-hero__mascot" />

                <div className="global-hero__phone">
                  <div className="global-hero__phone-top">
                    <div className="global-hero__phone-app">
                      <MessageCircle size={14} />
                      <span>WhatsApp thread</span>
                    </div>
                    <div className="global-hero__phone-meta">Kap is ready</div>
                  </div>

                  <div className="global-thread">
                    {CHAT_THREAD.map((message, index) => (
                      <div key={index} className={`global-thread__bubble global-thread__bubble--${message.who}`}>
                        <p>{message.text}</p>
                        {message.status ? (
                          <span className="global-thread__status">
                            <CheckCheck size={12} aria-hidden="true" />
                            {message.status}
                          </span>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <div className="global-ticker" aria-hidden="true">
          <div className="global-ticker__track">
            {[...GLOBAL_TICKER_ITEMS, ...GLOBAL_TICKER_ITEMS].map((item, index) => (
              <span key={`${item}-${index}`}>
                {item}
                <span className="sep">●</span>
              </span>
            ))}
          </div>
        </div>

        <section id="promise" className="global-section">
          <div className="global-section__head">
            <span className="global-section__eyebrow">Why Kap</span>
            <h2 className="global-section__title">One focused entry into the same Kap product</h2>
            <p className="global-section__body">
              The global page only has one job: get you into the WhatsApp thread fast, then keep the reminder,
              check-in, and follow-up there.
            </p>
          </div>

          <div className="global-promise-grid">
            {PROMISE_CARDS.map((card) => (
              <article key={card.title} className="global-promise-card">
                <span className="global-promise-card__marker" aria-hidden="true" />
                <h3>{card.title}</h3>
                <p>{card.body}</p>
              </article>
            ))}
          </div>

          <div className="global-inline-cta">
            <WhatsAppButton label="Start the conversation" />
          </div>
        </section>

        <section id="workflow" className="global-section global-section--workflow">
          <div className="global-section__head">
            <span className="global-section__eyebrow">How it works</span>
            <h2 className="global-section__title">Simple enough to start in seconds</h2>
          </div>

          <div className="global-workflow">
            {WORKFLOW_STEPS.map((step, index) => (
              <article key={step.title} className="global-workflow__step">
                <div className="global-workflow__index">{String(index + 1).padStart(2, '0')}</div>
                <div className="global-workflow__copy">
                  <p className="global-workflow__label">{step.label}</p>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section id="close" className="global-close">
          <div className="global-close__inner">
            <div>
              <span className="global-section__eyebrow global-section__eyebrow--light">Open the thread</span>
              <h2 className="global-close__title">Start on WhatsApp, then keep everything in the same thread.</h2>
              <p className="global-close__body">
                Open the chat, send the goal once, and let Kap carry the reminder, check-in, and next action forward
                from there.
              </p>
            </div>

            <WhatsAppButton label="Open WhatsApp now" className="global-close__cta" />
          </div>
        </section>
      </main>
    </div>
  );
}

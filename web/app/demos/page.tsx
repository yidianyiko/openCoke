import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, CalendarCheck, CheckCheck, MessageCircle, RotateCcw } from 'lucide-react';

import { CokePublicShell } from '../../components/coke-public-shell';

export const metadata: Metadata = {
  title: 'Demos | Kap AI',
  description: 'Concrete Kap AI conversation demos for reminders, follow-up, WhatsApp, Personal WeChat, and Google Calendar import.',
};

const DEMOS = [
  {
    tag: 'Study',
    title: 'Finish one IELTS practice set',
    summary: 'Kap turns a vague study intention into a scheduled reminder and a later completion check.',
    status: 'Follow-up active',
    icon: CheckCheck,
    messages: [
      { who: 'user', text: 'I need to finish one IELTS practice set this afternoon.' },
      { who: 'kap', text: 'What time should I remind you to start, and when should I check whether it is done?' },
      { who: 'user', text: 'Remind me at 3pm and check at 4pm.' },
      { who: 'kap', text: 'Set. I will nudge you at 3pm and check back at 4pm.' },
    ],
  },
  {
    tag: 'Life admin',
    title: 'Pay the credit card bill',
    summary: 'A small administrative task becomes visible before it turns into a missed deadline.',
    status: 'Reminder set',
    icon: MessageCircle,
    messages: [
      { who: 'user', text: 'Remind me to pay the credit card bill tomorrow morning.' },
      { who: 'kap', text: 'I can do that. What time tomorrow morning should I remind you?' },
      { who: 'user', text: '9am.' },
      { who: 'kap', text: 'Done. I will remind you tomorrow at 9am.' },
    ],
  },
  {
    tag: 'Calendar',
    title: 'Turn Google Calendar events into reminders',
    summary: 'A calendar-heavy user can connect events to the same supervision thread.',
    status: 'Calendar import',
    icon: CalendarCheck,
    messages: [
      { who: 'user', text: 'My week is already in Google Calendar. Can Kap follow those events?' },
      { who: 'kap', text: 'Open the import page, authorize Google, and I will turn future events into Kap reminders.' },
      { who: 'user', text: 'I want the reminders in this conversation.' },
      { who: 'kap', text: 'Use the account import flow and I will attach imported reminders here.' },
    ],
  },
  {
    tag: 'Habit',
    title: 'Keep a daily walking habit visible',
    summary: 'Kap keeps a habit concrete by asking for timing instead of accepting a loose intention.',
    status: 'Check-in ready',
    icon: CheckCheck,
    messages: [
      { who: 'user', text: 'I want to walk after dinner every day.' },
      { who: 'kap', text: 'What time should I remind you, and should I check whether you actually went?' },
      { who: 'user', text: 'Remind me at 8pm and check at 9pm.' },
      { who: 'kap', text: 'Set. I will remind you at 8pm and check back at 9pm.' },
    ],
  },
  {
    tag: 'WeChat',
    title: 'Recover a Personal WeChat channel',
    summary: 'Kap keeps account and channel recovery steps legible instead of hiding them in support text.',
    status: 'Reconnect path',
    icon: RotateCcw,
    messages: [
      { who: 'user', text: 'My WeChat connection stopped working. What should I do?' },
      { who: 'kap', text: 'Check your account state first. If access is active, open Personal WeChat setup and scan again.' },
      { who: 'user', text: 'Do I need to renew?' },
      { who: 'kap', text: 'If renewal is required, the account page will show it before reconnect.' },
    ],
  },
  {
    tag: 'WhatsApp',
    title: 'Start from WhatsApp',
    summary: 'A global user can begin with one real task instead of learning a dashboard first.',
    status: 'Global entry',
    icon: MessageCircle,
    messages: [
      { who: 'user', text: 'Hi Kap, I need help making sure I finish a focused work block today.' },
      { who: 'kap', text: 'What time should I remind you to start, and when should I check whether it is done?' },
      { who: 'user', text: 'Start at 2pm. Check at 3:30pm.' },
      { who: 'kap', text: 'Set. I will keep this in the same WhatsApp thread.' },
    ],
  },
] as const;

export default function DemosPage() {
  return (
    <CokePublicShell>
      <section className="demo-page">
        <div className="wrap">
          <div className="demo-page__hero">
            <span className="eyebrow">Conversation demos</span>
            <h1>See how Kap turns a message into follow-up.</h1>
            <p>
              These examples show the live product shape: reminders, check-ins, account access, Personal WeChat,
              WhatsApp, and Google Calendar import.
            </p>
            <div className="demo-page__actions">
              <Link href="/global" className="btn-sticker">
                Start on WhatsApp
                <ArrowRight size={15} aria-hidden="true" />
              </Link>
              <Link href="/auth/register" className="btn-ghost">
                Create account
              </Link>
            </div>
          </div>

          <div className="demo-grid">
            {DEMOS.map((demo) => {
              const Icon = demo.icon;
              return (
                <article key={demo.title} className="demo-card">
                  <div className="demo-card__top">
                    <div className="demo-card__icon">
                      <Icon size={20} aria-hidden="true" />
                    </div>
                    <span>{demo.tag}</span>
                  </div>
                  <h2>{demo.title}</h2>
                  <p>{demo.summary}</p>
                  <div className="demo-thread">
                    {demo.messages.map((message, index) => (
                      <div key={`${demo.title}-${index}`} className={`demo-bubble demo-bubble--${message.who}`}>
                        {message.text}
                      </div>
                    ))}
                  </div>
                  <div className="demo-card__status">
                    <CheckCheck size={13} aria-hidden="true" />
                    {demo.status}
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </section>
    </CokePublicShell>
  );
}

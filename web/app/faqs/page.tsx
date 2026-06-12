import type { Metadata } from 'next';

import { PublicInfoPage } from '../../components/public-info-page';

export const metadata: Metadata = {
  title: 'FAQ | Kap AI',
  description: 'Answers about starting Kap, using Personal WeChat or WhatsApp, reminders, follow-up, and Google Calendar import.',
};

const FAQ_SECTIONS = [
  {
    title: 'What is Kap?',
    body: 'Kap is an AI supervision thread for goals that need reminders, check-ins, and follow-up. It is built to keep the next action visible after the first message.',
  },
  {
    title: 'How do I start using Kap?',
    body: 'Domestic users can register and connect a Personal WeChat channel. Global users can open the WhatsApp entry and send the first real task there.',
  },
  {
    title: 'What can I ask Kap to track?',
    body: 'Start with a concrete commitment: a study block, work deadline, habit, errand, payment, appointment, or anything that needs a reminder and a later check-in.',
  },
  {
    title: 'Can Kap use Google Calendar?',
    body: 'Yes. If your schedule already lives in Google Calendar, the account import flow can turn future events into Kap reminders attached to your active conversation.',
  },
  {
    title: 'Is Kap free to try?',
    body: 'Kap has public registration and account access flows. If a subscription or renewal step is required, the account page shows the next action before channel use continues.',
  },
  {
    title: 'Where does the conversation happen?',
    body: 'Kap currently exposes Personal WeChat for domestic users and a focused WhatsApp global entry. Account pages also handle verification, renewal, and reconnect steps.',
  },
] as const;

export default function FaqsPage() {
  return (
    <PublicInfoPage
      eyebrow="FAQ"
      title="Frequently asked questions"
      lead="A short guide to what Kap does today, how to start, and where reminders, follow-up, channels, and calendar import fit."
      sections={FAQ_SECTIONS}
      primaryLink={{ href: '/global', label: 'Start on WhatsApp' }}
      secondaryLink={{ href: '/auth/register', label: 'Create account' }}
    />
  );
}

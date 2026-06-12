import type { Metadata } from 'next';

import { PublicInfoPage } from '../../components/public-info-page';

export const metadata: Metadata = {
  title: 'Terms | Kap AI',
  description: 'Terms of Use for Kap AI public access, reminders, follow-up, channel setup, and calendar import.',
};

const TERMS_SECTIONS = [
  {
    title: 'Service scope',
    body: 'Kap helps you manage reminders, check-ins, follow-up, channel access, and calendar import flows. The service is meant to support personal supervision, not replace professional advice.',
  },
  {
    title: 'Your responsibility',
    body: 'You are responsible for the tasks, decisions, and commitments you ask Kap to track. Kap can remind and follow up, but you remain responsible for acting on the information.',
  },
  {
    title: 'Account and channel access',
    body: 'You should keep your account, subscription, WeChat, WhatsApp, and Google authorization information accurate and under your control.',
  },
  {
    title: 'Acceptable use',
    body: 'Do not use Kap to send unlawful, abusive, deceptive, or harmful content, or to interfere with channel providers, infrastructure, or other users.',
  },
  {
    title: 'Availability',
    body: 'Kap depends on messaging providers, calendar providers, and network services. We may change, suspend, or limit parts of the public service as the product evolves.',
  },
  {
    title: 'Privacy',
    body: 'Our Privacy Notice explains what information is used to run Kap, including account, channel, reminder, and calendar-import data.',
  },
] as const;

export default function TermsPage() {
  return (
    <PublicInfoPage
      eyebrow="Terms"
      title="Terms of Use"
      lead="These terms describe the basic public-service expectations for using Kap to manage reminders, follow-up, channels, and calendar import."
      sections={TERMS_SECTIONS}
      primaryLink={{ href: '/privacy', label: 'Read privacy notice' }}
      secondaryLink={{ href: '/faqs', label: 'Read FAQ' }}
    />
  );
}

import type { Metadata } from 'next';

import { PublicInfoPage } from '../../components/public-info-page';

export const metadata: Metadata = {
  title: 'Privacy | Kap AI',
  description: 'Privacy Notice for Kap AI account, channel, reminder, follow-up, and Google Calendar import data.',
};

const PRIVACY_SECTIONS = [
  {
    title: 'Information we use',
    body: 'We use your account, channel, reminder, and calendar-import information to run the Kap service. That can include email, verification state, conversation context, reminders, and provider connection status.',
  },
  {
    title: 'Channels',
    body: 'Kap uses channel information for WeChat and WhatsApp delivery so it can route reminders, check-ins, reconnect states, and account-access steps to the right place.',
  },
  {
    title: 'Google Calendar',
    body: 'If you authorize Google Calendar import, Kap uses calendar event details to create reminders in the active Kap conversation. You should only connect calendars you control.',
  },
  {
    title: 'How information is used',
    body: 'Kap uses service data to create reminders, schedule follow-up, show account status, recover channel connections, and keep the next required action visible.',
  },
  {
    title: 'Retention and control',
    body: 'Account, reminder, channel, and calendar-import records may remain while needed to provide the service, troubleshoot issues, or preserve user-visible state.',
  },
  {
    title: 'Contact and updates',
    body: 'We may update this notice as Kap changes. The public FAQ and account pages should remain the clearest place to understand what is available today.',
  },
] as const;

export default function PrivacyPage() {
  return (
    <PublicInfoPage
      eyebrow="Privacy"
      title="Privacy Notice"
      lead="A practical summary of the information Kap uses to run reminders, follow-up, channel delivery, account access, and Google Calendar import."
      sections={PRIVACY_SECTIONS}
      primaryLink={{ href: '/terms', label: 'Read terms' }}
      secondaryLink={{ href: '/faqs', label: 'Read FAQ' }}
    />
  );
}

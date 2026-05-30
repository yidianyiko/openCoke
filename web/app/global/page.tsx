import type { Metadata } from 'next';

import { GlobalHomepage } from '../../components/global-homepage';

export const metadata: Metadata = {
  title: 'kap global | WhatsApp supervision that follows up',
  description: 'Start a WhatsApp thread with Kap to turn one real goal into a reminder, check-in, and follow-up loop.',
};

export default function GlobalPage() {
  return <GlobalHomepage />;
}

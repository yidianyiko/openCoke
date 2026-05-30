'use client';

import type { ReactNode } from 'react';

import { CustomerShell } from '../../../components/customer-shell';

export default function CustomerAccountLayout({ children }: { children: ReactNode }) {
  return <CustomerShell>{children}</CustomerShell>;
}

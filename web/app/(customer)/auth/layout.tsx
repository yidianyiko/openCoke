'use client';

import type { ReactNode } from 'react';

import { CustomerAuthShell } from '../../../components/customer-auth-shell';

export default function CustomerAuthLayout({ children }: { children: ReactNode }) {
  return <CustomerAuthShell>{children}</CustomerAuthShell>;
}

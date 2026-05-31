import type { ApiResponse } from './api-types';
import { customerApi } from './customer-api';

interface CustomerClaimRequestInput {
  entryToken: string;
  email: string;
  next?: string;
}

interface CustomerClaimRequestResult {
  message: 'claim_email_sent';
}

export interface CustomerGoogleCalendarImportRunSummary {
  id: string;
  status: 'authorizing' | 'importing' | 'succeeded' | 'succeeded_with_errors' | 'failed';
  providerAccountEmail: string | null;
  importedCount: number;
  skippedCount: number;
  failedCount: number;
  errorSummary: string | null;
}

export interface CustomerGoogleCalendarImportPreflightResult {
  ready: boolean;
  blockedReason?: string | null;
  latestRun: CustomerGoogleCalendarImportRunSummary | null;
}

interface CustomerGoogleCalendarImportStartResult {
  runId: string;
  url: string;
}

interface CustomerGoogleCalendarImportStatusResult {
  run?: CustomerGoogleCalendarImportRunSummary | null;
  latestRun: CustomerGoogleCalendarImportRunSummary | null;
}

export function requestCustomerClaimEmail(
  _input: CustomerClaimRequestInput,
): Promise<ApiResponse<CustomerClaimRequestResult>> {
  return Promise.resolve({ ok: false, error: 'claim_email_flow_unavailable' });
}

export function getCustomerGoogleCalendarImportPreflight(): Promise<
  ApiResponse<CustomerGoogleCalendarImportPreflightResult>
> {
  return getCustomerGoogleCalendarImportPreflightForHandoff();
}

export function getCustomerGoogleCalendarImportPreflightForHandoff(
  _handoff?: string,
): Promise<ApiResponse<CustomerGoogleCalendarImportPreflightResult>> {
  return customerApi
    .get<{ access_allowed: boolean; denial_reason: string | null }>('/api/account/access-status')
    .then((access) => ({
      ok: true,
      data: {
        ready: false,
        blockedReason: access.access_allowed
          ? 'calendar_import_browser_flow_unavailable'
          : access.denial_reason,
        latestRun: null,
      },
    }));
}

export function startCustomerGoogleCalendarImport(
  _handoff?: string,
): Promise<
  ApiResponse<CustomerGoogleCalendarImportStartResult>
> {
  return Promise.resolve({ ok: false, error: 'calendar_import_browser_flow_unavailable' });
}

export function claimCustomerCalendarImportHandoff(
  _token: string,
): Promise<ApiResponse<{ status: string; continue_to: string }>> {
  return Promise.resolve({ ok: false, error: 'calendar_import_handoff_unavailable' });
}

export function getCustomerGoogleCalendarImportStatusForRun(
  _runId?: string,
): Promise<ApiResponse<CustomerGoogleCalendarImportStatusResult>> {
  return Promise.resolve({
    ok: true,
    data: {
      run: null,
      latestRun: null,
    },
  });
}

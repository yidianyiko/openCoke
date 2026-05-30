import type { ApiResponse } from '../../shared/src/types/api';
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
  input: CustomerClaimRequestInput,
): Promise<ApiResponse<CustomerClaimRequestResult>> {
  return customerApi.post<ApiResponse<CustomerClaimRequestResult>>('/api/auth/claim/request', input);
}

export function getCustomerGoogleCalendarImportPreflight(): Promise<
  ApiResponse<CustomerGoogleCalendarImportPreflightResult>
> {
  return getCustomerGoogleCalendarImportPreflightForHandoff();
}

export function getCustomerGoogleCalendarImportPreflightForHandoff(
  handoff?: string,
): Promise<ApiResponse<CustomerGoogleCalendarImportPreflightResult>> {
  return customerApi.get<ApiResponse<CustomerGoogleCalendarImportPreflightResult>>(
    handoff
      ? `/api/customer/google-calendar-import/preflight?handoff=${encodeURIComponent(handoff)}`
      : '/api/customer/google-calendar-import/preflight',
  );
}

export function startCustomerGoogleCalendarImport(
  handoff?: string,
): Promise<
  ApiResponse<CustomerGoogleCalendarImportStartResult>
> {
  return customerApi.post<ApiResponse<CustomerGoogleCalendarImportStartResult>>(
    '/api/customer/google-calendar-import/start',
    handoff ? { handoff } : undefined,
  );
}

export function claimCustomerCalendarImportHandoff(
  token: string,
): Promise<ApiResponse<{ status: string; continue_to: string }>> {
  return customerApi.post<ApiResponse<{ status: string; continue_to: string }>>(
    '/api/customer/calendar-import-handoffs/claim',
    { token },
  );
}

export function getCustomerGoogleCalendarImportStatusForRun(
  runId?: string,
): Promise<ApiResponse<CustomerGoogleCalendarImportStatusResult>> {
  return customerApi.get<ApiResponse<CustomerGoogleCalendarImportStatusResult>>(
    runId
      ? `/api/customer/google-calendar-import/status?runId=${encodeURIComponent(runId)}`
      : '/api/customer/google-calendar-import/status',
  );
}

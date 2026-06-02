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

type CleanRouteError = {
  error: {
    code: string;
  };
};

function isCleanRouteError(value: unknown): value is CleanRouteError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as CleanRouteError).error?.code === 'string'
  );
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
  return customerApi
    .post<{ accepted: boolean } | CleanRouteError>('/api/claim/email', {
      entry_token: input.entryToken,
      email: input.email,
      continuation: input.next ? { next: input.next } : {},
    })
    .then((result) => {
      if (!isCleanRouteError(result)) {
        return { ok: true, data: { message: 'claim_email_sent' } };
      }
      if (
        ['artifact_not_found', 'artifact_expired', 'artifact_consumed', 'artifact_wrong_type'].includes(
          result.error.code,
        )
      ) {
        return { ok: false, error: 'invalid_or_expired_token' };
      }
      if (result.error.code === 'email_already_registered') {
        return { ok: false, error: 'email_already_exists' };
      }
      return { ok: false, error: result.error.code };
    });
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

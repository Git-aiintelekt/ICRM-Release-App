import { ApiError, apiFetch, getToken } from './apiClient';

export function getUsers() {
  return apiFetch('/api/admin/users');
}

export function updateUserAccess(userId, changes) {
  return apiFetch(`/api/admin/users/${userId}`, { method: 'PATCH', json: changes });
}

function auditParams({ action, username, from, to }, params = new URLSearchParams()) {
  if (action) params.set('action', action);
  if (username) params.set('username', username);
  if (from) params.set('from', from);
  if (to) params.set('to', to);
  return params;
}

export function getAuditLog({ limit = 50, offset = 0, ...filters } = {}) {
  const params = auditParams(filters, new URLSearchParams({ limit: String(limit), offset: String(offset) }));
  return apiFetch(`/api/admin/audit-log?${params}`);
}

// Every entry matching the filters as a CSV file (fetched with the sign-in token, so a plain link wouldn't work).
export async function downloadAuditLogCsv(filters = {}) {
  const token = getToken();
  const response = await fetch(`/api/admin/audit-log.csv?${auditParams(filters)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const body = response.headers.get('content-type')?.includes('application/json') ? await response.json() : null;
    throw new ApiError(response.status, body?.detail ?? `Download failed with status ${response.status}`);
  }
  const name = /filename="([^"]+)"/.exec(response.headers.get('content-disposition') ?? '')?.[1] ?? 'audit-log.csv';
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

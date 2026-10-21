import { apiFetch } from './apiClient';

export function parseReleaseDocument(file) {
  const body = new FormData();
  body.append('file', file);
  return apiFetch('/api/admin/releases/parse', { method: 'POST', body });
}

export function publishRelease(release) {
  return apiFetch('/api/admin/releases', { method: 'POST', json: release });
}

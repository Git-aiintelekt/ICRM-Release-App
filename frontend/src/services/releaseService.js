import { apiFetch } from './apiClient';

export function getReleases() {
  return apiFetch('/api/releases');
}

import { apiFetch } from './apiClient';

export function getReleases() {
  return apiFetch('/api/releases');
}

// The public page (no sign-in): the same release notes without Jira numbers, while the server has it switched on.
export function getPublicReleases() {
  return apiFetch('/api/public/releases');
}

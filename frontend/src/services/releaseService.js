import { apiFetch } from './apiClient';

export function getReleases() {
  return apiFetch('/api/releases');
}

// The public page (no sign-in): the same release notes without Jira numbers, while the server has it switched on.
// key: the public link's key (/public/release-notes/<key>); none = the first product.
const keyQuery = (key) => (key ? `?key=${encodeURIComponent(key)}` : '');

export function getPublicReleases(key) {
  return apiFetch(`/api/public/releases${keyQuery(key)}`);
}

// { label }: the product or client the public link shows.
export function getPublicProduct(key) {
  return apiFetch(`/api/public/product${keyQuery(key)}`);
}

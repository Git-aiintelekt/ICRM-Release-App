import { apiFetch } from './apiClient';

export function parseReleaseDocument(file) {
  const body = new FormData();
  body.append('file', file);
  return apiFetch('/api/admin/releases/parse', { method: 'POST', body });
}

export function publishRelease(release) {
  return apiFetch('/api/admin/releases', { method: 'POST', json: release });
}

// Versions that have a release/ branch in Bitbucket, newest first, each with the branch it is compared against.
export function getBitbucketVersions() {
  return apiFetch('/api/integrations/release-notes/versions');
}

// A draft in the same shape as parseReleaseDocument(), from the version's commits and their Jira issues.
export function draftFromBitbucket(version) {
  return apiFetch('/api/integrations/release-notes/draft', { method: 'POST', json: { version } });
}

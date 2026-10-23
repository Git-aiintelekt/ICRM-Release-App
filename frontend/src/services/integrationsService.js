import { apiFetch } from './apiClient';

// Live Jira Cloud / Bitbucket Cloud data, always through Django (tokens never reach the browser).
const BASE = '/api/integrations';

function query(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    (Array.isArray(value) ? value : [value]).forEach((v) => {
      if (v !== undefined && v !== null && v !== '') {
        search.append(key, String(v));
      }
    });
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

// productId: the status as that product sees it (its repositories); otherwise the header's product.
export const getIntegrationStatus = (productId) =>
  apiFetch(`${BASE}/status`, productId ? { headers: { 'X-Product': String(productId) } } : undefined);
export const refreshIntegrations = () => apiFetch(`${BASE}/refresh`, { method: 'POST' });
// Admins: limit every screen to chosen branches (kind BRANCH + repository) or Jira fix versions (kind FIX_VERSION).
export const addScope = ({ kind, repository, value }) =>
  apiFetch(`${BASE}/scope`, { method: 'POST', json: { kind, repository, value } });
export const removeScope = (id) => apiFetch(`${BASE}/scope/${id}`, { method: 'DELETE' });
export const getDashboard = () => apiFetch(`${BASE}/dashboard`);

export const getJiraFilters = () => apiFetch(`${BASE}/jira/filters`);
// release: only the Jira issues of that published release (found in its release branch's commits).
export function getJiraIssues({ q, release, type, status, state, fixVersion, createdFrom, createdTo, pageToken, limit = 25 } = {}) {
  return apiFetch(
    `${BASE}/jira/issues${query({ q, release, type, status, state, fixVersion, createdFrom, createdTo, pageToken, limit })}`
  );
}

const repoUrl = (slug) => `${BASE}/bitbucket/repositories/${encodeURIComponent(slug)}`;
export const getRepositories = () => apiFetch(`${BASE}/bitbucket/repositories`);
export const getBranches = (slug, { q, page = 1, limit = 25 } = {}) =>
  apiFetch(`${repoUrl(slug)}/branches${query({ q, page, limit })}`);
export const getCommits = (slug, { branch, page = 1, limit = 25 } = {}) =>
  apiFetch(`${repoUrl(slug)}/commits${query({ branch, page, limit })}`);
export const getPullRequests = (slug, { state, branch, page = 1, limit = 25 } = {}) =>
  apiFetch(`${repoUrl(slug)}/pullrequests${query({ state, branch, page, limit })}`);

// Admins: the Jira / Bitbucket accounts and tokens. Tokens are never returned, only whether they are set.
export const getCredentials = () => apiFetch(`${BASE}/credentials`);
// { jiraBaseUrl: '...', jiraApiToken: '...' }: only the settings to change; '' or null removes a saved value.
export const saveCredentials = (changes) => apiFetch(`${BASE}/credentials`, { method: 'PUT', json: changes });

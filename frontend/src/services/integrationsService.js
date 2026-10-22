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

export const getIntegrationStatus = () => apiFetch(`${BASE}/status`);
export const refreshIntegrations = () => apiFetch(`${BASE}/refresh`, { method: 'POST' });
// Admins: limit every screen to chosen branches (kind BRANCH + repository) or Jira fix versions (kind FIX_VERSION).
export const addScope = ({ kind, repository, value }) =>
  apiFetch(`${BASE}/scope`, { method: 'POST', json: { kind, repository, value } });
export const removeScope = (id) => apiFetch(`${BASE}/scope/${id}`, { method: 'DELETE' });
export const getDashboard = () => apiFetch(`${BASE}/dashboard`);

export const getJiraFilters = () => apiFetch(`${BASE}/jira/filters`);
export const getJiraSummary = (fixVersion) => apiFetch(`${BASE}/jira/summary${query({ fixVersion })}`);
export const getJiraReleases = () => apiFetch(`${BASE}/jira/releases`);
export function getJiraIssues({ q, type, status, state, fixVersion, createdFrom, createdTo, pageToken, limit = 25 } = {}) {
  return apiFetch(
    `${BASE}/jira/issues${query({ q, type, status, state, fixVersion, createdFrom, createdTo, pageToken, limit })}`
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

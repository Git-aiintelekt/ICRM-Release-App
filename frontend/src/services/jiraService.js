import { apiFetch } from './apiClient';

const JIRA_ISSUES_URL = '/api/jira-issues';

export function getJiraIssues() {
  return apiFetch(JIRA_ISSUES_URL);
}

export function getJiraIssueDetail(jiraId) {
  return apiFetch(`${JIRA_ISSUES_URL}/${encodeURIComponent(jiraId)}`);
}

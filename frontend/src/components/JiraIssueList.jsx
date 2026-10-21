import { useMemo, useState } from 'react';

function JiraIssueList({ issues, selectedId, onSelect }) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return issues;
    }
    return issues.filter(
      (issue) =>
        issue.jiraId.toLowerCase().includes(q) ||
        (issue.description ?? '').toLowerCase().includes(q)
    );
  }, [issues, query]);

  return (
    <nav className="jira-list" aria-label="Jira issues">
      <input
        type="search"
        className="jira-search"
        placeholder="Search by ID or description..."
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <p className="jira-list-count">
        {filtered.length} of {issues.length} issues
      </p>
      <ul>
        {filtered.map((issue) => (
          <li key={issue.jiraId}>
            <button
              type="button"
              className={
                issue.jiraId === selectedId ? 'jira-item jira-item-active' : 'jira-item'
              }
              onClick={() => onSelect(issue.jiraId)}
            >
              <span className="jira-item-id">{issue.jiraId}</span>
              <span className="jira-item-desc">{issue.description || 'No description'}</span>
              {(issue.seedCount > 0 || issue.tableCount > 0) && (
                <span className="jira-item-counts">
                  {issue.seedCount} seeds &middot; {issue.tableCount} tables
                </span>
              )}
            </button>
          </li>
        ))}
        {filtered.length === 0 && <li className="jira-empty">No matching issues.</li>}
      </ul>
    </nav>
  );
}

export default JiraIssueList;

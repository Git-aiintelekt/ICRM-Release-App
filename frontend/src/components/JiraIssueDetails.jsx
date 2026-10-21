function EntryContent({ content }) {
  if (!content) {
    return null;
  }
  return <pre className="jira-entry-content"><code>{content}</code></pre>;
}

function JiraIssueDetails({ issue, loading, error }) {
  if (loading) {
    return <p>Loading issue details...</p>;
  }

  if (error) {
    return <p>{error}</p>;
  }

  if (!issue) {
    return <p>Select a Jira issue to see its details.</p>;
  }

  return (
    <article className="jira-details">
      <div className="jira-details-header">
        <div className="jira-details-title">
          <h2>{issue.jiraId}</h2>
          <a href={issue.link} target="_blank" rel="noreferrer" className="jira-link-badge">
            Open in Jira &rarr;
          </a>
        </div>
        <p className="jira-description">{issue.description || 'No description available.'}</p>
      </div>

      {issue.seeds.length > 0 && (
        <section className="jira-section">
          <h3>Seeds ({issue.seeds.length})</h3>
          <ul className="jira-entry-list">
            {issue.seeds.map((seed) => (
              <li key={seed.id}>
                <div className="jira-entry-meta">
                  <span className={`badge jira-type-badge jira-type-${seed.type?.toLowerCase()}`}>
                    {seed.type}
                  </span>
                  {seed.seedRef && <span className="jira-entry-ref">{seed.seedRef}</span>}
                </div>
                <EntryContent content={seed.content} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {issue.tables.length > 0 && (
        <section className="jira-section">
          <h3>Tables ({issue.tables.length})</h3>
          <ul className="jira-entry-list">
            {issue.tables.map((table) => (
              <li key={table.id}>
                <div className="jira-entry-meta">
                  <span className={`badge jira-type-badge jira-type-${table.type?.toLowerCase()}`}>
                    {table.type}
                  </span>
                  {table.tableName && <strong>{table.tableName}</strong>}
                  {table.primaryKeyField && (
                    <span className="jira-entry-ref">
                      {table.primaryKeyField} = {table.primaryKeyValue}
                    </span>
                  )}
                </div>
                {table.nameDescription && <p>{table.nameDescription}</p>}
                <EntryContent content={table.content} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {issue.seeds.length === 0 && issue.tables.length === 0 && (
        <p className="jira-no-data">No related seed or table data for this issue.</p>
      )}
    </article>
  );
}

export default JiraIssueDetails;

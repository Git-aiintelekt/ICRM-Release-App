import { ApiState, HealthPanel, JiraKeyLinks, NotConfigured, Warnings } from '../components/IntegrationUI';
import { formatDateTime, formatNumber, useApi } from '../lib/integrationData';
import { Link } from '../lib/router';
import { getDashboard } from '../services/integrationsService';

// Every number comes from /api/integrations/dashboard (one request; the server reuses cached Jira/Bitbucket answers).
function StatCard({ label, value, hint, to, tone }) {
  const body = (
    <>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{formatNumber(value)}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </>
  );
  return to ? (
    <Link to={to} className={`stat-card stat-${tone ?? 'neutral'}`}>
      {body}
    </Link>
  ) : (
    <div className={`stat-card stat-${tone ?? 'neutral'}`}>{body}</div>
  );
}

function doneHint(group) {
  if (!group) {
    return null;
  }
  // A figure is null when no status of that kind is configured (e.g. projects that only use Done): left out.
  const parts = [];
  if (group.resolved != null) parts.push(`${formatNumber(group.resolved)} resolved`);
  if (group.closed != null) parts.push(`${formatNumber(group.closed)} closed`);
  if (group.doneOther) {
    parts.push(`${formatNumber(group.doneOther)} other done`);
  }
  return parts.join(' · ');
}

function Section({ section, service, children }) {
  if (section?.notConfigured) {
    return <NotConfigured service={service} />;
  }
  if (section?.error) {
    return (
      <p className="form-error" role="alert">
        {section.error}
      </p>
    );
  }
  return section?.data ? children(section.data) : null;
}

function bugLink(bugTypes, state) {
  const params = new URLSearchParams(state ? { state } : {});
  bugTypes.forEach((type) => params.append('type', type));
  return `/jira?${params}`;
}

function TicketCards({ summary }) {
  const { issues, bugs } = summary;
  const bugTypes = summary.definitions.bugTypes;
  return (
    <>
      <div className="stat-grid">
        <StatCard label="Total tickets" value={issues.total} to="/jira" />
        <StatCard label="Open tickets" value={issues.open} to="/jira?state=open" tone="open" hint="Not in a Done status" />
        <StatCard label="Resolved / closed" value={issues.done} to="/jira?state=done" tone="done" hint={doneHint(issues)} />
        <StatCard label="Total bugs" value={bugs?.total} to={bugs ? bugLink(bugTypes) : undefined} />
        <StatCard label="Open bugs" value={bugs?.open} to={bugs ? bugLink(bugTypes, 'open') : undefined} tone="open" />
        <StatCard
          label="Resolved / closed bugs"
          value={bugs?.done}
          to={bugs ? bugLink(bugTypes, 'done') : undefined}
          tone="done"
          hint={doneHint(bugs)}
        />
      </div>
      {!bugs && <p className="cell-sub">Bug counts need a bug issue type that exists in these projects (JIRA_BUG_ISSUE_TYPES).</p>}
      <p className="cell-sub dashboard-footnote">
        Projects {summary.projects.join(', ')}. Resolved = {summary.definitions.resolvedStatuses.join(', ') || 'none'}; closed ={' '}
        {summary.definitions.closedStatuses.join(', ') || 'none (these projects have no separate Closed status)'}; bugs = {summary.definitions.bugTypes.join(', ') || 'none'}. Counts
        from Jira's count API, which can lag a few seconds behind very recent changes.
      </p>
      <Warnings items={summary.warnings} />
    </>
  );
}

function ReleaseTable({ releases }) {
  if (!releases.rows.length) {
    return <p className="status-text">Jira has no fix versions in these projects.</p>;
  }
  const hints = Object.entries(releases.candidates);
  // Columns for a status kind that isn't configured would only ever show 0.
  const showResolved = releases.definitions.resolvedStatuses.length > 0;
  const showClosed = releases.definitions.closedStatuses.length > 0;
  return (
    <>
      {!releases.mapped && (
        <p className="settings-hint">
          Rows are Jira fix versions, named exactly as in Jira. They are not linked to this app's release versions until an
          administrator sets <code>JIRA_FIX_VERSION_MAP</code>.
        </p>
      )}
      <div className="review-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">{releases.mapped ? 'Release' : 'Jira fix version'}</th>
              <th scope="col">Total</th>
              <th scope="col">Open</th>
              {showResolved && <th scope="col">Resolved</th>}
              {showClosed && <th scope="col">Closed</th>}
              <th scope="col">Bugs</th>
              <th scope="col">Open bugs</th>
            </tr>
          </thead>
          <tbody>
            {releases.rows.map((row) => (
              <tr key={row.label}>
                <td>
                  <strong>{row.label}</strong>
                  {releases.mapped && <span className="cell-sub">{row.fixVersions.join(', ') || 'no matching fix version'}</span>}
                  {!releases.mapped && row.project && (
                    <span className="cell-sub">
                      {row.project}
                      {row.releaseDate ? ` · ${row.releaseDate}` : ''}
                      {row.released ? ' · released' : ' · unreleased'}
                    </span>
                  )}
                </td>
                <td>{formatNumber(row.counts.total)}</td>
                <td>{formatNumber(row.counts.open)}</td>
                {showResolved && <td>{formatNumber(row.counts.resolved)}</td>}
                {showClosed && <td>{formatNumber(row.counts.closed)}</td>}
                <td>{formatNumber(row.counts.bugs)}</td>
                <td>{formatNumber(row.counts.openBugs)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hints.length > 0 && (
        <details className="format-guide">
          <summary>Possible matches with this app's versions (unconfirmed)</summary>
          <ul className="plain-list">
            {hints.map(([version, names]) => (
              <li key={version}>
                {version}: {names.join(', ')}
              </li>
            ))}
          </ul>
        </details>
      )}
      <Warnings items={releases.warnings} />
    </>
  );
}

function CommitList({ commits }) {
  if (!commits.values.length) {
    return <p className="status-text">No commits found.</p>;
  }
  return (
    <>
      <ul className="activity-list">
        {commits.values.map((commit) => (
          <li key={commit.hash}>
            <a href={commit.url} target="_blank" rel="noreferrer" className="mono">
              {commit.shortHash}
            </a>
            <span className="activity-title">{commit.subject}</span>
            <span className="cell-sub">
              {commit.author ?? 'Unknown author'} · {formatDateTime(commit.date)}
            </span>
            <JiraKeyLinks issues={commit.jiraIssues} />
          </li>
        ))}
      </ul>
      {commits.jiraWarning && <p className="cell-sub">{commits.jiraWarning}</p>}
    </>
  );
}

function PullRequestList({ pullRequests }) {
  if (!pullRequests.values.length) {
    return <p className="status-text">No pull requests found.</p>;
  }
  return (
    <ul className="activity-list">
      {pullRequests.values.map((pr) => (
        <li key={pr.id}>
          <a href={pr.url} target="_blank" rel="noreferrer">
            #{pr.id}
          </a>
          <span className="activity-title">{pr.title}</span>
          <span className="cell-sub">
            <span className={`pr-state pr-${(pr.state ?? '').toLowerCase()}`}>{pr.state}</span> {pr.author} · {pr.sourceBranch} →{' '}
            {pr.destinationBranch} · updated {formatDateTime(pr.updatedOn)}
          </span>
          <JiraKeyLinks issues={pr.jiraIssues} />
        </li>
      ))}
    </ul>
  );
}

// The fix versions / branches an admin limited the screens to (Settings → Integrations).
function ScopeNote({ names, what }) {
  if (!names?.length) {
    return null;
  }
  return (
    <p className="settings-hint">
      {what}: <strong>{names.join(', ')}</strong> (set in Settings → Integrations).
    </p>
  );
}

function branchText(data) {
  const branches = data.status.scope.branches[data.repository] ?? [];
  return branches.length ? `${branches.length === 1 ? 'branch' : 'branches'} ${branches.join(', ')}` : 'all branches';
}

function DashboardPage() {
  const dashboard = useApi(() => getDashboard(), []);

  return (
    <div className="page dashboard-page">
      <section className="page-hero">
        <p className="eyebrow">Overview</p>
        <h1>Dashboard</h1>
        <p className="page-lede">Live ticket counts from Jira and recent activity from Bitbucket.</p>
      </section>

      <ApiState state={dashboard} loadingText="Loading live data from Jira and Bitbucket…">
        {(data) => (
          <>
            <section className="dashboard-section">
              <div className="section-head">
                <h2>Jira tickets</h2>
                <button type="button" className="button button-ghost" onClick={dashboard.reload} disabled={dashboard.loading}>
                  {dashboard.loading ? 'Reloading…' : 'Reload'}
                </button>
              </div>
              <ScopeNote
                names={data.status.scope.fixVersions}
                what="Counts cover only these Jira fix versions"
              />
              <Section section={data.jiraSummary} service="jira">
                {(summary) => <TicketCards summary={summary} />}
              </Section>
            </section>

            <section className="dashboard-section">
              <h2>Release-wise tickets</h2>
              <ScopeNote names={data.status.scope.fixVersions} what="Only these fix versions" />
              <Section section={data.releases} service="jira">
                {(releases) => <ReleaseTable releases={releases} />}
              </Section>
            </section>

            <div className="dashboard-columns">
              <section className="dashboard-section">
                <div className="section-head">
                  <h2>Recent commits</h2>
                  {data.repository && <Link to="/commits">All commits</Link>}
                </div>
                {data.repository && <p className="cell-sub">{data.repository}, {branchText(data)}</p>}
                <Section section={data.commits} service="bitbucket">
                  {(commits) => <CommitList commits={commits} />}
                </Section>
              </section>
              <section className="dashboard-section">
                <div className="section-head">
                  <h2>Recent pull requests</h2>
                  {data.repository && <Link to="/commits?tab=pullrequests">All pull requests</Link>}
                </div>
                {data.repository && <p className="cell-sub">{data.repository}, {branchText(data)}</p>}
                <Section section={data.pullRequests} service="bitbucket">
                  {(prs) => <PullRequestList pullRequests={prs} />}
                </Section>
              </section>
            </div>

            <section className="dashboard-section">
              <h2>Integration health</h2>
              <HealthPanel status={data.status} />
            </section>
          </>
        )}
      </ApiState>
    </div>
  );
}

export default DashboardPage;

import { ApiState, HealthPanel, NotConfigured, Warnings } from '../components/IntegrationUI';
import { formatNumber, useApi } from '../lib/integrationData';
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

// Published releases drafted from release/ branches: their Jira issues, with the live status from Jira.
function ReleaseBranchTable({ rows }) {
  if (!rows.length) {
    return (
      <p className="status-text">
        None yet. Publish a version from Import / Export → Draft from Bitbucket to see its Jira counts here.
      </p>
    );
  }
  return (
    <div className="review-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Release</th>
            <th scope="col">Jira issues</th>
            <th scope="col">Done</th>
            <th scope="col">Open</th>
            <th scope="col">Bugs</th>
            <th scope="col">Open bugs</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.version}>
              <td>
                <strong>{row.version}</strong>
                <span className="cell-sub">
                  {[...new Set(row.branches.map((b) => b.branch))].join(', ')} ·{' '}
                  {row.branches.map((b) => b.repository).join(', ')}
                </span>
              </td>
              <td>
                {formatNumber(row.counts.total)}
                {row.counts.notFound > 0 && (
                  <span className="cell-sub">{formatNumber(row.counts.notFound)} not visible in Jira</span>
                )}
              </td>
              <td>{formatNumber(row.counts.done)}</td>
              <td>{formatNumber(row.counts.open)}</td>
              <td>{formatNumber(row.counts.bugs)}</td>
              <td>{formatNumber(row.counts.openBugs)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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

function DashboardPage() {
  const dashboard = useApi(() => getDashboard(), []);

  return (
    <div className="page dashboard-page">
      <section className="page-hero">
        <p className="eyebrow">Overview</p>
        <h1>Dashboard</h1>
        <p className="page-lede">Live ticket counts from Jira, overall and per published release branch.</p>
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
              <h2>Published release branches</h2>
              <p className="cell-sub">Jira issues in each published release, from its release branch&apos;s commits.</p>
              <Section section={data.releaseBranches} service="jira">
                {(rows) => <ReleaseBranchTable rows={rows} />}
              </Section>
            </section>

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

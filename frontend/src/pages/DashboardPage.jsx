import { useState } from 'react';
import { ApiState, HealthPanel, HeroStats, NotConfigured, serviceHealth } from '../components/IntegrationUI';
import { formatNumber, useApi } from '../lib/integrationData';
import { getDashboard } from '../services/integrationsService';

// Every number comes from /api/integrations/dashboard (one request; the server reuses cached Jira answers).
function StatCard({ label, value, hint, tone }) {
  return (
    <div className={`stat-card stat-${tone ?? 'neutral'}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{formatNumber(value)}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
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

const NO_COUNTS = { total: 0, open: 0, done: 0, resolved: null, closed: null, doneOther: 0 };
const branchNames = (row) => [...new Set(row.branches.map((b) => b.branch))].join(', ');

function TicketCards({ issues, bugs }) {
  return (
    <div className="stat-grid">
      <StatCard label="Total tickets" value={issues.total} />
      <StatCard label="Open tickets" value={issues.open} tone="open" hint="Not in a Done status" />
      <StatCard label="Resolved / closed" value={issues.done} tone="done" hint={doneHint(issues)} />
      <StatCard label="Total bugs" value={bugs.total} />
      <StatCard label="Open bugs" value={bugs.open} tone="open" />
      <StatCard label="Resolved / closed bugs" value={bugs.done} tone="done" hint={doneHint(bugs)} />
    </div>
  );
}

// The counts of one published release: its Jira issues are the ones found in its release branch's commits. Before
// any release branch is published, every count is 0.
function ReleaseTickets({ rows }) {
  const [version, setVersion] = useState(rows[0]?.version ?? '');
  const row = rows.find((r) => r.version === version) ?? rows[0];

  if (!row) {
    return (
      <>
        <TicketCards issues={NO_COUNTS} bugs={NO_COUNTS} />
        <p className="cell-sub dashboard-footnote">
          No release branch is published yet. Publish a version from Import / Export → Draft from Bitbucket and these
          counts show its Jira issues.
        </p>
      </>
    );
  }
  return (
    <>
      <label className="field dashboard-release-picker">
        <span>Release</span>
        <select className="input" value={row.version} onChange={(event) => setVersion(event.target.value)}>
          {rows.map((r) => (
            <option key={r.version} value={r.version}>
              {r.version} ({branchNames(r)})
            </option>
          ))}
        </select>
      </label>
      <TicketCards issues={row.issues} bugs={row.bugs} />
      <p className="cell-sub dashboard-footnote">
        The Jira issues found in the commits of {branchNames(row)} ({row.branches.map((b) => b.repository).join(', ')}),
        with their live status in Jira.
        {row.notFound > 0 && ` ${formatNumber(row.notFound)} of them aren't visible to the Jira account.`}
      </p>
    </>
  );
}

// Every published release side by side.
function ReleaseBranchTable({ rows }) {
  return (
    <div className="review-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Release</th>
            <th scope="col">Tickets</th>
            <th scope="col">Open</th>
            <th scope="col">Resolved / closed</th>
            <th scope="col">Bugs</th>
            <th scope="col">Open bugs</th>
            <th scope="col">Resolved / closed bugs</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.version}>
              <td>
                <strong>{row.version}</strong>
                <span className="cell-sub">{branchNames(row)}</span>
              </td>
              <td>{formatNumber(row.issues.total)}</td>
              <td>{formatNumber(row.issues.open)}</td>
              <td>{formatNumber(row.issues.done)}</td>
              <td>{formatNumber(row.bugs.total)}</td>
              <td>{formatNumber(row.bugs.open)}</td>
              <td>{formatNumber(row.bugs.done)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Beside the title: how many releases are published, the newest one's open work, and how many integrations are connected.
function dashboardStats(data) {
  const rows = data.releaseBranches?.data ?? [];
  const latest = rows[0];
  const services = [data.status.jira, data.status.bitbucket];
  const connected = services.filter((s) => serviceHealth(s).healthy).length;
  return [
    { label: 'Releases', value: formatNumber(rows.length), sub: 'published' },
    latest
      ? { label: 'Latest', value: latest.version, sub: `${formatNumber(latest.issues.open)} open · ${formatNumber(latest.bugs.open)} open bugs` }
      : { label: 'Latest', value: '—', sub: 'none published yet' },
    { label: 'Integrations', value: `${connected} / ${services.length}`, sub: 'connected' },
  ];
}

function DashboardPage() {
  const dashboard = useApi(() => getDashboard(), []);

  return (
    <div className="page dashboard-page">
      <section className="page-hero page-hero-split">
        <div className="hero-text">
          <p className="eyebrow">Overview</p>
          <h1>Dashboard</h1>
          <p className="page-lede">Live Jira ticket counts of the published release branches.</p>
        </div>
        {dashboard.data && <HeroStats items={dashboardStats(dashboard.data)} />}
      </section>

      <ApiState state={dashboard} loadingText="Loading live data from Jira…">
        {(data) => (
          <>
            <section className="dashboard-section">
              <div className="section-head">
                <h2>Jira tickets</h2>
                <button type="button" className="button button-ghost" onClick={dashboard.reload} disabled={dashboard.loading}>
                  {dashboard.loading ? 'Reloading…' : 'Reload'}
                </button>
              </div>
              <Section section={data.releaseBranches} service="jira">
                {(rows) => <ReleaseTickets rows={rows} />}
              </Section>
            </section>

            {data.releaseBranches?.data?.length > 1 && (
              <section className="dashboard-section">
                <h2>Published release branches</h2>
                <ReleaseBranchTable rows={data.releaseBranches.data} />
              </section>
            )}

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

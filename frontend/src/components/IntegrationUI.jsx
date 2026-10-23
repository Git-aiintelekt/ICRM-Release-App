import { useAuth } from '../context/AuthContext';
import { formatDateTime } from '../lib/integrationData';
import { Link } from '../lib/router';

// Jira status, coloured by Jira's status category: to do (new), in progress (indeterminate), done.
export function JiraStatusBadge({ status, category }) {
  if (!status) {
    return <span className="status-badge status-unknown">Unknown</span>;
  }
  return <span className={`status-badge status-${category || 'unknown'}`}>{status}</span>;
}

// Jira keys found in a commit or PR, each with the live status Jira reports (never inferred from the commit).
export function JiraKeyLinks({ issues }) {
  if (!issues?.length) {
    return <span className="cell-sub">—</span>;
  }
  return (
    <ul className="jira-key-list">
      {issues.map((issue) => (
        <li key={issue.key}>
          {issue.url ? (
            <a className="jira-chip" href={issue.url} target="_blank" rel="noreferrer" title={issue.summary ?? undefined}>
              {issue.key}
            </a>
          ) : (
            <span className="jira-chip">{issue.key}</span>
          )}
          {issue.notFound ? (
            <span className="status-badge status-unknown" title="Jira has no such issue, or this account can't see it">
              Not found
            </span>
          ) : (
            <JiraStatusBadge status={issue.status} category={issue.statusCategory} />
          )}
        </li>
      ))}
    </ul>
  );
}

const SERVICE_NAMES = { jira: 'Jira', bitbucket: 'Bitbucket' };

// Shown instead of data when an integration has no credentials yet (503 from the API).
export function NotConfigured({ service, message }) {
  const { user } = useAuth();
  return (
    <div className="notice-card integration-notice">
      <h2>{SERVICE_NAMES[service] ?? service} is not connected yet</h2>
      <p>{message || `The server has no ${SERVICE_NAMES[service] ?? service} credentials configured.`}</p>
      {user?.isAdmin ? (
        <Link to="/settings#integrations" className="button button-secondary">
          See integration settings
        </Link>
      ) : (
        <p className="cell-sub">Ask an administrator to configure it.</p>
      )}
    </div>
  );
}

// Loading / error / not configured / empty, then the content.
export function ApiState({ state, service, loadingText = 'Loading…', isEmpty, emptyText = 'Nothing to show.', children }) {
  if (state.loading && !state.data) {
    return <p className="status-text">{loadingText}</p>;
  }
  if (state.error) {
    if (state.status === 503 && /not configured/i.test(state.error)) {
      return <NotConfigured service={service} message={state.error} />;
    }
    return (
      <div className="form-error integration-error" role="alert">
        <span>{state.error}</span>
        <button type="button" className="link-button" onClick={state.reload}>
          Try again
        </button>
      </div>
    );
  }
  if (state.data && isEmpty?.(state.data)) {
    return <p className="status-text">{emptyText}</p>;
  }
  return state.data ? children(state.data) : null;
}

export function Warnings({ items }) {
  if (!items?.length) {
    return null;
  }
  return (
    <ul className="warning-list integration-warnings">
      {items.map((warning) => (
        <li key={warning}>{warning}</li>
      ))}
    </ul>
  );
}

export function Pager({ page, hasNext, onChange, label }) {
  if (page <= 1 && !hasNext) {
    return null;
  }
  return (
    <div className="pager" aria-label={label}>
      <button type="button" className="button button-secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        Previous
      </button>
      <span className="cell-sub">Page {page}</span>
      <button type="button" className="button button-secondary" disabled={!hasNext} onClick={() => onChange(page + 1)}>
        Next
      </button>
    </div>
  );
}

// Connection state per service: configured, last successful sync, last error (from /api/integrations/status).
// One service's connection state, from its entry in /api/integrations/status.
export function serviceHealth(s) {
  const healthy = Boolean(s.configured && s.lastSuccessAt && (!s.lastErrorAt || s.lastErrorAt < s.lastSuccessAt));
  const state = !s.configured ? 'Not configured' : healthy ? 'Connected' : s.lastErrorAt ? 'Error' : 'Not checked yet';
  const tone = !s.configured ? 'unknown' : healthy ? 'done' : s.lastErrorAt ? 'error' : 'new';
  return { healthy, state, tone };
}

// Summary tiles beside a page title (inside .page-hero-split). Each item: { label, value, sub?, text?, wide? };
// `text` marks a word rather than a number, shown smaller.
export function HeroStats({ items }) {
  return (
    <dl className="hero-stats">
      {items.map((item) => (
        <div key={item.label} className={item.wide ? 'hero-stat hero-stat-wide' : 'hero-stat'}>
          <dt>{item.label}</dt>
          <dd className={item.text ? 'hero-stat-text' : undefined}>
            {item.value}
            {item.sub && <span className="hero-stat-sub">{item.sub}</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function HealthPanel({ status }) {
  const services = [
    ['Jira', status.jira, status.jira.projectKeys?.join(', ')],
    ['Bitbucket', status.bitbucket, status.bitbucket.workspace && `${status.bitbucket.workspace} / ${status.bitbucket.repositories.join(', ')}`],
  ];
  return (
    <div className="health-grid">
      {services.map(([name, s, scope]) => {
        const { state, tone } = serviceHealth(s);
        return (
          <div key={name} className="health-card">
            <div className="health-head">
              <strong>{name}</strong>
              <span className={`status-badge status-${tone}`}>{state}</span>
            </div>
            {scope && <span className="cell-sub">{scope}</span>}
            <span className="cell-sub">Last successful sync: {formatDateTime(s.lastSuccessAt)}</span>
            {s.lastErrorAt && (
              <span className="cell-sub status-error">
                Last error {formatDateTime(s.lastErrorAt)}: {s.lastError}
              </span>
            )}
            {!s.configured && <span className="cell-sub">Missing: {s.missingSettings.join(', ')}</span>}
          </div>
        );
      })}
    </div>
  );
}

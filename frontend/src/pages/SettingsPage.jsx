import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { downloadAuditLogCsv, getAuditLog, getUsers, updateUserAccess } from '../services/adminSettingsService';
import IntegrationsTab from '../components/IntegrationsTab';
import { useLocation } from '../lib/router';

const ACTION_LABELS = {
  LOGIN: 'Signed in',
  LOGIN_FAILED: 'Failed sign-in',
  REGISTER: 'Created account',
  PASSWORD_RESET_REQUEST: 'Asked for password reset',
  PASSWORD_RESET: 'Reset password',
  JIRA_LIST_VIEW: 'Opened Jira list',
  JIRA_ISSUE_VIEW: 'Viewed Jira issue',
  JIRA_ACCESS_DENIED: 'Jira access denied',
  RELEASE_PUBLISH: 'Published release',
  RELEASE_EDIT: 'Edited release',
  RELEASE_DELETE: 'Deleted release',
  ACCESS_CHANGE: 'Changed access',
  OFBIZ_PACKAGE: 'Generated OFBiz package',
  INTEGRATION_REFRESH: 'Refreshed integrations',
  INTEGRATION_SCOPE: 'Changed integration scope',
  LOGOUT_EVERYWHERE: 'Signed out everywhere',
  PASSWORD_CHANGE: 'Changed password',
  INTEGRATION_SETTINGS: 'Changed connection settings',
};

const ACTION_FILTERS = [
  { value: '', label: 'All activity' },
  { value: 'JIRA', label: 'Jira views' },
  { value: 'JIRA_ISSUE_VIEW', label: 'Jira issues viewed' },
  { value: 'JIRA_ACCESS_DENIED', label: 'Jira access denied' },
  { value: 'LOGIN', label: 'Sign-ins' },
  { value: 'LOGIN_FAILED', label: 'Failed sign-ins' },
  { value: 'REGISTER', label: 'New accounts' },
  { value: 'PASSWORD_RESET_REQUEST', label: 'Password reset requests' },
  { value: 'PASSWORD_RESET', label: 'Password resets' },
  { value: 'ACCESS_CHANGE', label: 'Access changes' },
  { value: 'RELEASE_PUBLISH', label: 'Release uploads' },
  { value: 'RELEASE_EDIT', label: 'Release edits' },
  { value: 'RELEASE_DELETE', label: 'Deleted releases' },
  { value: 'OFBIZ_PACKAGE', label: 'OFBiz packages' },
  { value: 'INTEGRATION_REFRESH', label: 'Integration refreshes' },
  { value: 'INTEGRATION_SCOPE', label: 'Integration scope changes' },
  { value: 'LOGOUT_EVERYWHERE', label: 'Signed out everywhere' },
  { value: 'PASSWORD_CHANGE', label: 'Password changes' },
  { value: 'INTEGRATION_SETTINGS', label: 'Connection settings changes' },
];

const PAGE_SIZE = 50;

function formatDateTime(value) {
  if (!value) {
    return '—';
  }
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function Toggle({ checked, disabled, label, onChange }) {
  return (
    <label className={disabled ? 'toggle toggle-disabled' : 'toggle'}>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        aria-label={label}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="toggle-track" aria-hidden="true" />
    </label>
  );
}

function UsersTab() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [savingId, setSavingId] = useState(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    getUsers()
      .then(setUsers)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const change = async (target, changes) => {
    setError(null);
    setSavingId(target.id);
    try {
      const updated = await updateUserAccess(target.id, changes);
      setUsers((current) => current.map((u) => (u.id === updated.id ? updated : u)));
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingId(null);
    }
  };

  const q = query.trim().toLowerCase();
  const visible = users.filter(
    (u) =>
      !q ||
      u.username.includes(q) ||
      (u.email ?? '').includes(q) ||
      (u.displayName ?? '').toLowerCase().includes(q)
  );

  if (loading) {
    return <p className="status-text">Loading users…</p>;
  }

  return (
    <>
      <div className="settings-toolbar">
        <input
          type="search"
          className="input search-input"
          placeholder="Search name or email…"
          aria-label="Search users"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <p className="settings-hint">
          Admins can always see Jira issues. Turn on <strong>Jira access</strong> for anyone else who should.
        </p>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="review-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">User</th>
              <th scope="col">Last sign-in</th>
              <th scope="col">Jira issues viewed</th>
              <th scope="col">Jira access</th>
              <th scope="col">Admin</th>
              <th scope="col">Enabled</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((u) => {
              const isMe = u.id === me.id;
              const busy = savingId === u.id;
              return (
                <tr key={u.id} className={u.isEnabled ? undefined : 'row-muted'}>
                  <td>
                    <div className="user-cell">
                      <span className="user-name">
                        {u.displayName || u.username}
                        {isMe && <span className="you-badge">You</span>}
                      </span>
                      <span className="user-login">{u.email ?? `${u.username} (no email set)`}</span>
                    </div>
                  </td>
                  <td>{formatDateTime(u.lastLoginAt)}</td>
                  <td>
                    {u.jiraViewCount > 0 ? (
                      <>
                        {u.jiraViewCount}
                        <span className="cell-sub">last {formatDateTime(u.lastJiraViewAt)}</span>
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    <Toggle
                      checked={u.canViewJira}
                      disabled={busy || u.isAdmin}
                      label={`Jira access for ${u.username}`}
                      onChange={(value) => change(u, { canViewJira: value })}
                    />
                  </td>
                  <td>
                    <Toggle
                      checked={u.isAdmin}
                      disabled={busy || isMe}
                      label={`Admin access for ${u.username}`}
                      onChange={(value) => change(u, { isAdmin: value })}
                    />
                  </td>
                  <td>
                    <Toggle
                      checked={u.isEnabled}
                      disabled={busy || isMe}
                      label={`Account enabled for ${u.username}`}
                      onChange={(value) => change(u, { isEnabled: value })}
                    />
                  </td>
                </tr>
              );
            })}
            {visible.length === 0 && (
              <tr>
                <td colSpan={6} className="empty-cell">
                  No users match your search.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

// Also the Audit Logs page (/audit); /settings#audit keeps working as before.
export function AuditTab() {
  const [filters, setFilters] = useState({ action: '', username: '', from: '', to: '' });
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(
    (offset) => {
      setLoading(true);
      setError(null);
      getAuditLog({ ...filters, username: filters.username.trim(), limit: PAGE_SIZE, offset })
        .then((page) => {
          setTotal(page.total);
          setEntries((current) => (offset === 0 ? page.entries : [...current, ...page.entries]));
        })
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false));
    },
    [filters]
  );

  useEffect(() => {
    const timer = setTimeout(() => load(0), 250);
    return () => clearTimeout(timer);
  }, [load]);

  const setFilter = (key) => (event) => setFilters((current) => ({ ...current, [key]: event.target.value }));

  return (
    <>
      <div className="audit-filters">
        <label className="field">
          <span>Activity</span>
          <select className="input" value={filters.action} onChange={setFilter('action')}>
            {ACTION_FILTERS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>User</span>
          <input className="input" type="search" placeholder="Any email or user" value={filters.username} onChange={setFilter('username')} />
        </label>
        <label className="field">
          <span>From</span>
          <input className="input" type="date" value={filters.from} onChange={setFilter('from')} />
        </label>
        <label className="field">
          <span>To</span>
          <input className="input" type="date" value={filters.to} onChange={setFilter('to')} />
        </label>
      </div>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="audit-summary">
        <p className="settings-hint">
          {total} {total === 1 ? 'event' : 'events'}
        </p>
        <button
          type="button"
          className="button button-secondary"
          disabled={exporting || total === 0}
          onClick={() => {
            setExporting(true);
            setError(null);
            downloadAuditLogCsv({ ...filters, username: filters.username.trim() })
              .catch((err) => setError(err.message))
              .finally(() => setExporting(false));
          }}
        >
          {exporting ? 'Preparing…' : 'Download CSV'}
        </button>
      </div>

      <div className="review-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">When</th>
              <th scope="col">User</th>
              <th scope="col">Activity</th>
              <th scope="col">Details</th>
              <th scope="col">IP address</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td className="nowrap">{formatDateTime(entry.createdAt)}</td>
                <td>{entry.username ?? '—'}</td>
                <td>
                  <span className={`audit-action audit-${entry.action.toLowerCase()}`}>
                    {ACTION_LABELS[entry.action] ?? entry.action}
                  </span>
                </td>
                <td>
                  {entry.target && <span className="audit-target">{entry.target}</span>}
                  {entry.details && <span className="cell-sub">{entry.details}</span>}
                  {!entry.target && !entry.details && '—'}
                </td>
                <td className="mono nowrap" title={entry.userAgent ?? undefined}>
                  {entry.ipAddress ?? '—'}
                </td>
              </tr>
            ))}
            {!loading && entries.length === 0 && (
              <tr>
                <td colSpan={5} className="empty-cell">
                  No activity matches these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {loading && <p className="status-text">Loading activity…</p>}
      {!loading && entries.length < total && (
        <div className="load-more">
          <button type="button" className="button button-secondary" onClick={() => load(entries.length)}>
            Load more
          </button>
        </div>
      )}
    </>
  );
}

const TABS = [
  { id: 'users', label: 'Users & access' },
  { id: 'audit', label: 'Audit log' },
  { id: 'integrations', label: 'Integrations' },
];
const TAB_IDS = TABS.map((item) => item.id);

const tabFromHash = (hash) => (TAB_IDS.includes(hash.slice(1)) ? hash.slice(1) : 'users');

function SettingsPage() {
  const { hash } = useLocation();
  const [tab, setTab] = useState(() => tabFromHash(hash));
  // Follow links to another tab while already on this page (e.g. /settings#integrations).
  const [seenHash, setSeenHash] = useState(hash);
  if (hash !== seenHash) {
    setSeenHash(hash);
    setTab(tabFromHash(hash));
  }

  const selectTab = (id) => {
    setTab(id);
    window.history.replaceState(null, '', id === 'users' ? window.location.pathname : `#${id}`);
  };

  return (
    <div className="page settings-page">
      <section className="page-hero">
        <p className="eyebrow">Admin</p>
        <h1>Settings</h1>
        <p className="page-lede">
          Choose which signed-in users can see Jira issues, review who signed in and what they opened, and check the Jira and
          Bitbucket connections.
        </p>
      </section>

      <div className="tabs" role="tablist" aria-label="Settings sections">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls={`panel-${item.id}`}
            className={tab === item.id ? 'tab active' : 'tab'}
            onClick={() => selectTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="tab-panel">
        {tab === 'users' && <UsersTab />}
        {tab === 'audit' && <AuditTab />}
        {tab === 'integrations' && <IntegrationsTab />}
      </div>
    </div>
  );
}

export default SettingsPage;

import { useEffect, useMemo, useState } from 'react';
import { ApiState, JiraStatusBadge, Warnings } from './IntegrationUI';
import { formatDateTime, formatNumber, useApi } from '../lib/integrationData';
import { useAuth } from '../context/AuthContext';
import { addScope, getIntegrationStatus, getJiraFilters, getJiraIssues } from '../services/integrationsService';
import { getReleases } from '../services/releaseService';

const STATES = [
  { value: '', label: 'Any status category' },
  { value: 'open', label: 'Open (not done)' },
  { value: 'done', label: 'Resolved or closed' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
  { value: 'bug', label: 'Bugs (any status)' },
];
const PAGE_SIZE = 25;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

// Each release version's period: its saved start date (else the previous version's release date) until its release
// date (else today, for a version that hasn't shipped).
function releasePeriods(releases, starts) {
  const ordered = [...releases].sort((a, b) => a.releaseDate.localeCompare(b.releaseDate));
  return ordered
    .map((release, index) => ({
      version: release.version,
      start: starts[release.version] ?? ordered[index - 1]?.releaseDate ?? null,
      saved: Boolean(starts[release.version]),
      end: release.status === 'UPCOMING' ? null : release.releaseDate,
    }))
    .reverse();
}

const shortDate = (iso) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

function initialFilters(search) {
  const params = new URLSearchParams(search);
  return {
    q: params.get('q') ?? '',
    types: params.getAll('type'),
    status: params.get('status') ?? '',
    fixVersion: params.get('fixVersion') ?? '',
    state: STATES.some((s) => s.value === params.get('state')) ? params.get('state') : '',
    period: params.get('period') ?? '',
    createdFrom: DATE_RE.test(params.get('createdFrom') ?? '') ? params.get('createdFrom') : '',
    createdTo: DATE_RE.test(params.get('createdTo') ?? '') ? params.get('createdTo') : '',
  };
}

function useDebounced(value, delay = 350) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

// Live Jira issues: search, filters, and token-based paging (Jira Cloud's search API pages with tokens).
function LiveJiraTickets({ search }) {
  const [filters, setFilters] = useState(() => initialFilters(search));
  const [pages, setPages] = useState({ key: '', tokens: [null], index: 0 });
  const q = useDebounced(filters.q.trim());
  const meta = useApi(() => getJiraFilters(), []);

  const { user } = useAuth();
  const releases = useApi(() => getReleases(), []);
  const status = useApi(() => getIntegrationStatus(), []);
  const periods = useMemo(
    () => releasePeriods(releases.data ?? [], status.data?.scope.versionStarts ?? {}),
    [releases.data, status.data]
  );
  // There's no "any time": with no version or dates picked, the newest version's period applies.
  const auto = !filters.period && !filters.createdFrom && !filters.createdTo ? periods[0] ?? null : null;
  const periodValue = filters.period || auto?.version || '';
  const createdFrom = auto ? auto.start ?? '' : filters.createdFrom;
  const createdTo = auto ? auto.end ?? '' : filters.createdTo;

  const request = useMemo(
    () => ({
      q,
      type: filters.types,
      status: filters.status,
      fixVersion: filters.fixVersion,
      state: filters.state,
      createdFrom,
      createdTo,
    }),
    [q, filters.types, filters.status, filters.fixVersion, filters.state, createdFrom, createdTo]
  );
  const [saving, setSaving] = useState({ busy: false, error: null });
  const choosePeriod = (event) => {
    const name = event.target.value;
    const period = periods.find((p) => p.version === name);
    setFilters((current) => ({
      ...current,
      period: name,
      createdFrom: name ? period?.start ?? '' : '',
      createdTo: name ? period?.end ?? '' : '',
    }));
  };
  // Changing "from" keeps the version, so an admin can save it as that version's start date.
  const setDate = (key) => (event) =>
    setFilters((current) => ({
      ...current,
      period: key === 'createdFrom' ? periodValue : '',
      createdFrom,
      createdTo,
      [key]: event.target.value,
    }));
  const chosen = periods.find((p) => p.version === periodValue);
  const saveStart = async () => {
    setSaving({ busy: true, error: null });
    try {
      await addScope({ kind: 'VERSION_START', repository: chosen.version, value: createdFrom });
      status.reload();
      setSaving({ busy: false, error: null });
    } catch (err) {
      setSaving({ busy: false, error: err.message });
    }
  };
  const requestKey = JSON.stringify(request);
  // New filters start again at page 1.
  const page = pages.key === requestKey ? pages : { key: requestKey, tokens: [null], index: 0 };
  const token = page.tokens[page.index];

  const issues = useApi(() => getJiraIssues({ ...request, pageToken: token, limit: PAGE_SIZE }), [requestKey, token]);

  const setFilter = (key) => (event) => setFilters((current) => ({ ...current, [key]: event.target.value }));
  const goNext = () => {
    const next = issues.data?.nextPageToken;
    if (next) {
      setPages({ key: requestKey, tokens: [...page.tokens.slice(0, page.index + 1), next], index: page.index + 1 });
    }
  };
  const goPrevious = () => setPages({ ...page, index: Math.max(0, page.index - 1) });

  const typeValue = filters.types.length > 1 ? '__several__' : filters.types[0] ?? '';

  return (
    <div className="live-jira">
      <div className="audit-filters jira-filters">
        <label className="field">
          <span>Search</span>
          <input
            className="input"
            type="search"
            placeholder="Key (CS-123) or text"
            value={filters.q}
            maxLength={200}
            onChange={setFilter('q')}
          />
        </label>
        <label className="field">
          <span>Status category</span>
          <select className="input" value={filters.state} onChange={setFilter('state')}>
            {STATES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Issue type</span>
          <select
            className="input"
            value={typeValue}
            onChange={(event) => setFilters((current) => ({ ...current, types: event.target.value ? [event.target.value] : [] }))}
          >
            <option value="">Any type</option>
            {typeValue === '__several__' && <option value="__several__">{filters.types.join(' or ')}</option>}
            {(meta.data?.issueTypes ?? filters.types).map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Status</span>
          <select className="input" value={filters.status} onChange={setFilter('status')}>
            <option value="">Any status</option>
            {(meta.data?.statuses ?? []).map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Fix version</span>
          <select className="input" value={filters.fixVersion} onChange={setFilter('fixVersion')}>
            <option value="">Any fix version</option>
            {(meta.data?.fixVersions ?? []).map((v) => (
              <option key={`${v.project}-${v.name}`} value={v.name}>
                {v.name} ({v.project}
                {v.archived ? ', archived' : ''})
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="audit-filters jira-filters">
        <label className="field">
          <span>Version period (tickets created)</span>
          <select className="input" value={periodValue} onChange={choosePeriod}>
            {!periodValue && (
              <option value="" disabled>
                {periods.length ? 'Custom dates' : 'No release versions yet'}
              </option>
            )}
            {periods.map((period) => (
              <option key={period.version} value={period.version}>
                Version {period.version}: {period.start ? shortDate(period.start) : 'start unknown'} –{' '}
                {period.end ? shortDate(period.end) : 'today'}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Created from</span>
          <input className="input" type="date" value={createdFrom} max={createdTo || undefined} onChange={setDate('createdFrom')} />
        </label>
        <label className="field">
          <span>Created until</span>
          <input className="input" type="date" value={createdTo} min={createdFrom || undefined} onChange={setDate('createdTo')} />
        </label>
        {!auto && periods.length > 0 && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setFilters((current) => ({ ...current, period: '', createdFrom: '', createdTo: '' }))}
          >
            Newest version
          </button>
        )}
      </div>
      {chosen && (
        <p className="settings-hint">
          Tickets created during version {chosen.version}:{' '}
          {chosen.saved ? 'from its saved start date' : chosen.start ? 'from the previous version’s release date' : 'no start date yet'}
          {chosen.end ? ' until its release date.' : ' until today.'}
          {user?.isAdmin && createdFrom && createdFrom !== chosen.start && (
            <>
              {' '}
              <button type="button" className="link-button" disabled={saving.busy} onClick={saveStart}>
                {saving.busy ? 'Saving…' : `Save ${shortDate(createdFrom)} as version ${chosen.version}’s start date`}
              </button>
            </>
          )}
          {user?.isAdmin && !createdFrom && ' Pick “Created from” to set when it started.'}
        </p>
      )}
      {saving.error && <p className="form-error">{saving.error}</p>}
      {meta.error && meta.status !== 503 && <p className="form-error">Filter lists unavailable: {meta.error}</p>}
      <Warnings items={meta.data?.warnings} />

      <ApiState
        state={issues}
        service="jira"
        loadingText="Loading tickets from Jira…"
        isEmpty={(data) => data.issues.length === 0}
        emptyText="No Jira tickets match these filters."
      >
        {(data) => (
          <>
            <p className="settings-hint">
              About {formatNumber(data.total)} {data.total === 1 ? 'ticket' : 'tickets'} · page {page.index + 1}
              {issues.loading && ' · updating…'}
            </p>
            <div className="review-table-wrap">
              <table className="data-table jira-table">
                <thead>
                  <tr>
                    <th scope="col">Key</th>
                    <th scope="col">Summary</th>
                    <th scope="col">Type</th>
                    <th scope="col">Status</th>
                    <th scope="col">Assignee</th>
                    <th scope="col">Priority</th>
                    <th scope="col">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {data.issues.map((issue) => (
                    <tr key={issue.key}>
                      <td className="nowrap">
                        <a className="jira-chip" href={issue.url} target="_blank" rel="noreferrer">
                          {issue.key}
                        </a>
                      </td>
                      <td>
                        {issue.summary ?? '—'}
                        {issue.fixVersions.length > 0 && <span className="cell-sub">Fix version: {issue.fixVersions.join(', ')}</span>}
                      </td>
                      <td>{issue.issueType ?? '—'}</td>
                      <td>
                        <JiraStatusBadge status={issue.status} category={issue.statusCategory} />
                        {issue.resolution && <span className="cell-sub">{issue.resolution}</span>}
                      </td>
                      <td>{issue.assignee ?? 'Unassigned'}</td>
                      <td>{issue.priority ?? '—'}</td>
                      <td className="nowrap">{formatDateTime(issue.updated)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pager">
              <button type="button" className="button button-secondary" disabled={page.index === 0} onClick={goPrevious}>
                Previous
              </button>
              <span className="cell-sub">Page {page.index + 1}</span>
              <button
                type="button"
                className="button button-secondary"
                disabled={data.isLast || !data.nextPageToken}
                onClick={goNext}
              >
                Next
              </button>
            </div>
          </>
        )}
      </ApiState>
    </div>
  );
}

export default LiveJiraTickets;

import { useEffect, useMemo, useState } from 'react';
import { ApiState, JiraStatusBadge, Warnings } from './IntegrationUI';
import { formatDateTime, formatNumber, useApi } from '../lib/integrationData';
import { getJiraFilters, getJiraIssues } from '../services/integrationsService';
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

// Published releases, newest version first (10.10.0 before 10.9.0).
function newestFirst(releases) {
  const parts = (v) => v.split(/[^0-9]+/).filter(Boolean).map(Number);
  return [...releases].sort((a, b) => {
    const [pa, pb] = [parts(a.version), parts(b.version)];
    for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
      if ((pa[i] ?? 0) !== (pb[i] ?? 0)) return (pb[i] ?? 0) - (pa[i] ?? 0);
    }
    return b.version.localeCompare(a.version);
  });
}

function initialFilters(search) {
  const params = new URLSearchParams(search);
  return {
    q: params.get('q') ?? '',
    types: params.getAll('type'),
    status: params.get('status') ?? '',
    fixVersion: params.get('fixVersion') ?? '',
    state: STATES.some((s) => s.value === params.get('state')) ? params.get('state') : '',
    release: params.get('release') ?? '',
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

  const releases = useApi(() => getReleases(), []);
  const versions = useMemo(() => newestFirst(releases.data ?? []).map((r) => r.version), [releases.data]);
  // Always one release: the tickets are the Jira issues found in its release branch's commits (its published Jira
  // IDs), newest release unless another is picked. No release published yet: no tickets.
  const release = versions.includes(filters.release) ? filters.release : versions[0] ?? '';

  const request = useMemo(
    () => ({
      q,
      release,
      type: filters.types,
      status: filters.status,
      fixVersion: filters.fixVersion,
      state: filters.state,
      createdFrom: filters.createdFrom,
      createdTo: filters.createdTo,
    }),
    [q, release, filters.types, filters.status, filters.fixVersion, filters.state, filters.createdFrom, filters.createdTo]
  );
  const requestKey = JSON.stringify(request);
  // New filters start again at page 1.
  const page = pages.key === requestKey ? pages : { key: requestKey, tokens: [null], index: 0 };
  const token = page.tokens[page.index];

  const issues = useApi(
    () => (release ? getJiraIssues({ ...request, pageToken: token, limit: PAGE_SIZE }) : Promise.resolve(null)),
    [requestKey, token]
  );

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
          <span>Release version</span>
          <select className="input" value={release} onChange={setFilter('release')} disabled={!versions.length}>
            {!versions.length && <option value="">{releases.loading ? 'Loading…' : 'No release published yet'}</option>}
            {versions.map((version) => (
              <option key={version} value={version}>
                Version {version}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Created from</span>
          <input
            className="input"
            type="date"
            value={filters.createdFrom}
            max={filters.createdTo || undefined}
            onChange={setFilter('createdFrom')}
          />
        </label>
        <label className="field">
          <span>Created until</span>
          <input
            className="input"
            type="date"
            value={filters.createdTo}
            min={filters.createdFrom || undefined}
            onChange={setFilter('createdTo')}
          />
        </label>
        {(filters.createdFrom || filters.createdTo) && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setFilters((current) => ({ ...current, createdFrom: '', createdTo: '' }))}
          >
            Clear dates
          </button>
        )}
      </div>
      {release ? (
        <p className="settings-hint">
          The Jira issues of version {release}: the ones found in its release branch&apos;s commits.
        </p>
      ) : (
        !releases.loading && (
          <p className="settings-hint">
            No release is published yet. Publish one from Import / Export → Draft from Bitbucket, and its Jira issues
            are listed here.
          </p>
        )
      )}
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
                        {/* Jira's resolution, only when it adds something (it is often named like the status). */}
                        {issue.resolution && issue.resolution.toLowerCase() !== (issue.status ?? '').toLowerCase() && (
                          <span className="cell-sub">Resolution: {issue.resolution}</span>
                        )}
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

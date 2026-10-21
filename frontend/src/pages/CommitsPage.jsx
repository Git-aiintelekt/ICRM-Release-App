import { useState } from 'react';
import { ApiState, JiraKeyLinks, NotConfigured, Pager } from '../components/IntegrationUI';
import { BranchEditor } from '../components/ScopeEditors';
import { useAuth } from '../context/AuthContext';
import { formatDateTime, useApi } from '../lib/integrationData';
import { getCommits, getIntegrationStatus, getPullRequests } from '../services/integrationsService';

const PR_STATES = [
  { value: '', label: 'All states' },
  { value: 'OPEN', label: 'Open' },
  { value: 'MERGED', label: 'Merged' },
  { value: 'DECLINED', label: 'Declined' },
  { value: 'SUPERSEDED', label: 'Superseded' },
];
const BRANCH_RE = /^[A-Za-z0-9._/-]+$/;

const JIRA_NOTE =
  'Jira status is read live from Jira for each key in the message. A commit or merged pull request does not by itself mean the ticket is resolved.';

function Commits({ slug, branch }) {
  const [page, setPage] = useState(1);
  const commits = useApi(() => getCommits(slug, { branch: branch || undefined, page }), [slug, branch, page]);

  return (
    <ApiState
      state={commits}
      service="bitbucket"
      loadingText="Loading commits…"
      isEmpty={(data) => data.values.length === 0}
      emptyText="No commits found."
    >
      {(data) => (
        <>
          {data.jiraWarning && <p className="form-error">{data.jiraWarning}</p>}
          <div className="review-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Commit</th>
                  <th scope="col">Message</th>
                  <th scope="col">Author</th>
                  <th scope="col">Date</th>
                  <th scope="col">Jira tickets (live status)</th>
                </tr>
              </thead>
              <tbody>
                {data.values.map((commit) => (
                  <tr key={commit.hash}>
                    <td>
                      <a href={commit.url} target="_blank" rel="noreferrer" className="mono" title={commit.hash}>
                        {commit.shortHash}
                      </a>
                    </td>
                    <td className="commit-message" title={commit.message}>
                      {commit.subject}
                    </td>
                    <td>{commit.author ?? '—'}</td>
                    <td className="nowrap">{formatDateTime(commit.date)}</td>
                    <td>
                      <JiraKeyLinks issues={commit.jiraIssues} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={page} hasNext={data.hasNext} onChange={setPage} label="Commit pages" />
        </>
      )}
    </ApiState>
  );
}

function PullRequests({ slug, state, branch }) {
  const [page, setPage] = useState(1);
  const prs = useApi(
    () => getPullRequests(slug, { state: state || undefined, branch: branch || undefined, page }),
    [slug, state, branch, page]
  );

  return (
    <ApiState
      state={prs}
      service="bitbucket"
      loadingText="Loading pull requests…"
      isEmpty={(data) => data.values.length === 0}
      emptyText="No pull requests found."
    >
      {(data) => (
        <>
          {data.jiraWarning && <p className="form-error">{data.jiraWarning}</p>}
          <div className="review-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Pull request</th>
                  <th scope="col">State</th>
                  <th scope="col">Branches</th>
                  <th scope="col">Author</th>
                  <th scope="col">Updated</th>
                  <th scope="col">Jira tickets (live status)</th>
                </tr>
              </thead>
              <tbody>
                {data.values.map((pr) => (
                  <tr key={pr.id}>
                    <td>
                      <a href={pr.url} target="_blank" rel="noreferrer">
                        #{pr.id}
                      </a>{' '}
                      {pr.title}
                    </td>
                    <td>
                      <span className={`pr-state pr-${(pr.state ?? '').toLowerCase()}`}>{pr.state}</span>
                    </td>
                    <td className="mono">
                      {pr.sourceBranch} → {pr.destinationBranch}
                    </td>
                    <td>{pr.author ?? '—'}</td>
                    <td className="nowrap">{formatDateTime(pr.updatedOn)}</td>
                    <td>
                      <JiraKeyLinks issues={pr.jiraIssues} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={page} hasNext={data.hasNext} onChange={setPage} label="Pull request pages" />
        </>
      )}
    </ApiState>
  );
}

function CommitsPage({ search = '' }) {
  const params = new URLSearchParams(search);
  const status = useApi(() => getIntegrationStatus(), []);
  const [tab, setTab] = useState(params.get('tab') === 'pullrequests' ? 'pullrequests' : 'commits');
  const [repo, setRepo] = useState(params.get('repo') ?? '');
  const [branchInput, setBranchInput] = useState(params.get('branch') ?? '');
  const [branch, setBranch] = useState(params.get('branch') ?? '');
  const [prState, setPrState] = useState('');
  const [managing, setManaging] = useState(false);
  const { user } = useAuth();

  const repositories = status.data?.bitbucket.repositories ?? [];
  const slug = repositories.includes(repo) ? repo : repositories[0];
  // Branches an admin limited this repository to (Settings → Integrations); empty = every branch.
  const scopeBranches = status.data?.scope.branches[slug] ?? [];
  const scoped = scopeBranches.length > 0;
  const shownBranch = scoped && !scopeBranches.includes(branch) ? '' : branch;
  const branchInvalid = !scoped && branchInput.trim() && !BRANCH_RE.test(branchInput.trim());

  return (
    <div className="page">
      <section className="page-hero">
        <p className="eyebrow">Engineering</p>
        <h1>Commits &amp; pull requests</h1>
        <p className="page-lede">Recent Bitbucket activity, linked to Jira tickets by the keys in commit messages.</p>
      </section>

      <div className="tabs" role="tablist" aria-label="Bitbucket activity">
        {[
          ['commits', 'Commits'],
          ['pullrequests', 'Pull requests'],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? 'tab active' : 'tab'}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      <ApiState state={status} service="bitbucket" loadingText="Loading…">
        {(data) =>
          !data.bitbucket.configured ? (
            <NotConfigured
              service="bitbucket"
              message={`Bitbucket is not configured. Missing: ${data.bitbucket.missingSettings.join(', ')}.`}
            />
          ) : (
            <>
              <div className="audit-filters commits-filters">
                <label className="field">
                  <span>Repository</span>
                  <select
                    className="input"
                    value={slug}
                    onChange={(event) => {
                      setRepo(event.target.value);
                      setBranch('');
                      setBranchInput('');
                    }}
                  >
                    {repositories.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </label>
                {scoped ? (
                  <label className="field">
                    <span>Branch</span>
                    <select className="input" value={shownBranch} onChange={(event) => setBranch(event.target.value)}>
                      <option value="">All added branches ({scopeBranches.length})</option>
                      {scopeBranches.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <form
                    className="field"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (!branchInvalid) setBranch(branchInput.trim());
                    }}
                  >
                    <span>Branch (empty = all branches)</span>
                    <input
                      className="input"
                      type="search"
                      placeholder="e.g. icrm_release_10_9_0"
                      value={branchInput}
                      maxLength={200}
                      onChange={(event) => setBranchInput(event.target.value)}
                      onBlur={() => !branchInvalid && setBranch(branchInput.trim())}
                    />
                  </form>
                )}
                {tab === 'pullrequests' && (
                  <label className="field">
                    <span>State</span>
                    <select className="input" value={prState} onChange={(event) => setPrState(event.target.value)}>
                      {PR_STATES.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
              {branchInvalid && <p className="form-error">Branch names contain only letters, digits, '.', '_', '-' and '/'.</p>}
              {scoped && (
                <p className="settings-hint">
                  Showing only the added branches of {slug}: {scopeBranches.join(', ')}.
                  {tab === 'pullrequests' && ' Pull requests into these branches.'}
                </p>
              )}
              {user?.isAdmin && (
                <button type="button" className="link-button" onClick={() => setManaging((open) => !open)} aria-expanded={managing}>
                  {managing ? 'Done adding / removing branches' : `Add / remove branches of ${slug}`}
                </button>
              )}
              {user?.isAdmin && managing && (
                <div className="edit-panel">
                  <BranchEditor status={data} slug={slug} onChange={status.reload} />
                </div>
              )}
              <p className="settings-hint">{JIRA_NOTE}</p>
              {tab === 'commits' ? (
                <Commits key={`${slug}:${shownBranch}`} slug={slug} branch={shownBranch} />
              ) : (
                <PullRequests key={`${slug}:${prState}:${shownBranch}`} slug={slug} state={prState} branch={shownBranch} />
              )}
            </>
          )
        }
      </ApiState>
    </div>
  );
}

export default CommitsPage;

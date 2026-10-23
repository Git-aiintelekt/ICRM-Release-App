import { useEffect, useState } from 'react';
import { ApiState, HeroStats, Pager } from '../components/IntegrationUI';
import { BranchEditor, RepositoryEditor } from '../components/ScopeEditors';
import { useAuth } from '../context/AuthContext';
import { useProduct } from '../context/ProductContext';
import { formatDateTime, formatNumber, useApi } from '../lib/integrationData';
import { Link } from '../lib/router';
import { getBranches, getIntegrationStatus, getRepositories } from '../services/integrationsService';

function RepositoryCard({ repo, selected, onSelect }) {
  if (repo.error) {
    return (
      <div className="repo-card">
        <strong>{repo.slug}</strong>
        <p className="form-error">{repo.error}</p>
      </div>
    );
  }
  return (
    <button type="button" className={selected ? 'repo-card repo-card-active' : 'repo-card'} onClick={() => onSelect(repo.slug)}>
      <span className="repo-name">{repo.name}</span>
      <span className="cell-sub">{repo.fullName}</span>
      {repo.description && <span className="repo-desc">{repo.description}</span>}
      <span className="repo-meta">
        <span>Main branch: {repo.mainBranch ?? '—'}</span>
        {repo.language && <span>{repo.language}</span>}
        <span>{repo.isPrivate ? 'Private' : 'Public'}</span>
        <span>Updated {formatDateTime(repo.updatedOn)}</span>
      </span>
      {repo.url && (
        <a href={repo.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
          Open in Bitbucket
        </a>
      )}
    </button>
  );
}

function Branches({ slug, status, onScopeChange }) {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(query.trim());
      setPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [query]);

  const branches = useApi(() => getBranches(slug, { q: debounced || undefined, page }), [slug, debounced, page]);
  const invalid = query.trim() && !/^[A-Za-z0-9._/-]+$/.test(query.trim());
  const { user } = useAuth();
  const [managing, setManaging] = useState(false);

  return (
    <section className="dashboard-section">
      <div className="section-head">
        <h2>Branches</h2>
        {user?.isAdmin && status && (
          <button type="button" className="button button-secondary" onClick={() => setManaging((open) => !open)} aria-expanded={managing}>
            {managing ? 'Done' : 'Add / remove branches'}
          </button>
        )}
      </div>
      {managing && status && (
        <div className="edit-panel">
          <p className="field-hint">
            Only the branches added here are shown for {slug}, on this page and on Commits &amp; pull requests. With none
            added, every branch is shown.
          </p>
          <BranchEditor status={status} slug={slug} onChange={() => { onScopeChange(); branches.reload(); }} />
        </div>
      )}
      <input
        type="search"
        className="input search-input"
        placeholder="Search branch name…"
        aria-label="Search branches"
        value={query}
        maxLength={200}
        onChange={(event) => setQuery(event.target.value)}
      />
      {invalid && <p className="form-error">Branch names contain only letters, digits, '.', '_', '-' and '/'.</p>}
      <ApiState
        state={branches}
        service="bitbucket"
        loadingText="Loading branches…"
        isEmpty={(data) => data.values.length === 0}
        emptyText="No branches match. If branches were added in Settings → Integrations, only those are listed."
      >
        {(data) => (
          <>
            {data.scopeBranches?.length > 0 && (
              <p className="settings-hint">
                Showing only the branches added in Settings → Integrations ({data.scopeBranches.length}).
              </p>
            )}
            {data.size != null && <p className="settings-hint">{data.size} branches, most recently updated first</p>}
            <div className="review-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Branch</th>
                    <th scope="col">Last commit</th>
                    <th scope="col">Jira</th>
                    <th scope="col">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {data.values.map((branch) => (
                    <tr key={branch.name}>
                      <td>
                        <a href={branch.url} target="_blank" rel="noreferrer" className="mono">
                          {branch.name}
                        </a>
                        <span className="cell-sub">
                          <Link to={`/commits?repo=${encodeURIComponent(slug)}&branch=${encodeURIComponent(branch.name)}`}>
                            Commits on this branch
                          </Link>
                        </span>
                      </td>
                      <td>
                        {branch.lastCommit ? (
                          <>
                            <a href={branch.lastCommit.url} target="_blank" rel="noreferrer" className="mono">
                              {branch.lastCommit.shortHash}
                            </a>{' '}
                            {branch.lastCommit.subject}
                            <span className="cell-sub">{branch.lastCommit.author}</span>
                          </>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td>
                        {/* Keys only; their live Jira status is shown on the Commits page. */}
                        {branch.lastCommit?.jiraKeys.length
                          ? branch.lastCommit.jiraKeys.map((key) => (
                              <span key={key} className="jira-chip">
                                {key}
                              </span>
                            ))
                          : '—'}
                      </td>
                      <td className="nowrap">{formatDateTime(branch.lastCommit?.date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={page} hasNext={data.hasNext} onChange={setPage} label="Branch pages" />
          </>
        )}
      </ApiState>
    </section>
  );
}

// Beside the title: the linked repositories, the branches they're limited to, and the workspace.
function bitbucketStats(data) {
  const repos = data.repositories.filter((r) => !r.error);
  // The branches added to this product's or client's repositories, each name once: the same release branch in two
  // repositories counts as one.
  const limited = Object.entries(data.branches ?? {}).filter(([, names]) => names.length > 0);
  const branches = new Set(limited.flatMap(([, names]) => names)).size;
  const where = limited.length > 1 ? `in ${formatNumber(limited.length)} repositories` : 'added in Settings';
  return [
    { label: 'Repositories', value: formatNumber(data.repositories.length), sub: `${formatNumber(repos.filter((r) => r.isPrivate).length)} private` },
    { label: 'Branches', value: branches ? formatNumber(branches) : 'All', sub: branches ? where : 'no branch limit' },
    { label: 'Workspace', value: data.workspace ?? '—', text: true, wide: true },
  ];
}

function BitbucketPage() {
  const repos = useApi(() => getRepositories(), []);
  const { user } = useAuth();
  const { product } = useProduct();
  const status = useApi(() => (user?.isAdmin ? getIntegrationStatus() : Promise.resolve(null)), [user?.isAdmin]);
  const [selected, setSelected] = useState(null);
  const [managing, setManaging] = useState(false);
  const listed = repos.data?.repositories ?? [];
  const first = listed.find((r) => !r.error)?.slug ?? null;
  const slug = selected && listed.some((r) => r.slug === selected) ? selected : first;
  const scopeChanged = () => {
    status.reload();
    repos.reload();
  };

  return (
    <div className="page">
      <section className="page-hero page-hero-split">
        <div className="hero-text">
          <p className="eyebrow">Engineering</p>
          <h1>Bitbucket repositories</h1>
          <p className="page-lede">Repositories linked to this app, with their branches.</p>
        </div>
        {repos.data && <HeroStats items={bitbucketStats(repos.data)} />}
      </section>

      {user?.isAdmin && status.data && (
        <section className="dashboard-section">
          <div className="section-head">
            <h2>Linked repositories</h2>
            <button type="button" className="button button-secondary" onClick={() => setManaging((open) => !open)} aria-expanded={managing}>
              {managing ? 'Done' : 'Add / remove repositories'}
            </button>
          </div>
          {managing && (
            <div className="edit-panel">
              <RepositoryEditor status={status.data} product={status.data.product} onChange={scopeChanged} />
            </div>
          )}
        </section>
      )}

      <ApiState state={repos} service="bitbucket" loadingText="Loading repositories from Bitbucket…">
        {(data) => (
          <>
            <p className="settings-hint">Workspace: {data.workspace}</p>
            {data.repositories.length === 0 && (
              <p className="status-text">
                No repositories are linked to {product?.label ?? 'this product'} yet.
                {user?.isAdmin ? ' Use Add / remove repositories above.' : ' An admin can add them.'}
              </p>
            )}
            <div className="repo-grid">
              {data.repositories.map((repo) => (
                <RepositoryCard key={repo.slug} repo={repo} selected={repo.slug === slug} onSelect={setSelected} />
              ))}
            </div>
            {slug && <Branches key={slug} slug={slug} status={status.data} onScopeChange={scopeChanged} />}
          </>
        )}
      </ApiState>
    </div>
  );
}

export default BitbucketPage;

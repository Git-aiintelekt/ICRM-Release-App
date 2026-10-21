import { useState } from 'react';
import { addScope, removeScope } from '../services/integrationsService';

const BRANCH_RE = /^[A-Za-z0-9._/-]+$/;
const SLUG_RE = /^[A-Za-z0-9._-]+$/;

// Runs an add / remove call, then tells the page to reload the integration status.
function useScopeRun(onChange) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const run = async (call) => {
    setBusy(true);
    setError(null);
    try {
      await call();
      onChange();
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

function Chips({ items, busy, emptyText }) {
  if (!items.length) {
    return <p className="cell-sub">{emptyText}</p>;
  }
  return (
    <ul className="scope-chips">
      {items.map((item) => (
        <li key={item.key} className="scope-chip">
          <span className="mono">{item.label}</span>
          <button
            type="button"
            className="scope-chip-remove"
            onClick={item.onRemove}
            disabled={busy}
            aria-label={`Remove ${item.label}`}
            title="Remove"
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}

// Admins: the branches one repository is limited to (or, without `slug`, a repository picker too).
export function BranchEditor({ status, slug, onChange }) {
  const repositories = status.bitbucket.repositories;
  const [picked, setPicked] = useState(repositories[0] ?? '');
  const repo = slug ?? (repositories.includes(picked) ? picked : repositories[0]);
  const [branch, setBranch] = useState('');
  const { busy, error, run } = useScopeRun(onChange);
  const entries = status.scope.entries.filter((e) => e.kind === 'BRANCH');
  const invalid = branch.trim() && !BRANCH_RE.test(branch.trim());

  const add = async (event) => {
    event.preventDefault();
    if (await run(() => addScope({ kind: 'BRANCH', repository: repo, value: branch.trim() }))) setBranch('');
  };
  const chipsFor = (name) =>
    entries
      .filter((e) => e.repository === name)
      .map((e) => ({ key: e.id, label: e.value, onRemove: () => run(() => removeScope(e.id)) }));

  return (
    <div className="scope-editor">
      {(slug ? [slug] : repositories).map((name) => (
        <div key={name} className="scope-repo">
          {!slug && <p className="scope-repo-name mono">{name}</p>}
          <Chips items={chipsFor(name)} busy={busy} emptyText="All branches (none added)" />
        </div>
      ))}
      <form className="scope-add" onSubmit={add}>
        {!slug && (
          <label className="field">
            <span>Repository</span>
            <select className="input" value={repo} onChange={(event) => setPicked(event.target.value)}>
              {repositories.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="field">
          <span>Branch name (exact)</span>
          <input
            className="input mono"
            value={branch}
            onChange={(event) => setBranch(event.target.value)}
            placeholder="e.g. dev_release_18072023"
            maxLength={100}
          />
        </label>
        <button type="submit" className="button button-secondary" disabled={busy || !repo || !branch.trim() || invalid}>
          {busy ? 'Checking…' : 'Add branch'}
        </button>
      </form>
      {invalid && <p className="form-error">Branch names contain only letters, digits, &apos;.&apos;, &apos;_&apos;, &apos;-&apos; and &apos;/&apos;.</p>}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

// Admins: which Bitbucket repositories the app shows. .env ones can be removed (and added back) too.
export function RepositoryEditor({ status, onChange }) {
  const [slug, setSlug] = useState('');
  const { busy, error, run } = useScopeRun(onChange);
  const base = status.bitbucket.baseRepositories ?? [];
  const added = status.scope.entries.filter((e) => e.kind === 'REPOSITORY');
  const invalid = slug.trim() && !SLUG_RE.test(slug.trim());

  const remove = (name) => {
    if (!window.confirm(`Remove ${name} from this app? Its added branches are removed too. The repository itself isn't changed.`)) {
      return;
    }
    const row = added.find((e) => e.value === name);
    run(() => (row ? removeScope(row.id) : addScope({ kind: 'REPOSITORY_HIDDEN', value: name })));
  };
  const add = async (event) => {
    event.preventDefault();
    if (await run(() => addScope({ kind: 'REPOSITORY', value: slug.trim() }))) setSlug('');
  };
  const removed = base.filter((name) => !status.bitbucket.repositories.includes(name));

  return (
    <div className="scope-editor">
      <Chips
        items={status.bitbucket.repositories.map((name) => ({ key: name, label: name, onRemove: () => remove(name) }))}
        busy={busy}
        emptyText="No repositories."
      />
      <form className="scope-add" onSubmit={add}>
        <label className="field">
          <span>Repository slug (from its Bitbucket URL)</span>
          <input
            className="input mono"
            value={slug}
            onChange={(event) => setSlug(event.target.value)}
            placeholder="e.g. icrm-base-framework-master"
            maxLength={100}
            list="removed-repositories"
          />
          <datalist id="removed-repositories">
            {removed.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </label>
        <button type="submit" className="button button-secondary" disabled={busy || !slug.trim() || invalid}>
          {busy ? 'Checking…' : 'Add repository'}
        </button>
      </form>
      {removed.length > 0 && <p className="cell-sub">Removed: {removed.join(', ')}. Add one again to bring it back.</p>}
      {invalid && <p className="form-error">A repository slug contains only letters, digits, &apos;.&apos;, &apos;_&apos; and &apos;-&apos;.</p>}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

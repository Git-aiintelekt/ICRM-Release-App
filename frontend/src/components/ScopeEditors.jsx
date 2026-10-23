import { useState } from 'react';
import { addScope, removeScope } from '../services/integrationsService';
import { linkRepository, unlinkRepository } from '../services/productService';

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

// Admins: which Bitbucket repositories a product shows (status: the integration status as that product sees it).
// Removing one only unlinks it from this product; adding one the app doesn't have yet checks it in Bitbucket first.
export function RepositoryEditor({ status, product, onChange }) {
  const [slug, setSlug] = useState('');
  const { busy, error, run } = useScopeRun(onChange);
  const linked = status.bitbucket.repositories;
  const invalid = slug.trim() && !SLUG_RE.test(slug.trim());

  const remove = (name) => {
    if (!window.confirm(`Remove ${name} from ${product.label}? Other products keep it, and the repository itself isn't changed.`)) {
      return;
    }
    run(() => unlinkRepository(product.id, name));
  };
  const add = async (event) => {
    event.preventDefault();
    if (await run(() => linkRepository(product.id, slug.trim()))) setSlug('');
  };
  // Repositories the app already has (other products', or .env ones) to pick from.
  const others = [...new Set([...(status.bitbucket.allRepositories ?? []), ...(status.bitbucket.baseRepositories ?? [])])].filter(
    (name) => !linked.includes(name)
  );
  const listId = `repositories-for-${product.id}`;

  return (
    <div className="scope-editor">
      <Chips
        items={linked.map((name) => ({ key: name, label: name, onRemove: () => remove(name) }))}
        busy={busy}
        emptyText={`No repositories for ${product.label} yet.`}
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
            list={listId}
          />
          <datalist id={listId}>
            {others.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </label>
        <button type="submit" className="button button-secondary" disabled={busy || !slug.trim() || invalid}>
          {busy ? 'Checking…' : 'Add repository'}
        </button>
      </form>
      {others.length > 0 && <p className="cell-sub">Also in the app: {others.join(', ')}.</p>}
      {invalid && <p className="form-error">A repository slug contains only letters, digits, &apos;.&apos;, &apos;_&apos; and &apos;-&apos;.</p>}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

import { useState } from 'react';
import { useProduct } from '../context/ProductContext';
import { ApiState } from './IntegrationUI';
import { RepositoryEditor } from './ScopeEditors';
import { useApi } from '../lib/integrationData';
import { getIntegrationStatus } from '../services/integrationsService';
import { publicLink } from '../lib/navigation';
import { addProduct, newPublicLink, removeProduct } from '../services/productService';

// The product's or client's public release notes link: copy it, or replace it (the old one then stops working).
function PublicLink({ product }) {
  const { reload } = useProduct();
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);
  if (!product.publicKey) {
    return null;
  }
  const url = publicLink(product.publicKey);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt('Copy the public link:', url);
    }
  };
  const replace = async () => {
    if (!window.confirm(`Make a new public link for ${product.label}? The current link stops working for everyone who has it.`)) {
      return;
    }
    try {
      await newPublicLink(product.id);
      await reload();
    } catch (err) {
      setError(err.message);
    }
  };
  return (
    <div className="public-link">
      <span className="cell-sub">Public link (no sign-in, no Jira numbers)</span>
      <code className="public-link-url" title={url}>
        {url}
      </code>
      <div className="public-link-actions">
        <button type="button" className="button button-secondary" onClick={copy}>
          {copied ? 'Copied' : 'Copy'}
        </button>
        <button type="button" className="button button-ghost" onClick={replace}>
          New link
        </button>
      </div>
      {error && <p className="form-error">{error}</p>}
    </div>
  );
}

// One product or client: its repositories (as its screens show them) and, with onRemove, a way to remove it.
function ProductCard({ product, title, onRemove, busy }) {
  const status = useApi(() => getIntegrationStatus(product.id), [product.id]);
  return (
    <div className="scope-block product-card">
      <div className="section-head">
        <h4>{title}</h4>
        {onRemove && (
          <button type="button" className="button button-ghost" onClick={() => onRemove(product)} disabled={busy}>
            Remove
          </button>
        )}
      </div>
      <PublicLink product={product} />
      <ApiState state={status} service="bitbucket" loadingText="Loading repositories…">
        {(data) => <RepositoryEditor status={data} product={product} onChange={status.reload} />}
      </ApiState>
    </div>
  );
}

// Adds a product (no parentId) or a client of one.
function AddForm({ label, placeholder, busy, onAdd }) {
  const [name, setName] = useState('');
  const submit = async (event) => {
    event.preventDefault();
    if (await onAdd(name.trim())) setName('');
  };
  return (
    <form className="scope-add" onSubmit={submit}>
      <label className="field">
        <span>{label}</span>
        <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder={placeholder} maxLength={50} />
      </label>
      <button type="submit" className="button button-secondary" disabled={busy || !name.trim()}>
        Add
      </button>
    </form>
  );
}

// Settings → Products: the products and their clients in the header's pickers, and the Bitbucket repositories of
// each. A product's own repositories are the ones all its clients share; a client's are only its own.
function ProductsTab() {
  const { products, topProducts, reload } = useProduct();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const run = async (call) => {
    setBusy(true);
    setError(null);
    try {
      await call();
      await reload();
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  };
  const remove = (product) => {
    if (window.confirm(`Remove ${product.label}? Its repository links are removed too; the repositories stay in the app.`)) {
      run(() => removeProduct(product.id));
    }
  };

  return (
    <>
      <p className="settings-hint">
        Everyone picks a product, and a client of it, in the header. Release Notes, the Dashboard, Bitbucket and
        Commits then show only that client&apos;s versions and repositories. &quot;Shared&quot; is the product itself: use
        it when all clients have the same repositories and releases (like iCRM). Anything with release notes can only
        be removed once its versions are deleted.
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <AddForm label="New product" placeholder="e.g. Sales Audit" busy={busy} onAdd={(name) => run(() => addProduct(name))} />

      {topProducts.map((top) => {
        const clients = products.filter((p) => p.parentId === top.id);
        return (
          <section key={top.id} className="product-section">
            <div className="section-head">
              <h3 className="integration-subhead">{top.name}</h3>
              <button type="button" className="button button-ghost" onClick={() => remove(top)} disabled={busy}>
                Remove {top.name}
              </button>
            </div>
            <div className="scope-grid">
              <ProductCard product={top} title="Shared (all clients)" busy={busy} />
              {clients.map((client) => (
                <ProductCard key={client.id} product={client} title={client.name} onRemove={remove} busy={busy} />
              ))}
            </div>
            <AddForm
              label={`New client of ${top.name}`}
              placeholder="e.g. Client A"
              busy={busy}
              onAdd={(name) => run(() => addProduct(name, top.id))}
            />
          </section>
        );
      })}
    </>
  );
}

export default ProductsTab;

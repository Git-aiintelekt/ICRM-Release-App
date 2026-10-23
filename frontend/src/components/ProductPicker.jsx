import { useEffect, useRef, useState } from 'react';
import { useProduct } from '../context/ProductContext';
import { addProduct } from '../services/productService';

// "+" beside a picker (admins): a small form under it that adds a product or a client, then shows it.
function AddButton({ label, text = '+', placeholder, parentId }) {
  const { reload, selectProduct } = useProduct();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const box = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => {
      if (event.type === 'keydown' ? event.key === 'Escape' : !box.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open]);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await addProduct(name.trim(), parentId);
      await reload();
      selectProduct(created.id);
      setName('');
      setOpen(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="picker-add" ref={box}>
      <button
        type="button"
        className={text === '+' ? 'icon-button picker-add-button' : 'button button-ghost picker-add-text'}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={label}
        title={label}
      >
        {text}
      </button>
      {open && (
        <form className="picker-add-form" onSubmit={submit}>
          <label className="field">
            <span>{label}</span>
            <input
              className="input"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={placeholder}
              maxLength={50}
              autoFocus
            />
          </label>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="picker-add-actions">
            <button type="button" className="button button-ghost" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button type="submit" className="button button-primary" disabled={busy || !name.trim()}>
              {busy ? 'Adding…' : 'Add'}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

// Header: which product, and which of its clients, every page shows. canAdd: admins get a "+" beside each.
// "Shared (all clients)" is the product itself: what all its clients have in common (iCRM's clients all use it).
function ProductPicker({ canAdd }) {
  const { topProducts, product, top, clients, selectProduct } = useProduct();
  if (!product || (topProducts.length < 2 && clients.length === 0 && !canAdd)) {
    return null;
  }
  return (
    <div className="product-picker">
      <label className="picker-field">
        <span>Product</span>
        <select className="input" value={top.id} onChange={(event) => selectProduct(Number(event.target.value))}>
          {topProducts.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      {canAdd && <AddButton label="Add a product" placeholder="e.g. Sales Audit" parentId={null} />}

      {clients.length > 0 && (
        <label className="picker-field">
          <span>Client</span>
          <select className="input" value={product.id} onChange={(event) => selectProduct(Number(event.target.value))}>
            <option value={top.id}>Shared (all clients)</option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {canAdd && (
        <AddButton
          key={top.id}
          label={`Add a client to ${top.name}`}
          text={clients.length > 0 ? '+' : '+ Client'}
          placeholder="e.g. Client A"
          parentId={top.id}
        />
      )}
    </div>
  );
}

export default ProductPicker;

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from './AuthContext';
import { setProductHeader } from '../services/apiClient';
import { getProducts } from '../services/productService';

const ProductContext = createContext(null);
const STORAGE_KEY = 'release-manager-product';

// A signed-in link with ?product=2 wins over the product this browser last showed (public links use a key instead).
function savedId() {
  const linked = Number(new URLSearchParams(window.location.search).get('product'));
  if (linked) {
    return linked;
  }
  try {
    return Number(localStorage.getItem(STORAGE_KEY)) || null;
  } catch {
    return null;
  }
}

function saveId(id) {
  try {
    localStorage.setItem(STORAGE_KEY, String(id));
  } catch {
    // Not remembered; the pick still applies until the page is reloaded.
  }
}

const NONE = { products: [], topProducts: [], product: null, top: null, clients: [], failed: false,
  selectProduct: () => {}, reload: () => Promise.resolve([]) };

// The product every page shows (picked in the header, remembered per browser). The pages render only once it is
// known, so their first request already carries it (apiClient's X-Product header).
// The list is for signed-in users only. disabled: the public page, which lists no products (its link's key picks
// one) and sends no X-Product.
export function ProductProvider({ disabled = false, children }) {
  const { user, checking } = useAuth();
  if (disabled || (!checking && !user)) {
    setProductHeader(null);
    return <ProductContext.Provider value={NONE}>{children}</ProductContext.Provider>;
  }
  if (checking) {
    return <p className="status-text page">Loading…</p>;
  }
  // A new sign-in (another user) loads the list again.
  return <SignedInProducts key={user.id}>{children}</SignedInProducts>;
}

function SignedInProducts({ children }) {
  const [products, setProducts] = useState(null);
  const [productId, setProductId] = useState(savedId);
  const [failed, setFailed] = useState(false);

  const load = useCallback(
    () =>
      getProducts()
        .then((list) => {
          setProducts(list);
          setFailed(false);
          return list;
        })
        .catch(() => {
          // Without the list the server picks its first product: the app still works.
          setProducts([]);
          setFailed(true);
          return [];
        }),
    []
  );

  useEffect(() => {
    load();
  }, [load]);

  const value = useMemo(() => {
    const all = products ?? [];
    const topProducts = all.filter((p) => p.parentId == null);
    // The product or client picked; none (or one removed meanwhile): the first product.
    const product = all.find((p) => p.id === productId) ?? topProducts[0] ?? null;
    const top = product?.parentId != null ? (all.find((p) => p.id === product.parentId) ?? product) : product;
    return {
      products: all,
      // product: what every page shows (a product, or one of its clients); top: its product; clients: top's clients.
      topProducts,
      product,
      top,
      clients: top ? all.filter((p) => p.parentId === top.id) : [],
      failed,
      selectProduct: (id) => {
        saveId(id);
        setProductId(id);
      },
      reload: load,
    };
  }, [products, productId, failed, load]);
  // Set during render, before any child effect sends a request.
  setProductHeader(value.product?.id ?? null);

  if (products === null) {
    return <p className="status-text page">Loading…</p>;
  }
  return <ProductContext.Provider value={value}>{children}</ProductContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useProduct() {
  return useContext(ProductContext);
}

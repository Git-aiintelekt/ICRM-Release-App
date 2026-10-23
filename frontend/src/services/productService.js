import { apiFetch } from './apiClient';

// Products (iCRM, IUC, ...) and their clients (parentId = the product): anyone can list them; admins add and
// remove them and link their repositories.
export const getProducts = () => apiFetch('/api/products');
export const addProduct = (name, parentId = null) =>
  apiFetch('/api/admin/products', { method: 'POST', json: { name, parentId } });
export const removeProduct = (id) => apiFetch(`/api/admin/products/${id}`, { method: 'DELETE' });
// A new public link (key); the old one stops working.
export const newPublicLink = (id) => apiFetch(`/api/admin/products/${id}/public-key`, { method: 'POST' });

const repositoriesUrl = (id) => `/api/integrations/products/${id}/repositories`;
// Both return the integration status as that product sees it.
export const linkRepository = (id, repository) =>
  apiFetch(repositoriesUrl(id), { method: 'POST', json: { repository } });
export const unlinkRepository = (id, repository) =>
  apiFetch(`${repositoriesUrl(id)}/${encodeURIComponent(repository)}`, { method: 'DELETE' });

import { ApiError, apiFetch, getToken } from './apiClient';

// Each call returns the whole updated release (except deleteRelease).

export function updateRelease(releaseId, changes) {
  return apiFetch(`/api/admin/releases/${releaseId}`, { method: 'PATCH', json: changes });
}

export function deleteRelease(releaseId) {
  return apiFetch(`/api/admin/releases/${releaseId}`, { method: 'DELETE' });
}

export function addItem(releaseId, item) {
  return apiFetch(`/api/admin/releases/${releaseId}/items`, { method: 'POST', json: item });
}

// Adds every row of a CSV file as a change. Resolves to { release, added, warnings }.
export function importItems(releaseId, file) {
  const body = new FormData();
  body.append('file', file);
  return apiFetch(`/api/admin/releases/${releaseId}/items/import`, { method: 'POST', body });
}

export function updateItem(itemId, item) {
  return apiFetch(`/api/admin/release-items/${itemId}`, { method: 'PATCH', json: item });
}

export function deleteItem(itemId) {
  return apiFetch(`/api/admin/release-items/${itemId}`, { method: 'DELETE' });
}

export function addImage(releaseId, file, { caption, itemId } = {}) {
  const body = new FormData();
  body.append('file', file);
  if (caption) body.append('caption', caption);
  if (itemId) body.append('itemId', String(itemId));
  return apiFetch(`/api/admin/releases/${releaseId}/images`, { method: 'POST', body });
}

export function updateImageCaption(imageId, caption) {
  return apiFetch(`/api/admin/release-images/${imageId}`, { method: 'PATCH', json: { caption } });
}

export function deleteImage(imageId) {
  return apiFetch(`/api/admin/release-images/${imageId}`, { method: 'DELETE' });
}

// One release's notes as an HTML file, emailed as an attachment. Resolves to { delivery, recipients, attachment }.
export function emailReleaseNotes(releaseId, { to, cc, message }) {
  return apiFetch(`/api/admin/releases/${releaseId}/email`, { method: 'POST', json: { to, cc, message } });
}

// The same HTML file, downloaded (fetched with the sign-in token, so a plain link wouldn't work).
export async function downloadReleaseNotes(releaseId) {
  const token = getToken();
  const response = await fetch(`/api/admin/releases/${releaseId}/notes-file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const body = response.headers.get('content-type')?.includes('application/json') ? await response.json() : null;
    throw new ApiError(response.status, body?.detail ?? `Download failed with status ${response.status}`);
  }
  const name = /filename="([^"]+)"/.exec(response.headers.get('content-disposition') ?? '')?.[1] ?? 'release-notes.html';
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

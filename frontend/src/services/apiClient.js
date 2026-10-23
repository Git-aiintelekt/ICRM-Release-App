const TOKEN_KEY = 'icrm-release-token';

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    // Storage unavailable (private mode); the session just won't survive a reload.
  }
}

// The product picked in the header (ProductContext); sent with every call, so the server answers for that product.
let productId = null;

export function setProductHeader(id) {
  productId = id;
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function errorMessage(body, status) {
  if (typeof body?.detail === 'string') {
    return body.detail;
  }
  if (body?.errors) {
    return Object.entries(body.errors)
      .map(([field, msg]) => `${field}: ${msg}`)
      .join('; ');
  }
  return body?.message ?? `Request failed with status ${status}`;
}

export async function apiFetch(url, { json, body, headers, ...options } = {}) {
  const token = getToken();
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(productId != null ? { 'X-Product': String(productId) } : {}),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : body,
  });
  const data = response.headers.get('content-type')?.includes('application/json')
    ? await response.json()
    : null;
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(data, response.status));
  }
  return data;
}

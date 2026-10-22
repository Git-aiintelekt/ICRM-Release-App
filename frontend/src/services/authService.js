import { apiFetch } from './apiClient';

export function login(email, password) {
  return apiFetch('/api/auth/login', { method: 'POST', json: { email, password } });
}

// { registrationOpen, registrationDomains }: whether the sign-in page offers "Create one".
export function getAuthOptions() {
  return apiFetch('/api/auth/options');
}

export function register(email, password, displayName) {
  return apiFetch('/api/auth/register', {
    method: 'POST',
    json: { email, password, displayName: displayName || null },
  });
}

export function getCurrentUser() {
  return apiFetch('/api/auth/me');
}

export function requestPasswordReset(email) {
  return apiFetch('/api/auth/forgot-password', { method: 'POST', json: { email } });
}

export function resetPassword(token, password) {
  return apiFetch('/api/auth/reset-password', { method: 'POST', json: { token, password } });
}

// Signed in: replace the password (required first for the default admin). Returns a new { token, user }.
export function changePassword(currentPassword, newPassword) {
  return apiFetch('/api/auth/change-password', { method: 'POST', json: { currentPassword, newPassword } });
}

// Ends the Django session too (the one Django Admin uses); the sign-in token is dropped by the caller.
export function logout() {
  return apiFetch('/api/auth/logout', { method: 'POST' }).catch(() => null);
}

// Ends every sign-in of this user, on every device; the caller drops this device's token.
export function logoutEverywhere() {
  return apiFetch('/api/auth/logout-all', { method: 'POST' });
}

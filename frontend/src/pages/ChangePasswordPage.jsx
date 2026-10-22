import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

// Shown instead of every page while the signed-in account still has the default password (admin / admin).
function ChangePasswordPage() {
  const { user, changePassword, logout } = useAuth();
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (password.length < 8) {
      setError('Use at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError("The new passwords don't match.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await changePassword(current, password);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  };

  return (
    <div className="page auth-page">
      <div className="auth-card">
        <h1>Choose a new password</h1>
        <p className="auth-lede">
          {user.username} still has the default password. Choose your own before you continue.
        </p>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <label className="field">
            <span>Current password</span>
            <input
              className="input"
              type="password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              autoComplete="current-password"
              required
              autoFocus
            />
          </label>
          <label className="field">
            <span>New password</span>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              required
              minLength={8}
            />
            <small className="field-hint">At least 8 characters.</small>
          </label>
          <label className="field">
            <span>Confirm new password</span>
            <input
              className="input"
              type="password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              autoComplete="new-password"
              required
              minLength={8}
            />
          </label>

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="button button-primary button-block" disabled={submitting}>
            {submitting ? 'Please wait…' : 'Save password'}
          </button>
        </form>

        <p className="auth-switch">
          <button type="button" className="link-button" onClick={logout}>
            Sign out
          </button>
        </p>
      </div>
    </div>
  );
}

export default ChangePasswordPage;

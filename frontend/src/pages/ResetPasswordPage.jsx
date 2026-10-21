import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Link, navigate } from '../lib/router';

function ResetPasswordPage({ search }) {
  const { resetPassword } = useAuth();
  const token = new URLSearchParams(search).get('token');
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
      setError("The passwords don't match.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const user = await resetPassword(token, password);
      navigate(user.isAdmin ? '/upload' : '/', { replace: true });
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  };

  if (!token) {
    return (
      <div className="page auth-page">
        <div className="auth-card">
          <h1>Reset link missing</h1>
          <p className="auth-lede">
            Open the link from your password reset email, or ask for a new one.
          </p>
          <p className="auth-switch">
            <Link to="/forgot-password" className="link-button">Send a new reset link</Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page auth-page">
      <div className="auth-card">
        <h1>Choose a new password</h1>
        <p className="auth-lede">You&apos;ll be signed in once it&apos;s saved.</p>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
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
              autoFocus
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
          Link expired? <Link to="/forgot-password" className="link-button">Send a new one</Link>
        </p>
      </div>
    </div>
  );
}

export default ResetPasswordPage;

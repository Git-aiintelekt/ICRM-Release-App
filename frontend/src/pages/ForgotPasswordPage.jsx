import { useState } from 'react';
import { Link } from '../lib/router';
import { requestPasswordReset } from '../services/authService';

function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sentMessage, setSentMessage] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const { message } = await requestPasswordReset(email);
      setSentMessage(message);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page auth-page">
      <div className="auth-card">
        <h1>Reset your password</h1>
        <p className="auth-lede">
          Enter the email you sign in with. We&apos;ll send you a link to choose a new password.
        </p>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <label className="field">
            <span>Email</span>
            <input
              className="input"
              type="email"
              inputMode="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              placeholder="you@company.com"
              required
              autoFocus
            />
          </label>

          {sentMessage && (
            <p className="form-success" role="status">
              {sentMessage} Check your inbox and spam folder.
            </p>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            className="button button-primary button-block"
            disabled={submitting || !email.trim()}
          >
            {submitting ? 'Please wait…' : sentMessage ? 'Send again' : 'Send reset link'}
          </button>
        </form>

        <p className="auth-switch">
          Remembered it? <Link to="/login" className="link-button">Sign in</Link>
        </p>
      </div>
    </div>
  );
}

export default ForgotPasswordPage;

import { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getAuthOptions } from '../services/authService';
import { Link, navigate } from '../lib/router';

function safeNext(search) {
  const next = new URLSearchParams(search).get('next');
  // Only allow same-site paths, never "//evil.example" or absolute URLs.
  return next && next.startsWith('/') && !next.startsWith('//') && next !== '/login' ? next : null;
}

function LoginPage({ search }) {
  const { login, register } = useAuth();
  const [mode, setMode] = useState('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  // Until the server answers, sign-up stays hidden rather than offered and then refused.
  const [options, setOptions] = useState({ registrationOpen: false, registrationDomains: [] });

  useEffect(() => {
    getAuthOptions()
      .then(setOptions)
      .catch(() => null);
  }, []);

  const isSignIn = mode === 'signin' || !options.registrationOpen;
  const domainsText = options.registrationDomains.map((domain) => `@${domain}`).join(', ');

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const user = isSignIn
        ? await login(email, password)
        : await register(email, password, displayName);
      navigate(safeNext(search) ?? (user.isAdmin ? '/upload' : '/'), { replace: true });
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  };

  return (
    <div className="page auth-page">
      <div className="auth-card">
        <h1>{isSignIn ? 'Sign in' : 'Create an account'}</h1>
        <p className="auth-lede">
          {isSignIn
            ? 'Sign in to see the Jira issues and admin tools your account has access to.'
            : 'New accounts can browse release notes. An administrator grants Jira and admin access.'}
        </p>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {!isSignIn && (
            <label className="field">
              <span>Display name</span>
              <input
                className="input"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                autoComplete="name"
                maxLength={150}
              />
            </label>
          )}
          <label className="field">
            <span>Email</span>
            <input
              className="input"
              type={isSignIn ? 'text' : 'email'}
              inputMode="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete={isSignIn ? 'username' : 'email'}
              placeholder="you@company.com"
              required
              autoFocus
            />
            {!isSignIn && domainsText && <small className="field-hint">Use your {domainsText} address.</small>}
          </label>
          <label className="field">
            <span>Password</span>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={isSignIn ? 'current-password' : 'new-password'}
              required
              minLength={8}
            />
            {!isSignIn && <small className="field-hint">At least 8 characters.</small>}
          </label>
          {isSignIn && (
            <Link to="/forgot-password" className="auth-forgot">
              Forgot password?
            </Link>
          )}

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="button button-primary button-block" disabled={submitting}>
            {submitting ? 'Please wait…' : isSignIn ? 'Sign in' : 'Create account'}
          </button>
        </form>

        {options.registrationOpen ? (
          <p className="auth-switch">
            {isSignIn ? "Don't have an account?" : 'Already have an account?'}{' '}
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setMode(isSignIn ? 'register' : 'signin');
                setError(null);
              }}
            >
              {isSignIn ? 'Create one' : 'Sign in'}
            </button>
          </p>
        ) : (
          <p className="auth-switch">Need an account? Ask an administrator.</p>
        )}
      </div>
    </div>
  );
}

export default LoginPage;

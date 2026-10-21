import { useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Link, navigate } from '../lib/router';

// Sends signed-out visitors to /login and shows a notice to users without the needed access.
function AccessGate({ allowed, returnTo, title, children }) {
  const { user, checking } = useAuth();

  useEffect(() => {
    if (!checking && !user) {
      navigate(`/login?next=${encodeURIComponent(returnTo)}`, { replace: true });
    }
  }, [checking, user, returnTo]);

  if (checking || !user) {
    return <p className="status-text page">Checking your access…</p>;
  }

  if (!allowed(user)) {
    return (
      <div className="page">
        <div className="notice-card">
          <h1>{title}</h1>
          <p>
            You are signed in as <strong>{user.email ?? user.username}</strong>, but this page is limited to users an administrator
            has given access to. Ask an administrator to grant it in Settings.
          </p>
          <Link to="/" className="button button-secondary">
            Back to release notes
          </Link>
        </div>
      </div>
    );
  }

  return children;
}

export default AccessGate;

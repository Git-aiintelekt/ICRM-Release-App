import { useAuth } from '../context/AuthContext';
import { Link, navigate } from '../lib/router';
import ThemeMenu from './ThemeMenu';

const LOGO_URL = `${import.meta.env.BASE_URL}favicon.ico`;

// The page links live in the left sidebar (AppSidebar); on narrow screens the menu button opens it.
// The public release notes page shows only the brand and the theme menu: no navigation, no sign-in.
function SiteHeader({ pathname, publicPage, menuOpen, onToggleMenu }) {
  const { user, checking, logout, logoutEverywhere } = useAuth();

  if (publicPage) {
    return (
      <header className="site-header">
        <div className="site-header-inner site-header-app">
          <a href={pathname} className="brand">
            <img src={LOGO_URL} alt="" className="brand-logo" width="32" height="32" />
            <span>
              Release <span className="brand-sub">Manager</span>
            </span>
          </a>
          <div className="site-header-spacer" />
          <div className="site-account">
            <ThemeMenu />
          </div>
        </div>
      </header>
    );
  }

  return (
    <header className="site-header">
      <div className="site-header-inner site-header-app">
        {user && (
          <button
            type="button"
            className="icon-button menu-toggle"
            aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
            aria-expanded={Boolean(menuOpen)}
            aria-controls="app-sidebar"
            onClick={onToggleMenu}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d={menuOpen ? 'M6 6l12 12M18 6L6 18' : 'M4 7h16M4 12h16M4 17h16'} />
            </svg>
          </button>
        )}
        <Link to="/" className="brand">
          <img src={LOGO_URL} alt="" className="brand-logo" width="32" height="32" />
          <span>
            Release <span className="brand-sub">Manager</span>
          </span>
        </Link>

        <div className="site-header-spacer" />

        <div className="site-account">
          <ThemeMenu />
          {checking ? null : user ? (
            <>
              <span className="account-name" title={user.email ?? user.username}>
                {user.displayName || user.username}
                {user.isAdmin && <span className="role-badge">Admin</span>}
              </span>
              <button
                type="button"
                className="button button-ghost"
                onClick={() => {
                  logout();
                  navigate('/');
                }}
              >
                Sign out
              </button>
              <button
                type="button"
                className="button button-ghost"
                title="End your sign-in on every device, e.g. after losing a laptop"
                onClick={() => {
                  if (window.confirm('Sign out on every device, including this one?')) {
                    logoutEverywhere()
                      .then(() => navigate('/'))
                      .catch((err) => window.alert(err.message));
                  }
                }}
              >
                Sign out everywhere
              </button>
            </>
          ) : (
            <Link to={`/login?next=${encodeURIComponent(pathname)}`} className="button button-primary">
              Sign in
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}

export default SiteHeader;

import { useAuth } from '../context/AuthContext';
import { Link, navigate } from '../lib/router';
import { OFBIZ_VIEWER, embeddedPackage } from '../lib/target';
import ThemeMenu from './ThemeMenu';

const LOGO_URL = `${import.meta.env.BASE_URL}favicon.ico`;

// Read-only header of the viewer packaged into OFBiz: no sign-in, no admin pages.
function ViewerHeader() {
  const { homeUrl } = embeddedPackage();
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <a href="#top" className="brand">
          <img src={LOGO_URL} alt="" className="brand-logo" width="32" height="32" />
          <span>
            iCRM <span className="brand-sub">Releases</span>
          </span>
        </a>
        <nav className="site-nav" aria-label="Main">
          <a href="#top" className="site-nav-link active" aria-current="page">
            Release notes
          </a>
        </nav>
        <div className="site-account">
          <ThemeMenu />
          {homeUrl && (
            <a href={homeUrl} className="button button-ghost">
              Back to iCRM
            </a>
          )}
        </div>
      </div>
    </header>
  );
}

function SiteHeader({ pathname, menuOpen, onToggleMenu }) {
  if (OFBIZ_VIEWER) {
    return <ViewerHeader />;
  }
  return <AppHeader pathname={pathname} menuOpen={menuOpen} onToggleMenu={onToggleMenu} />;
}

// The page links live in the left sidebar (AppSidebar); on narrow screens the menu button opens it.
function AppHeader({ pathname, menuOpen, onToggleMenu }) {
  const { user, checking, logout, logoutEverywhere } = useAuth();

  return (
    <header className="site-header">
      <div className="site-header-inner site-header-app">
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
        <Link to="/" className="brand">
          <img src={LOGO_URL} alt="" className="brand-logo" width="32" height="32" />
          <span>
            iCRM <span className="brand-sub">Releases</span>
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

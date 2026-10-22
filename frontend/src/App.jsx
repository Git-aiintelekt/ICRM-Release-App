import { useState } from 'react';
import AccessGate from './components/AccessGate';
import AppSidebar from './components/AppSidebar';
import SiteHeader from './components/SiteHeader';
import { AuthProvider, useAuth } from './context/AuthContext';
import { useLocation } from './lib/router';
import AuditLogPage from './pages/AuditLogPage';
import BitbucketPage from './pages/BitbucketPage';
import ChangePasswordPage from './pages/ChangePasswordPage';
import CommitsPage from './pages/CommitsPage';
import DashboardPage from './pages/DashboardPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ImportExportPage from './pages/ImportExportPage';
import JiraPage from './pages/JiraPage';
import LoginPage from './pages/LoginPage';
import ReleasesPage from './pages/ReleasesPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import SettingsPage from './pages/SettingsPage';
import './App.css';

const canViewJira = (user) => user.canViewJira;
const isAdmin = (user) => user.isAdmin;

function Gated({ allowed, path, title, children }) {
  return (
    <AccessGate allowed={allowed} returnTo={path} title={title}>
      {children}
    </AccessGate>
  );
}

// The only pages anyone can open without signing in.
const SIGNED_OUT_PAGES = ['/login', '/forgot-password', '/reset-password'];

function CurrentPage({ pathname, search }) {
  const { user, checking } = useAuth();
  if (checking) {
    return <p className="status-text page">Checking your sign-in…</p>;
  }
  // Signing in comes first: every other page shows the sign-in form, and opens once signed in.
  if (!user && !SIGNED_OUT_PAGES.includes(pathname)) {
    return <LoginPage search={`?next=${encodeURIComponent(pathname + search)}`} />;
  }
  // The default admin account must choose its own password before anything else.
  if (user?.mustChangePassword) {
    return <ChangePasswordPage />;
  }
  switch (pathname) {
    case '/login':
      return <LoginPage search={search} />;
    case '/forgot-password':
      return <ForgotPasswordPage />;
    case '/reset-password':
      return <ResetPasswordPage search={search} />;
    case '/upload':
      // UploadPage checks admin access itself, as before; the export panel is admin-only too.
      return <ImportExportPage />;
    case '/dashboard':
      return (
        <Gated allowed={canViewJira} path="/dashboard" title="Jira access required">
          <DashboardPage />
        </Gated>
      );
    case '/jira':
      return (
        <Gated allowed={canViewJira} path="/jira" title="Jira access required">
          <JiraPage search={search} />
        </Gated>
      );
    case '/bitbucket':
      return (
        <Gated allowed={canViewJira} path="/bitbucket" title="Jira access required">
          <BitbucketPage />
        </Gated>
      );
    case '/commits':
      return (
        <Gated allowed={canViewJira} path="/commits" title="Jira access required">
          <CommitsPage search={search} />
        </Gated>
      );
    case '/audit':
      return (
        <Gated allowed={isAdmin} path="/audit" title="Admin access required">
          <AuditLogPage />
        </Gated>
      );
    case '/settings':
      return (
        <Gated allowed={isAdmin} path="/settings" title="Admin access required">
          <SettingsPage />
        </Gated>
      );
    default:
      return <ReleasesPage />;
  }
}

// The navigation appears once signed in; it then lists only the pages this user may open (Release Notes only,
// unless the user is an admin or was given Jira access).
function Shell({ pathname, search }) {
  const { user } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <>
      <SiteHeader pathname={pathname} menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((open) => !open)} />
      <div className="app-shell">
        {user && !user.mustChangePassword && (
          <AppSidebar pathname={pathname} open={menuOpen} onClose={() => setMenuOpen(false)} />
        )}
        <main className="site-main">
          <CurrentPage pathname={pathname} search={search} />
        </main>
      </div>
    </>
  );
}

function App() {
  const { pathname, search } = useLocation();
  return (
    <AuthProvider>
      <Shell pathname={pathname} search={search} />
    </AuthProvider>
  );
}

export default App;

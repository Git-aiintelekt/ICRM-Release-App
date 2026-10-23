// The left sidebar. `show` uses the same rules as the server: FULLADMIN (isAdmin) and JIRA_VIEWER (canViewJira).
const canViewJira = (user) => Boolean(user?.canViewJira);
const isAdmin = (user) => Boolean(user?.isAdmin);

// The public release notes: read-only, the same for everyone, signed in or not (README: "Public release notes").
export const PUBLIC_RELEASE_NOTES_PATH = '/public/release-notes';

// /public/release-notes/<key>: one product's or client's public page (the key can't be guessed from another link).
export const isPublicPath = (pathname) =>
  pathname === PUBLIC_RELEASE_NOTES_PATH || pathname.startsWith(`${PUBLIC_RELEASE_NOTES_PATH}/`);
export const publicKeyOf = (pathname) =>
  isPublicPath(pathname) ? decodeURIComponent(pathname.slice(PUBLIC_RELEASE_NOTES_PATH.length + 1)) || null : null;
export const publicLink = (key) => `${window.location.origin}${PUBLIC_RELEASE_NOTES_PATH}/${encodeURIComponent(key)}`;

export const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: 'dashboard', show: canViewJira },
  { to: '/', label: 'Release Notes', icon: 'releases', show: () => true },
  { to: '/jira', label: 'Jira Tickets', icon: 'jira', show: canViewJira },
  { to: '/bitbucket', label: 'Bitbucket Repositories', icon: 'repo', show: canViewJira },
  { to: '/commits', label: 'Commits & Pull Requests', icon: 'commit', show: canViewJira },
  { to: '/audit', label: 'Audit Logs', icon: 'audit', show: isAdmin },
  { to: '/upload', label: 'Import / Export', icon: 'import', show: isAdmin },
  { to: '/settings', label: 'Settings / Integrations', icon: 'settings', show: isAdmin },
];

// Django pages (full page loads, not React routes), for admins.
// Hidden for now: set SHOW_ADMIN_LINKS to true to bring back the sidebar's "Administration" section.
// The server must also have ENABLE_DJANGO_ADMIN=true, or /admin/ is a 404.
export const SHOW_ADMIN_LINKS = false;
export const ADMIN_LINKS = [
  { href: '/admin/', label: 'Django Admin' },
];

export function isActive(pathname, to) {
  return to === '/' ? pathname === '/' : pathname === to || pathname.startsWith(`${to}/`);
}

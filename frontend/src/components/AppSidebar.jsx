import { useAuth } from '../context/AuthContext';
import { ADMIN_LINKS, NAV_ITEMS, SHOW_ADMIN_LINKS, isActive } from '../lib/navigation';
import { Link } from '../lib/router';

// 24x24 outline icons (stroke = currentColor).
const ICONS = {
  dashboard: 'M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z',
  releases: 'M6 3h9l4 4v14H6zM15 3v4h4M9 12h7M9 16h7',
  jira: 'M12 3l9 9-9 9-9-9zM12 8l4 4-4 4-4-4z',
  repo: 'M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h11',
  commit: 'M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM3 12h6M15 12h6',
  audit: 'M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6zM9 12l2 2 4-4',
  import: 'M12 3v12M8 11l4 4 4-4M4 17v3h16v-3',
  settings: 'M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM19 12l2-1-1-3-2 .3-1.5-1.5L17 5l-3-1-1 2h-2l-1-2-3 1 .5 2.3L6 8.8 4 8.5 3 11.5l2 .5v2l-2 .5 1 3 2-.3 1.5 1.5L7 21l3 1 1-2h2l1 2 3-1-.5-2.3 1.5-1.5 2 .3 1-3-2-.5z',
  external: 'M14 4h6v6M20 4l-9 9M18 14v6H4V6h6',
};

function Icon({ name }) {
  return (
    <svg className="app-sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  );
}

// Left navigation: always visible on wide screens, a drawer opened from the header's menu button on narrow ones.
function AppSidebar({ pathname, open, onClose }) {
  const { user, checking } = useAuth();
  const items = NAV_ITEMS.filter((item) => item.show(user));

  return (
    <>
      {open && <div className="sidebar-backdrop" onClick={onClose} aria-hidden="true" />}
      <aside id="app-sidebar" className={open ? 'app-sidebar open' : 'app-sidebar'} aria-label="Main navigation">
        <nav>
          <ul className="app-sidebar-list">
            {items.map((item) => {
              const active = isActive(pathname, item.to);
              return (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className={active ? 'app-sidebar-link active' : 'app-sidebar-link'}
                    aria-current={active ? 'page' : undefined}
                    onClick={onClose}
                  >
                    <Icon name={item.icon} />
                    <span>{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
          {SHOW_ADMIN_LINKS && user?.isAdmin && (
            <>
              <p className="app-sidebar-heading">Administration</p>
              <ul className="app-sidebar-list">
                {ADMIN_LINKS.map((item) => (
                  <li key={item.href}>
                    <a href={item.href} className="app-sidebar-link">
                      <Icon name="external" />
                      <span>{item.label}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </>
          )}
          {!user && !checking && <p className="app-sidebar-note">Sign in to see Jira, Bitbucket and admin pages you have access to.</p>}
        </nav>
      </aside>
    </>
  );
}

export default AppSidebar;

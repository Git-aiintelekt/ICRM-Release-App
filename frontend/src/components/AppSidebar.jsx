import { useState } from 'react';
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
  collapse: 'M15 6l-6 6 6 6',
  expand: 'M9 6l6 6-6 6',
};

function Icon({ name }) {
  return (
    <svg className="app-sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  );
}

// Whether the navigation is collapsed to icons, remembered per browser (storage can be unavailable: then expanded).
const COLLAPSED_KEY = 'app-sidebar-collapsed';

function readCollapsed() {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === '1';
  } catch {
    return false;
  }
}

// Left navigation: on wide screens always shown, full or collapsed to icons; on narrow ones a drawer opened from
// the header's menu button (never collapsed there).
function AppSidebar({ pathname, open, onClose }) {
  const { user, checking } = useAuth();
  const items = NAV_ITEMS.filter((item) => item.show(user));
  const [collapsed, setCollapsed] = useState(readCollapsed);

  const toggleCollapsed = () => {
    setCollapsed((value) => {
      try {
        localStorage.setItem(COLLAPSED_KEY, value ? '0' : '1');
      } catch {
        // Not remembered; the toggle still works for this visit.
      }
      return !value;
    });
  };

  return (
    <>
      {open && <div className="sidebar-backdrop" onClick={onClose} aria-hidden="true" />}
      <aside
        id="app-sidebar"
        className={['app-sidebar', open && 'open', collapsed && 'collapsed'].filter(Boolean).join(' ')}
        aria-label="Main navigation"
      >
        <button
          type="button"
          className="app-sidebar-collapse"
          onClick={toggleCollapsed}
          aria-expanded={!collapsed}
          aria-controls="app-sidebar"
          title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        >
          <Icon name={collapsed ? 'expand' : 'collapse'} />
          <span>{collapsed ? 'Expand' : 'Collapse'}</span>
        </button>
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
                    title={collapsed ? item.label : undefined}
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
                    <a href={item.href} className="app-sidebar-link" title={collapsed ? item.label : undefined}>
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

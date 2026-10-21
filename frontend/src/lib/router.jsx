import { useEffect, useState } from 'react';

// Minimal History-API router: /, /jira, /login, /forgot-password, /reset-password, /upload.
const NAVIGATE_EVENT = 'app:navigate';

export function navigate(to, { replace = false } = {}) {
  if (replace) {
    window.history.replaceState(null, '', to);
  } else {
    window.history.pushState(null, '', to);
  }
  window.dispatchEvent(new Event(NAVIGATE_EVENT));
}

export function useLocation() {
  const read = () => ({
    pathname: window.location.pathname,
    search: window.location.search,
    hash: window.location.hash,
  });
  const [location, setLocation] = useState(read);

  useEffect(() => {
    const update = () => setLocation(read());
    window.addEventListener('popstate', update);
    window.addEventListener(NAVIGATE_EVENT, update);
    return () => {
      window.removeEventListener('popstate', update);
      window.removeEventListener(NAVIGATE_EVENT, update);
    };
  }, []);

  return location;
}

export function Link({ to, onClick, ...props }) {
  return (
    <a
      href={to}
      onClick={(event) => {
        onClick?.(event);
        if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) {
          return;
        }
        event.preventDefault();
        navigate(to);
        if (!to.includes('#')) {
          window.scrollTo(0, 0);
        }
      }}
      {...props}
    />
  );
}

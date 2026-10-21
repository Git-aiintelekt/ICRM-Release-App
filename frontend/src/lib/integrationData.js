// Helpers for the Jira/Bitbucket pages (kept apart from components so React Fast Refresh works).
import { useCallback, useEffect, useState } from 'react';

export function formatDateTime(value) {
  if (!value) {
    return '—';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
}

export function formatNumber(value) {
  return value === null || value === undefined ? '—' : value.toLocaleString('en-US');
}

// Loads `load()` and re-runs it whenever `deps` change. Errors keep the server's message (ApiError.message).
export function useApi(load, deps) {
  const [state, setState] = useState({ data: null, error: null, status: null, loading: true });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps);

  const reload = useCallback(() => {
    let cancelled = false;
    setState((current) => ({ ...current, loading: true, error: null }));
    run()
      .then((data) => !cancelled && setState({ data, error: null, status: 200, loading: false }))
      .catch((err) => !cancelled && setState({ data: null, error: err.message, status: err.status ?? null, loading: false }));
    return () => {
      cancelled = true;
    };
  }, [run]);

  useEffect(() => reload(), [reload]);
  return { ...state, reload };
}

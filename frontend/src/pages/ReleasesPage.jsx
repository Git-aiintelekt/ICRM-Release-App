import { useEffect, useMemo, useState } from 'react';
import ReleaseEntry from '../components/ReleaseEntry';
import { useAuth } from '../context/AuthContext';
import { CATEGORIES, CATEGORY_ORDER, formatReleaseDate, versionAnchor } from '../lib/releaseFormat';
import { Link } from '../lib/router';
import { getReleases } from '../services/releaseService';

function matches(item, query) {
  return [item.title, item.description, item.jiraId].some((value) => value?.toLowerCase().includes(query));
}

function ReleasesPage() {
  const { user } = useAuth();
  const [releases, setReleases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('ALL');
  const [activeAnchor, setActiveAnchor] = useState(null);

  useEffect(() => {
    getReleases()
      .then(setReleases)
      .catch(() => setError('Unable to load release history. Please try again later.'))
      .finally(() => setLoading(false));
  }, []);

  // Honour deep links like /#icrm-v109 once the content exists.
  useEffect(() => {
    if (releases.length > 0 && window.location.hash) {
      document.getElementById(window.location.hash.slice(1))?.scrollIntoView();
    }
  }, [releases]);

  const filtering = query.trim() !== '' || category !== 'ALL';
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return releases
      .map((release) => ({
        release,
        items: release.items.filter(
          (item) => (category === 'ALL' || item.category === category) && (!q || matches(item, q))
        ),
      }))
      .filter(({ items }) => !filtering || items.length > 0);
  }, [releases, query, category, filtering]);

  // Highlight the version currently in view in the side navigation.
  useEffect(() => {
    const entries = document.querySelectorAll('.release-entry');
    if (entries.length === 0) {
      return undefined;
    }
    const observer = new IntersectionObserver(
      (observed) => {
        const top = observed.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (top) {
          setActiveAnchor(top.target.id);
        }
      },
      { rootMargin: '-80px 0px -60% 0px' }
    );
    entries.forEach((entry) => observer.observe(entry));
    return () => observer.disconnect();
  }, [visible]);

  const totals = useMemo(() => {
    const counts = { ALL: 0 };
    releases.forEach((release) =>
      release.items.forEach((item) => {
        counts.ALL += 1;
        counts[item.category] = (counts[item.category] ?? 0) + 1;
      })
    );
    return counts;
  }, [releases]);

  return (
    <div className="page">
      <section className="page-hero">
        <p className="eyebrow">Product updates</p>
        <h1>Release notes</h1>
        <p className="page-lede">
          New features, improvements and bug fixes shipped in every iCRM release, linked to their Jira tickets.
        </p>
        {user?.isAdmin && (
          <Link to="/upload" className="button button-primary hero-action">
            Upload release notes
          </Link>
        )}
      </section>

      {loading && <p className="status-text">Loading release history…</p>}
      {error && <p className="status-text status-error">{error}</p>}
      {!loading && !error && releases.length === 0 && <p className="status-text">No release history is available yet.</p>}

      {!loading && !error && releases.length > 0 && (
        <div className="releases-layout">
          <aside className="releases-sidebar">
            <nav aria-label="Versions">
              <p className="sidebar-title">Versions</p>
              <ul className="sidebar-versions">
                {releases.map((release) => {
                  const anchor = versionAnchor(release.version);
                  return (
                    <li key={release.id}>
                      <a href={`#${anchor}`} className={activeAnchor === anchor ? 'active' : undefined}>
                        <span className="sidebar-version">{release.version}</span>
                        <span className="sidebar-date">
                          {release.status === 'UPCOMING'
                            ? `Coming ${release.plannedLabel ?? 'soon'}`
                            : formatReleaseDate(release.releaseDate)}
                        </span>
                      </a>
                    </li>
                  );
                })}
              </ul>
            </nav>
          </aside>

          <div className="releases-main">
            <div className="releases-toolbar">
              <input
                type="search"
                className="input search-input"
                placeholder="Search changes or Jira ID…"
                aria-label="Search release notes"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <div className="filter-chips" role="group" aria-label="Filter by type">
                {['ALL', ...CATEGORY_ORDER].map((key) => (
                  <button
                    key={key}
                    type="button"
                    className={category === key ? 'chip chip-active' : 'chip'}
                    aria-pressed={category === key}
                    onClick={() => setCategory(key)}
                  >
                    {key === 'ALL' ? 'All' : CATEGORIES[key].label}
                    <span className="chip-count">{totals[key] ?? 0}</span>
                  </button>
                ))}
              </div>
            </div>

            {visible.length === 0 && <p className="status-text">No changes match your search.</p>}
            {visible.map(({ release, items }) => (
              <ReleaseEntry
                key={release.id}
                release={release}
                items={items}
                filtering={filtering}
                canEdit={Boolean(user?.isAdmin)}
                onChange={(updated) =>
                  setReleases((current) =>
                    current.map((r) =>
                      r.id === updated.id ? updated : updated.isLatest ? { ...r, isLatest: false } : r
                    )
                  )
                }
                onDeleted={(id) => setReleases((current) => current.filter((r) => r.id !== id))}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default ReleasesPage;

import { useEffect, useMemo, useState } from 'react';
import ReleaseEntry from '../components/ReleaseEntry';
import { useAuth } from '../context/AuthContext';
import { PUBLIC_RELEASE_NOTES_PATH } from '../lib/navigation';
import { CATEGORIES, CATEGORY_ORDER, formatReleaseDate, versionAnchor } from '../lib/releaseFormat';
import { Link } from '../lib/router';
import { getAuthOptions } from '../services/authService';
import { getPublicReleases, getReleases } from '../services/releaseService';

// Release manager only, while the public page is switched on: copies its link (or one version's) to share.
function CopyPublicLinkButton() {
  const [publicOn, setPublicOn] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getAuthOptions()
      .then((options) => setPublicOn(Boolean(options.publicReleaseNotes)))
      .catch(() => null);
  }, []);

  if (!publicOn) {
    return null;
  }
  const copy = async () => {
    const url = `${window.location.origin}${PUBLIC_RELEASE_NOTES_PATH}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt('Copy the public link:', url);
    }
  };
  return (
    <button
      type="button"
      className="button button-secondary hero-action"
      onClick={copy}
      title="Anyone with this link can read the release notes without signing in (no Jira numbers)"
    >
      {copied ? 'Link copied' : 'Copy public link'}
    </button>
  );
}

// Colour of each kind of change in the summary bars (the same as its label on the list).
const CATEGORY_TONE = { NEW_FEATURE: 'new', IMPROVEMENT: 'improved', BUG_FIX: 'fixed', SECURITY: 'security' };

// Beside the page title: how many versions and changes there are, and the latest version.
function HeroStats({ releases, totalChanges }) {
  const latest = releases.find((r) => r.isLatest);
  return (
    <dl className="hero-stats">
      <div className="hero-stat">
        <dt>Versions</dt>
        <dd>{releases.length}</dd>
      </div>
      <div className="hero-stat">
        <dt>Changes</dt>
        <dd>{totalChanges}</dd>
      </div>
      {latest && (
        <div className="hero-stat hero-stat-wide">
          <dt>Latest</dt>
          <dd>
            <a href={`#${versionAnchor(latest.version)}`}>{latest.version}</a>
            <span className="hero-stat-sub">{formatReleaseDate(latest.releaseDate)}</span>
          </dd>
        </div>
      )}
    </dl>
  );
}

// Right-hand panel on wide screens: the version being read, its changes by kind (click one to filter), and a way back up.
function GlanceRail({ release, category, onCategory }) {
  if (!release) {
    return null;
  }
  const counts = CATEGORY_ORDER.map((key) => [key, release.items.filter((item) => item.category === key).length]);
  const most = Math.max(1, ...counts.map(([, count]) => count));
  return (
    <aside className="releases-rail" aria-label="This version at a glance">
      <div className="rail-card">
        <p className="sidebar-title">At a glance</p>
        <p className="rail-version">Version {release.version}</p>
        <p className="rail-date">
          {release.status === 'UPCOMING'
            ? `Coming ${release.plannedLabel ?? 'soon'}`
            : `Released ${formatReleaseDate(release.releaseDate)}`}
        </p>
        <p className="rail-total">
          <strong>{release.items.length}</strong> changes
        </p>
        <ul className="rail-bars">
          {counts.map(([key, count]) => (
            <li key={key}>
              <button
                type="button"
                className={category === key ? 'rail-bar rail-bar-active' : 'rail-bar'}
                aria-pressed={category === key}
                onClick={() => onCategory(category === key ? 'ALL' : key)}
                title={category === key ? 'Show all changes' : `Show only ${CATEGORIES[key].heading.toLowerCase()}`}
              >
                <span className="rail-bar-label">
                  {CATEGORIES[key].label}
                  <span className="rail-bar-count">{count}</span>
                </span>
                <span className="rail-bar-track">
                  <span
                    className={`rail-bar-fill rail-tone-${CATEGORY_TONE[key]}`}
                    style={{ width: `${(count / most) * 100}%` }}
                  />
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
      <button type="button" className="link-button rail-top" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
        ↑ Back to top
      </button>
    </aside>
  );
}

function matches(item, query) {
  return [item.title, item.description, item.jiraId].some((value) => value?.toLowerCase().includes(query));
}

// publicView: the public page (/public/release-notes) for anyone, signed in or not. Read-only, without Jira numbers.
function ReleasesPage({ publicView = false }) {
  const { user: signedInUser } = useAuth();
  const user = publicView ? null : signedInUser;
  const [releases, setReleases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('ALL');
  const [activeAnchor, setActiveAnchor] = useState(null);

  useEffect(() => {
    (publicView ? getPublicReleases() : getReleases())
      .then(setReleases)
      .catch((err) =>
        setError(
          publicView && err.status === 404
            ? 'The public release notes page is switched off. Ask the release manager for access.'
            : 'Unable to load release history. Please try again later.'
        )
      )
      .finally(() => setLoading(false));
  }, [publicView]);

  // Which version is Latest is decided on the server (the highest released number); reload when an edit moves it.
  const reload = () =>
    (publicView ? getPublicReleases() : getReleases()).then(setReleases).catch(() => null);

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
      <section className="page-hero page-hero-split">
        <div className="hero-text">
          <p className="eyebrow">Product updates</p>
          <h1>Release notes</h1>
          <p className="page-lede">
            {publicView
              ? 'New features, improvements and bug fixes shipped in every iCRM release.'
              : 'New features, improvements and bug fixes shipped in every iCRM release, linked to their Jira tickets.'}
          </p>
          {user?.isAdmin && (
            <div className="hero-actions">
              <Link to="/upload" className="button button-primary hero-action">
                Upload release notes
              </Link>
              <CopyPublicLinkButton />
            </div>
          )}
        </div>
        {releases.length > 0 && <HeroStats releases={releases} totalChanges={totals.ALL} />}
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
                placeholder={publicView ? 'Search changes…' : 'Search changes or Jira ID…'}
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
                onChange={(updated) => {
                  const before = releases.find((r) => r.id === updated.id);
                  setReleases((current) => current.map((r) => (r.id === updated.id ? updated : r)));
                  if (before && before.isLatest !== updated.isLatest) {
                    reload(); // Latest moved to or from this version: the server has updated the others too
                  }
                }}
                onDeleted={(id) => {
                  const wasLatest = releases.find((r) => r.id === id)?.isLatest;
                  setReleases((current) => current.filter((r) => r.id !== id));
                  if (wasLatest) {
                    reload(); // the next highest version is the latest now
                  }
                }}
              />
            ))}
          </div>

          <GlanceRail
            release={releases.find((r) => versionAnchor(r.version) === activeAnchor) ?? visible[0]?.release}
            category={category}
            onCategory={setCategory}
          />
        </div>
      )}
    </div>
  );
}

export default ReleasesPage;

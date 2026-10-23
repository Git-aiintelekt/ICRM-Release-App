import { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { formatDateTime, formatNumber, useApi } from '../lib/integrationData';
import { HeroStats, serviceHealth } from '../components/IntegrationUI';
import JiraIssueDetails from '../components/JiraIssueDetails';
import JiraIssueList from '../components/JiraIssueList';
import LiveJiraTickets from '../components/LiveJiraTickets';
import { getJiraIssueDetail, getJiraIssues } from '../services/jiraService';
import { getIntegrationStatus } from '../services/integrationsService';
import { Link } from '../lib/router';

// The imported 10.9 Jira list with seed and table data (unchanged from before the live integration).
function ImportedJiraIssues() {
  const [issues, setIssues] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [listError, setListError] = useState(null);
  const [detailError, setDetailError] = useState(null);

  useEffect(() => {
    getJiraIssues()
      .then((data) => {
        setIssues(data);
        if (data.length > 0) {
          setSelectedId(data[0].jiraId);
        }
      })
      .catch(() => setListError('Unable to load Jira issues. Please try again later.'))
      .finally(() => setListLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    setDetailLoading(true);
    setDetailError(null);
    getJiraIssueDetail(selectedId)
      .then(setDetail)
      .catch(() => setDetailError('Unable to load issue details.'))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  return (
    <>
      {listLoading && <p className="status-text">Loading Jira issues…</p>}
      {listError && <p className="status-text status-error">{listError}</p>}
      {!listLoading && !listError && issues.length === 0 && <p className="status-text">No Jira issues imported yet.</p>}

      {!listLoading && !listError && issues.length > 0 && (
        <div className="jira-layout">
          <JiraIssueList issues={issues} selectedId={selectedId} onSelect={setSelectedId} />
          <JiraIssueDetails issue={detail} loading={detailLoading} error={detailError} />
        </div>
      )}
    </>
  );
}

// The imported list is hidden; set to true to bring its tab back.
const SHOW_IMPORTED = false;
// Beside the title: the Jira projects shown here and whether Jira answers.
function jiraStats(jira) {
  const keys = jira.projectKeys ?? [];
  return [
    { label: 'Projects', value: formatNumber(keys.length), sub: keys.join(', ') || 'none added' },
    { label: 'Jira', value: serviceHealth(jira).state, text: true, sub: `Synced ${formatDateTime(jira.lastSuccessAt)}`, wide: true },
  ];
}

const TABS = [
  { id: 'live', label: 'Live tickets' },
  ...(SHOW_IMPORTED ? [{ id: 'imported', label: 'Imported release data' }] : []),
];

function JiraPage({ search = '' }) {
  const status = useApi(() => getIntegrationStatus(), []);
  const { user } = useAuth();
  // #imported, or filters in the URL (links from the Dashboard), pick the tab; otherwise it follows the status.
  const [chosen, setChosen] = useState(() => {
    if (!SHOW_IMPORTED) return 'live';
    if (window.location.hash === '#imported') return 'imported';
    return search.length > 1 ? 'live' : null;
  });
  // Until Jira is connected, open on the imported data, as this page always did.
  const tab = chosen ?? (status.loading ? null : status.data?.jira.configured ? 'live' : 'imported');

  const selectTab = (id) => {
    setChosen(id);
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${id === 'imported' ? '#imported' : ''}`);
  };

  return (
    <div className="page">
      <section className="page-hero page-hero-split">
        <div className="hero-text">
          <p className="eyebrow">Engineering</p>
          <h1>Jira tickets</h1>
          <p className="page-lede">
            Live tickets from Jira (projects {status.data?.jira.projectKeys?.join(', ') || '…'})
            {SHOW_IMPORTED ? ', and the imported Jira list with its seed and table data.' : '.'}
            {user?.isAdmin && (
              <>
                {' '}
                <Link to="/settings#integrations">Add or remove Jira projects</Link>
              </>
            )}
          </p>
        </div>
        {status.data && <HeroStats items={jiraStats(status.data.jira)} />}
      </section>

      {TABS.length > 1 && (
        <div className="tabs" role="tablist" aria-label="Jira sections">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`tab-${item.id}`}
              aria-selected={tab === item.id}
              aria-controls={`panel-${item.id}`}
              className={tab === item.id ? 'tab active' : 'tab'}
              onClick={() => selectTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      {tab === null && <p className="status-text">Loading…</p>}
      {tab && (
        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="tab-panel">
          {tab === 'live' ? <LiveJiraTickets search={search} /> : <ImportedJiraIssues />}
        </div>
      )}
    </div>
  );
}

export default JiraPage;

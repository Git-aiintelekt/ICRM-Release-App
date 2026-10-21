import { useState } from 'react';
import { ApiState, HealthPanel } from './IntegrationUI';
import ScopeSettings from './ScopeSettings';
import { formatDateTime, useApi } from '../lib/integrationData';
import { getIntegrationStatus, refreshIntegrations } from '../services/integrationsService';

const SETTINGS_HELP = [
  ['JIRA_BASE_URL', 'Jira Cloud site, e.g. https://your-site.atlassian.net'],
  ['JIRA_EMAIL / JIRA_API_TOKEN', 'Atlassian account email and API token (read access to the projects)'],
  ['JIRA_PROJECT_KEYS', 'Projects to count and list, comma-separated'],
  ['JIRA_RESOLVED_STATUSES / JIRA_CLOSED_STATUSES', 'Done-category status names counted as resolved / closed'],
  ['JIRA_FIX_VERSION_MAP', 'Optional: app version = Jira fix version names, for release-wise summaries'],
  ['BITBUCKET_WORKSPACE / BITBUCKET_REPOSITORIES', 'Workspace and repository slugs (comma-separated)'],
  ['BITBUCKET_EMAIL / BITBUCKET_API_TOKEN', 'Atlassian API token with Bitbucket read scopes (or BITBUCKET_ACCESS_TOKEN)'],
];

// Settings → Integrations: connection health and a cache refresh. Credentials are never sent to the browser;
// this tab only shows whether each one is set.
function IntegrationsTab() {
  const status = useApi(() => getIntegrationStatus(), []);
  const [refreshing, setRefreshing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      setResult({ ...(await refreshIntegrations()), at: new Date().toISOString() });
      status.reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <ApiState state={status} loadingText="Loading integration status…">
      {(data) => (
        <>
          <div className="settings-toolbar">
            <p className="settings-hint">
              Jira and Bitbucket answers are reused for {Math.round(data.cacheSeconds / 60)} minutes. Refresh to fetch fresh data
              and test both connections now.
            </p>
            <button type="button" className="button button-primary" onClick={refresh} disabled={refreshing}>
              {refreshing ? 'Testing…' : 'Refresh and test connections'}
            </button>
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {result && (
            <ul className="plain-list integration-checks">
              {Object.entries(result.checks).map(([name, check]) => (
                <li key={name}>
                  <strong>{name === 'jira' ? 'Jira' : 'Bitbucket'}:</strong>{' '}
                  {check.ok
                    ? `connected${check.account ? ` as ${check.account}` : ''}${check.repository ? ` (${check.repository})` : ''}`
                    : check.detail}{' '}
                  <span className="cell-sub">tested {formatDateTime(result.at)}</span>
                </li>
              ))}
            </ul>
          )}

          <HealthPanel status={data} />

          <ScopeSettings status={data} onChange={status.reload} />

          <h3 className="integration-subhead">Server configuration (.env)</h3>
          <p className="settings-hint">
            Set these on the server in <code>release_notes/.env</code> (see <code>.env.example</code>), then restart Django.
          </p>
          <div className="review-table-wrap">
            <table className="data-table">
              <tbody>
                {SETTINGS_HELP.map(([name, help]) => (
                  <tr key={name}>
                    <td className="mono nowrap">{name}</td>
                    <td>{help}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ApiState>
  );
}

export default IntegrationsTab;

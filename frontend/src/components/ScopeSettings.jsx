import { useState } from 'react';
import { useApi } from '../lib/integrationData';
import { addScope, getJiraFilters, removeScope } from '../services/integrationsService';
import { BranchEditor, RepositoryEditor } from './ScopeEditors';

const PROJECT_KEY_RE = /^[A-Z][A-Z0-9_]{1,9}$/;

function ScopeList({ entries, busy, onRemove, emptyText }) {
  if (!entries.length) {
    return <p className="cell-sub">{emptyText}</p>;
  }
  return (
    <ul className="scope-chips">
      {entries.map((entry) => (
        <li key={entry.id} className="scope-chip">
          <span className="mono">{entry.value}</span>
          <button
            type="button"
            className="scope-chip-remove"
            onClick={() => onRemove(entry)}
            disabled={busy}
            aria-label={`Remove ${entry.value}`}
            title="Remove"
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}

// Settings → Integrations: the branches (per repository) and Jira fix versions every screen is limited to.
// Saved on the server for everyone; with none added, screens show every branch / every fix version.
function ScopeSettings({ status, onChange }) {
  const entries = status.scope.entries;
  const jiraFilters = useApi(() => (status.jira.configured ? getJiraFilters() : Promise.resolve(null)), [status.jira.configured]);
  const [version, setVersion] = useState('');
  const [project, setProject] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const run = async (call) => {
    setBusy(true);
    setError(null);
    try {
      await call();
      onChange();
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const addVersion = async (event) => {
    event.preventDefault();
    if (await run(() => addScope({ kind: 'FIX_VERSION', value: version.trim() }))) setVersion('');
  };
  const addProject = async (event) => {
    event.preventDefault();
    if (await run(() => addScope({ kind: 'JIRA_PROJECT', value: project.trim().toUpperCase() }))) setProject('');
  };
  const remove = (entry) => run(() => removeScope(entry.id));
  const projectInvalid = project.trim() && !PROJECT_KEY_RE.test(project.trim().toUpperCase());

  const versions = entries.filter((e) => e.kind === 'FIX_VERSION');
  const chosen = new Set(versions.map((e) => e.value));
  const versionOptions = (jiraFilters.data?.allFixVersions ?? []).filter((name) => name && !chosen.has(name));

  return (
    <section className="scope-settings">
      <h3 className="integration-subhead">What the screens show</h3>
      <p className="settings-hint">
        Add branches to show only those branches&apos; details, commits and pull requests on the Bitbucket, Commits and
        Dashboard pages. Add Jira fix versions to limit the Dashboard counts and the Jira ticket list to those versions. Add
        Jira projects to include a new project&apos;s tickets everywhere. This applies to everyone; with no branches or fix
        versions added, everything is shown.
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <div className="scope-grid">
        <div className="scope-block">
          <h4>Bitbucket repositories</h4>
          <RepositoryEditor status={status} onChange={onChange} />
        </div>

        <div className="scope-block">
          <h4>Bitbucket branches</h4>
          {status.bitbucket.repositories.length === 0 ? (
            <p className="cell-sub">No repositories are configured.</p>
          ) : (
            <BranchEditor status={status} onChange={onChange} />
          )}
        </div>

        <div className="scope-block">
          <h4>Jira projects</h4>
          {status.jira.baseProjectKeys?.length > 0 && (
            <ul className="scope-chips" aria-label="Projects from JIRA_PROJECT_KEYS">
              {status.jira.baseProjectKeys.map((key) => (
                <li key={key} className="scope-chip scope-chip-fixed" title="Set in .env (JIRA_PROJECT_KEYS)">
                  <span className="mono">{key}</span>
                </li>
              ))}
            </ul>
          )}
          <ScopeList
            entries={entries.filter((e) => e.kind === 'JIRA_PROJECT')}
            busy={busy}
            onRemove={remove}
            emptyText="No projects added here yet; the ones above come from .env (JIRA_PROJECT_KEYS)."
          />
          {status.jira.configured ? (
            <form className="scope-add" onSubmit={addProject}>
              <label className="field">
                <span>Project key</span>
                <input
                  className="input mono"
                  value={project}
                  onChange={(event) => setProject(event.target.value)}
                  placeholder="e.g. CRM"
                  maxLength={10}
                />
              </label>
              <button type="submit" className="button button-secondary" disabled={busy || !project.trim() || projectInvalid}>
                {busy ? 'Checking…' : 'Add project'}
              </button>
            </form>
          ) : (
            <p className="cell-sub">Jira is not configured.</p>
          )}
          {projectInvalid && (
            <p className="form-error">A project key is 2–10 letters or digits starting with a letter, as in a ticket number (CS-123 → CS).</p>
          )}
        </div>

        <div className="scope-block">
          <h4>Jira fix versions</h4>
          <ScopeList entries={versions} busy={busy} onRemove={remove} emptyText="All fix versions" />
          {status.jira.configured ? (
            <form className="scope-add" onSubmit={addVersion}>
              <label className="field">
                <span>Fix version</span>
                <input
                  className="input"
                  list="scope-fix-versions"
                  value={version}
                  onChange={(event) => setVersion(event.target.value)}
                  placeholder={jiraFilters.loading ? 'Loading versions…' : 'Type or pick a Jira fix version'}
                  maxLength={100}
                />
                <datalist id="scope-fix-versions">
                  {versionOptions.map((name) => (
                    <option key={name} value={name} />
                  ))}
                </datalist>
              </label>
              <button type="submit" className="button button-secondary" disabled={busy || !version.trim()}>
                {busy ? 'Checking…' : 'Add fix version'}
              </button>
            </form>
          ) : (
            <p className="cell-sub">Jira is not configured.</p>
          )}
          {jiraFilters.error && <p className="cell-sub">Couldn&apos;t load the version list: {jiraFilters.error}</p>}
        </div>
      </div>
    </section>
  );
}

export default ScopeSettings;

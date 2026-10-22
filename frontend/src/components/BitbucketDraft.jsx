import { useState } from 'react';
import { ApiState } from './IntegrationUI';
import { useApi } from '../lib/integrationData';
import { draftFromBitbucket, getBitbucketVersions } from '../services/adminReleaseService';

function versionLabel(v) {
  const compared = [...new Set(v.repositories.map((r) => r.previousVersion).filter(Boolean))];
  return `${v.version}${v.date ? ` (${v.date})` : ''}${compared.length ? `, changes since ${compared.join(' / ')}` : ''}${
    v.published ? ' (already published)' : ''
  }`;
}

function VersionPicker({ versions, onDraft }) {
  const [version, setVersion] = useState(() => (versions.find((v) => !v.published) ?? versions[0]).version);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const selected = versions.find((v) => v.version === version);

  const draft = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDraft(await draftFromBitbucket(version));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <form className="bitbucket-draft-form" onSubmit={draft}>
      <label className="field">
        <span>Version</span>
        <select className="input" value={version} onChange={(event) => setVersion(event.target.value)} disabled={busy}>
          {versions.map((v) => (
            <option key={v.version} value={v.version}>
              {versionLabel(v)}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" className="button button-primary" disabled={busy}>
        {busy ? 'Reading commits and Jira…' : 'Draft release notes'}
      </button>
      {selected && (
        <ul className="plain-list bitbucket-draft-branches">
          {selected.repositories.map((r) => (
            <li key={r.repository} className="cell-sub">
              <span className="mono">{r.repository}</span>: commits on <span className="mono">{r.branch}</span>
              {r.previousBranch ? (
                <>
                  {' '}that aren&apos;t on <span className="mono">{r.previousBranch}</span>
                </>
              ) : (
                ' (no earlier version branch: every commit)'
              )}
            </li>
          ))}
        </ul>
      )}
      {busy && <p className="cell-sub">This reads every commit of the version, so it can take 10–30 seconds.</p>}
      {selected?.published && (
        <p className="cell-sub">
          This version is already published. Delete it on the Release Notes page first if you want to replace it.
        </p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

// Import / Export: draft a version's release notes from its release/ branch in Bitbucket. The Jira keys in the
// version's commits become the changes (Jira summary, description and type); the draft opens in the same review
// as an uploaded document, and nothing is saved until it's published.
function BitbucketDraft({ onDraft }) {
  const versions = useApi(() => getBitbucketVersions(), []);
  return (
    <section className="bitbucket-draft" aria-labelledby="bitbucket-draft-heading">
      <h2 id="bitbucket-draft-heading">Draft from Bitbucket</h2>
      <p className="settings-hint">
        Each branch named <code>release/icrm_release_&lt;version&gt;_&lt;date&gt;</code> is a version. Its changes are
        the Jira issues mentioned in the commits that aren&apos;t on the previous version&apos;s branch.
      </p>
      <ApiState
        state={versions}
        service="bitbucket"
        loadingText="Looking for release branches…"
        isEmpty={(data) => data.length === 0}
        emptyText="No release/icrm_release_<version>_<date> branches were found in the repositories."
      >
        {(data) => <VersionPicker versions={data} onDraft={onDraft} />}
      </ApiState>
    </section>
  );
}

export default BitbucketDraft;

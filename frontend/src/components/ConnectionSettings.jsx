import { useState } from 'react';
import { ApiState } from './IntegrationUI';
import { useApi } from '../lib/integrationData';
import { getCredentials, saveCredentials } from '../services/integrationsService';

const SOURCE_TEXT = { app: 'Saved here', env: 'From .env', null: 'Not set' };

// JIRA_BASE_URL -> jiraBaseUrl, the key the server expects.
const toKey = (name) => name.toLowerCase().replace(/_([a-z])/g, (_, c) => c.toUpperCase());

function ConnectionForm({ fields, saved, setSaved, onSaved }) {
  const [values, setValues] = useState(() =>
    Object.fromEntries(fields.map((f) => [f.name, f.secret ? '' : (f.value ?? '')]))
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const send = async (changes) => {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await saveCredentials(changes);
      setSaved(true);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const submit = (event) => {
    event.preventDefault();
    // Only what changed: a blank token field keeps the saved token.
    const changes = {};
    fields.forEach((f) => {
      const value = values[f.name].trim();
      if (f.secret ? value : value !== (f.value ?? '')) {
        changes[toKey(f.name)] = value;
      }
    });
    if (Object.keys(changes).length) {
      send(changes);
    }
  };

  return (
    <form className="connection-form" onSubmit={submit}>
      {fields.map((f) => (
        <label key={f.name} className="field">
          <span>
            {f.label} <span className={`connection-source source-${f.source ?? 'none'}`}>{SOURCE_TEXT[f.source]}</span>
          </span>
          <input
            className="input"
            type={f.secret ? 'password' : 'text'}
            value={values[f.name]}
            onChange={(event) => setValues((v) => ({ ...v, [f.name]: event.target.value }))}
            placeholder={f.secret && f.source ? 'Saved; leave blank to keep it' : ''}
            autoComplete="off"
            spellCheck={false}
          />
          {f.secret && f.source === 'app' && (
            <button
              type="button"
              className="link-button connection-clear"
              disabled={busy}
              onClick={() => send({ [toKey(f.name)]: null })}
            >
              Remove the saved token
            </button>
          )}
        </label>
      ))}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="connection-actions">
        <button type="submit" className="button button-primary" disabled={busy}>
          {busy ? 'Saving…' : 'Save connection settings'}
        </button>
        {saved && <span className="cell-sub">Saved. Use “Refresh and test connections” above to check them.</span>}
      </div>
    </form>
  );
}

// Settings → Integrations: the Jira / Bitbucket accounts and tokens. Saved on the server, encrypted; a token is
// never shown again once saved. A value saved here replaces the .env value; an empty field falls back to .env.
function ConnectionSettings({ onChange }) {
  const credentials = useApi(() => getCredentials(), []);
  // Kept here: the form starts afresh with the saved values after each save.
  const [saved, setSaved] = useState(false);

  return (
    <ApiState state={credentials} loadingText="Loading connection settings…">
      {(data) => (
        <ConnectionForm
          key={JSON.stringify(data.fields)}
          fields={data.fields}
          saved={saved}
          setSaved={setSaved}
          onSaved={() => {
            credentials.reload();
            onChange();
          }}
        />
      )}
    </ApiState>
  );
}

export default ConnectionSettings;

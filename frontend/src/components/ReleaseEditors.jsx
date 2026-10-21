import { useRef, useState } from 'react';
import { CATEGORIES, CATEGORY_ORDER } from '../lib/releaseFormat';
import * as edit from '../services/adminReleaseEditService';

const toLines = (text) =>
  text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

// Runs a save call, reporting errors inline; returns true on success.
function useSaver(onSaved) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const run = async (call) => {
    setBusy(true);
    setError(null);
    try {
      const result = await call();
      if (result) {
        onSaved(result);
      }
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

export function ReleaseDetailsEditor({ release, onSaved, onDeleted, onClose }) {
  const [form, setForm] = useState({
    status: release.status,
    plannedLabel: release.plannedLabel ?? '',
    releaseDate: release.releaseDate,
    summary: release.description ?? '',
    highlights: release.highlights.join('\n'),
    knownIssues: release.knownIssues.join('\n'),
    upgradeNotes: release.upgradeNotes.join('\n'),
    markLatest: release.isLatest,
  });
  const { busy, error, run } = useSaver(onSaved);
  const set = (key) => (event) =>
    setForm((current) => ({ ...current, [key]: event.target.type === 'checkbox' ? event.target.checked : event.target.value }));

  const save = async (event) => {
    event.preventDefault();
    const ok = await run(() =>
      edit.updateRelease(release.id, {
        status: form.status,
        plannedLabel: form.status === 'UPCOMING' ? form.plannedLabel : null,
        releaseDate: form.releaseDate,
        summary: form.summary,
        highlights: toLines(form.highlights),
        knownIssues: toLines(form.knownIssues),
        upgradeNotes: toLines(form.upgradeNotes),
        markLatest: form.markLatest,
      })
    );
    if (ok) {
      onClose();
    }
  };

  const remove = async () => {
    const answer = window.prompt(
      `Delete version ${release.version} and all ${release.items.length} of its changes and screenshots? This can't be undone.\n\nType the version number to confirm:`
    );
    if (answer?.trim() !== release.version) {
      return;
    }
    const ok = await run(() => edit.deleteRelease(release.id).then(() => null));
    if (ok) {
      onDeleted(release.id);
    }
  };

  return (
    <form className="edit-panel" onSubmit={save}>
      <div className="review-meta review-meta-wide">
        <label className="field">
          <span>Status</span>
          <select className="input" value={form.status} onChange={set('status')}>
            <option value="RELEASED">Released</option>
            <option value="UPCOMING">Coming soon</option>
          </select>
        </label>
        {form.status === 'UPCOMING' && (
          <label className="field">
            <span>Planned for</span>
            <input className="input" value={form.plannedLabel} onChange={set('plannedLabel')} placeholder="October 2026" maxLength={100} />
          </label>
        )}
        <label className="field">
          <span>{form.status === 'UPCOMING' ? 'Expected date' : 'Release date'}</span>
          <input className="input" type="date" value={form.releaseDate} onChange={set('releaseDate')} required />
        </label>
        <label className="field field-wide">
          <span>Summary</span>
          <textarea className="input" rows={3} value={form.summary} onChange={set('summary')} maxLength={1000} />
        </label>
      </div>
      <div className="review-meta review-meta-three">
        <label className="field">
          <span>Highlights (one per line)</span>
          <textarea className="input" rows={4} value={form.highlights} onChange={set('highlights')} />
        </label>
        <label className="field">
          <span>Known issues (one per line)</span>
          <textarea className="input" rows={4} value={form.knownIssues} onChange={set('knownIssues')} />
        </label>
        <label className="field">
          <span>Upgrade notes (one per line)</span>
          <textarea className="input" rows={4} value={form.upgradeNotes} onChange={set('upgradeNotes')} />
        </label>
      </div>
      <label className="checkbox">
        <input type="checkbox" checked={form.markLatest} onChange={set('markLatest')} />
        Latest release
      </label>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="edit-actions">
        <button type="button" className="button button-danger-ghost" onClick={remove} disabled={busy}>
          Delete version
        </button>
        <span className="edit-actions-spacer" />
        <button type="button" className="button button-ghost" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="button button-primary" disabled={busy}>
          {busy ? 'Saving…' : 'Save details'}
        </button>
      </div>
    </form>
  );
}

export function ScreenshotManager({ releaseId, itemId, images, onSaved, label }) {
  const fileRef = useRef(null);
  const [captions, setCaptions] = useState({});
  const [newCaption, setNewCaption] = useState('');
  const { busy, error, run } = useSaver(onSaved);

  const upload = async (file) => {
    const ok = await run(() => edit.addImage(releaseId, file, { caption: newCaption, itemId }));
    if (ok) {
      setNewCaption('');
    }
  };

  return (
    <div className="screenshot-manager">
      {images.length > 0 && (
        <div className="image-strip">
          {images.map((image) => {
            const caption = captions[image.id] ?? image.caption ?? '';
            const dirty = caption !== (image.caption ?? '');
            return (
              <figure key={image.id} className="image-edit">
                <a href={image.url} target="_blank" rel="noreferrer">
                  <img src={image.url} alt={image.caption ?? 'Screenshot'} />
                </a>
                <input
                  className="input input-subtle"
                  value={caption}
                  placeholder="Caption (optional)"
                  aria-label="Screenshot caption"
                  maxLength={255}
                  onChange={(event) => setCaptions((c) => ({ ...c, [image.id]: event.target.value }))}
                />
                {dirty && (
                  <button
                    type="button"
                    className="link-button"
                    disabled={busy}
                    onClick={() => run(() => edit.updateImageCaption(image.id, caption))}
                  >
                    Save caption
                  </button>
                )}
                <button
                  type="button"
                  className="icon-button image-remove"
                  aria-label="Remove screenshot"
                  disabled={busy}
                  onClick={() => window.confirm('Remove this screenshot?') && run(() => edit.deleteImage(image.id))}
                >
                  ×
                </button>
              </figure>
            );
          })}
        </div>
      )}
      <div className="screenshot-add">
        <input
          className="input input-subtle"
          value={newCaption}
          placeholder="Caption for a new screenshot (optional)"
          aria-label="Caption for new screenshot"
          maxLength={255}
          onChange={(event) => setNewCaption(event.target.value)}
        />
        <button type="button" className="button button-secondary" disabled={busy} onClick={() => fileRef.current?.click()}>
          {busy ? 'Uploading…' : label}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/gif,image/webp"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (file) {
              upload(file);
            }
          }}
        />
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function ItemEditor({ releaseId, item, onSaved, onClose }) {
  const isNew = !item;
  const [form, setForm] = useState({
    category: item?.category ?? 'NEW_FEATURE',
    jiraId: item?.jiraId ?? '',
    title: item?.title ?? '',
    description: item?.description ?? '',
  });
  const { busy, error, run } = useSaver(onSaved);
  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }));

  const save = async (event) => {
    event.preventDefault();
    const body = { ...form, jiraId: form.jiraId.trim() || null, description: form.description.trim() || null };
    const ok = await run(() => (isNew ? edit.addItem(releaseId, body) : edit.updateItem(item.id, body)));
    if (ok) {
      onClose();
    }
  };

  const remove = async () => {
    if (!window.confirm(`Remove "${item.title}" and its screenshots from this release?`)) {
      return;
    }
    const ok = await run(() => edit.deleteItem(item.id));
    if (ok) {
      onClose();
    }
  };

  return (
    <form className="edit-panel item-editor" onSubmit={save}>
      <div className="item-editor-row">
        <label className="field">
          <span>Type</span>
          <select className="input" value={form.category} onChange={set('category')}>
            {CATEGORY_ORDER.map((key) => (
              <option key={key} value={key}>
                {CATEGORIES[key].label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Jira ID</span>
          <input className="input input-mono" value={form.jiraId} onChange={set('jiraId')} placeholder="CS-1234" maxLength={20} />
        </label>
        <label className="field item-editor-title">
          <span>Title</span>
          <input className="input" value={form.title} onChange={set('title')} required maxLength={500} />
        </label>
      </div>
      <label className="field">
        <span>Description</span>
        <textarea
          className="input"
          rows={3}
          value={form.description}
          onChange={set('description')}
          maxLength={1000}
          placeholder="What changed, where, and why it matters (2–3 sentences)"
        />
      </label>
      {!isNew && (
        <ScreenshotManager
          releaseId={releaseId}
          itemId={item.id}
          images={item.images}
          onSaved={onSaved}
          label="Add screenshot"
        />
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="edit-actions">
        {!isNew && (
          <button type="button" className="button button-danger-ghost" onClick={remove} disabled={busy}>
            Remove change
          </button>
        )}
        <span className="edit-actions-spacer" />
        <button type="button" className="button button-ghost" onClick={onClose} disabled={busy}>
          {isNew ? 'Cancel' : 'Close'}
        </button>
        <button type="submit" className="button button-primary" disabled={busy || !form.title.trim()}>
          {busy ? 'Saving…' : isNew ? 'Add change' : 'Save change'}
        </button>
      </div>
      {isNew && <p className="field-hint">Screenshots can be added once the change is saved.</p>}
    </form>
  );
}

// Admins: add the changes in a CSV file (same columns as the Upload page) to this version.
export function CsvImportButton({ release, onSaved }) {
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const upload = async (file) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const imported = await edit.importItems(release.id, file);
      onSaved(imported.release);
      setResult(imported);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button type="button" className="button button-secondary" disabled={busy} onClick={() => fileRef.current?.click()}>
        {busy ? 'Adding…' : 'Add changes from CSV'}
      </button>
      <input
        ref={fileRef}
        type="file"
        accept=".csv,text/csv"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = '';
          if (file) {
            upload(file);
          }
        }}
      />
      {error && (
        <p className="form-error edit-bar-message" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="form-success edit-bar-message" role="status">
          Added {result.added} {result.added === 1 ? 'change' : 'changes'} to version {release.version}. Use Edit next to
          a change to add its screenshots.
          {result.warnings.length > 0 && (
            <ul className="warning-list">
              {result.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </>
  );
}

// Admins: delete the whole version, its changes and screenshots, after typing the version number to confirm.
export function DeleteReleaseButton({ release, onDeleted }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const remove = async () => {
    const answer = window.prompt(
      `Delete version ${release.version} and all ${release.items.length} of its changes and screenshots? This can't be undone.

Type the version number to confirm:`
    );
    if (answer?.trim() !== release.version) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await edit.deleteRelease(release.id);
      onDeleted(release.id);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <>
      <button type="button" className="button button-danger-ghost" disabled={busy} onClick={remove}>
        {busy ? 'Deleting…' : 'Delete version'}
      </button>
      {error && (
        <p className="form-error edit-bar-message" role="alert">
          {error}
        </p>
      )}
    </>
  );
}

const splitAddresses = (text) =>
  text
    .split(/[,;\s]+/)
    .map((address) => address.trim())
    .filter(Boolean);

const DELIVERY_NOTES = {
  smtp: 'Sent',
  file: 'Saved as an .eml file in the server’s sent_emails folder (local test mode: not delivered)',
  console: 'Printed in the server console (no mail server configured: not delivered)',
};

// Admins: email this release's notes as an attached HTML file, or download that file.
export function ReleaseEmailPanel({ release, onClose }) {
  const [form, setForm] = useState({ to: '', cc: '', message: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }));

  const run = async (call) => {
    setBusy(true);
    setError(null);
    try {
      return await call();
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const send = async (event) => {
    event.preventDefault();
    setResult(null);
    const sent = await run(() =>
      edit.emailReleaseNotes(release.id, { to: splitAddresses(form.to), cc: splitAddresses(form.cc), message: form.message })
    );
    if (sent) {
      setResult(sent);
      setForm((current) => ({ ...current, to: '', cc: '' }));
    }
  };

  return (
    <form className="edit-panel" onSubmit={send}>
      <p className="field-hint">
        The notes for version {release.version} are attached as an HTML file, with a plain-text copy in the email
        and a link to this page for screenshots.
      </p>
      <div className="review-meta review-meta-wide">
        <label className="field field-wide">
          <span>To (separate addresses with commas)</span>
          <input className="input" type="text" value={form.to} onChange={set('to')} required placeholder="name@company.com" />
        </label>
        <label className="field field-wide">
          <span>Cc (optional)</span>
          <input className="input" type="text" value={form.cc} onChange={set('cc')} />
        </label>
        <label className="field field-wide">
          <span>Message (optional, shown above the notes)</span>
          <textarea className="input" rows={3} value={form.message} onChange={set('message')} maxLength={2000} />
        </label>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <p className="form-success" role="status">
          {DELIVERY_NOTES[result.delivery] ?? 'Sent'} to {result.recipients.join(', ')}, with {result.attachment} attached.
        </p>
      )}
      <div className="edit-actions">
        <button type="button" className="button button-secondary" onClick={() => run(() => edit.downloadReleaseNotes(release.id))} disabled={busy}>
          Download attachment
        </button>
        <span className="edit-actions-spacer" />
        <button type="button" className="button button-ghost" onClick={onClose} disabled={busy}>
          Close
        </button>
        <button type="submit" className="button button-primary" disabled={busy}>
          {busy ? 'Working…' : 'Send email'}
        </button>
      </div>
    </form>
  );
}

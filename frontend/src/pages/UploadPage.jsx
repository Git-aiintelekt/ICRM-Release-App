import { useEffect, useRef, useState } from 'react';
import BitbucketDraft from '../components/BitbucketDraft';
import { useAuth } from '../context/AuthContext';
import { useProduct } from '../context/ProductContext';
import { CATEGORIES, CATEGORY_ORDER, SAMPLE_CSV_URL, SAMPLE_DOC_URL, versionAnchor } from '../lib/releaseFormat';
import { Link, navigate } from '../lib/router';
import { parseReleaseDocument, publishRelease } from '../services/adminReleaseService';

const today = () => new Date().toISOString().slice(0, 10);
const toLines = (text) =>
  text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

// The review's editable copy of a parsed document or a Bitbucket draft (both have the same shape).
const toDraft = (parsed) => ({
  ...parsed,
  version: parsed.version ?? '',
  releaseDate: parsed.releaseDate ?? today(),
  plannedLabel: parsed.plannedLabel ?? '',
  summary: parsed.summary ?? '',
  highlightsText: parsed.highlights.join('\n'),
  knownIssuesText: parsed.knownIssues.join('\n'),
  upgradeNotesText: parsed.upgradeNotes.join('\n'),
  parsedVersion: parsed.version ?? '',
  items: parsed.items.map((item, index) => ({ ...item, key: index })),
});

const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

// A screenshot picked in the review becomes a data: URL, the same form the Word parser returns.
function readImage(file) {
  if (!IMAGE_TYPES.includes(file.type)) {
    return Promise.reject(new Error('Screenshots must be PNG, JPEG, GIF or WebP.'));
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return Promise.reject(new Error('The screenshot is larger than 5 MB.'));
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({ dataUrl: reader.result, caption: '' });
    reader.onerror = () => reject(new Error(`Couldn't read ${file.name}.`));
    reader.readAsDataURL(file);
  });
}

function DropZone({ onFile, busy }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div
      className={dragging ? 'dropzone dropzone-active' : 'dropzone'}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        const file = event.dataTransfer.files?.[0];
        if (file) {
          onFile(file);
        }
      }}
    >
      <svg className="dropzone-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6M12 18v-6M9 15l3-3 3 3" />
      </svg>
      <p className="dropzone-title">{busy ? 'Reading file…' : 'Drop a Word document or CSV file here'}</p>
      <p className="dropzone-hint">
        .docx (screenshots included) or .csv (wording only, add screenshots in the review), up to 10 MB
      </p>
      <div className="dropzone-actions">
        <button type="button" className="button button-primary" disabled={busy} onClick={() => inputRef.current?.click()}>
          Choose file
        </button>
        <a className="button button-secondary" href={SAMPLE_DOC_URL} download>
          Sample Word document
        </a>
        <a className="button button-secondary" href={SAMPLE_CSV_URL} download>
          Sample CSV
        </a>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".docx,.csv,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/csv"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = '';
          if (file) {
            onFile(file);
          }
        }}
      />
    </div>
  );
}

function FormatGuide() {
  return (
    <div className="format-guide">
      <div className="format-columns">
        <div>
          <h2>Required</h2>
          <ul className="check-list">
            <li>
              <strong>Version number</strong>, e.g. a title line <code>iCRM Release 11.1</code>
            </li>
            <li>
              <strong>At least one change</strong>, as a bullet under a heading such as <em>What&apos;s New</em> or{' '}
              <em>Bug Fixes</em>, or a row in a Jira table
            </li>
          </ul>
          <h2>Optional</h2>
          <ul className="check-list optional">
            <li>
              <code>Status: Coming soon</code> and <code>Planned release: October 2026</code> for a release that
              hasn&apos;t shipped yet
            </li>
            <li>
              A release date, e.g. <code>Released on September 28, 2026</code> (default: today)
            </li>
            <li>A summary paragraph under the title</li>
            <li>
              <em>Highlights</em>, <em>Known issues</em> and <em>Upgrade notes</em> sections
            </li>
            <li>
              Screenshots: a picture under a change belongs to that change; pictures under <em>Screenshots</em> go in
              the release&apos;s gallery. Add a caption line starting <code>Screenshot:</code>
            </li>
            <li>
              A <em>Jira list</em> table with <strong>Jira</strong>, <strong>Category</strong>, <strong>Title</strong>{' '}
              and <strong>Description</strong> columns
            </li>
          </ul>
        </div>
        <div>
          <h2>Layout</h2>
          <pre>{`iCRM Release 11.1
Status: Coming soon
Planned release: October 2026
One-paragraph summary of the release.

Highlights
  • Short points shown at the top
What's New
  • CT-363: Custom Field API – searchGroup support
      ◦ nested bullet becomes the description
      [screenshot]
Improvements / Bug Fixes / Security
  • CT-377 updateCustomerB returns E112
Jira list      (table: Jira | Category | Title | Description)
Known issues
Upgrade notes
Screenshots    (pictures for the gallery)
About this template   ← ignored, for instructions`}</pre>
          <p>
            The easiest start is the <a href={SAMPLE_DOC_URL} download>sample document</a>: it uses every option above
            and can be uploaded as-is to try it. You can correct anything in the preview before publishing.
          </p>
          <h2>CSV instead</h2>
          <p>
            One change per row, with a header row. Only <strong>Title</strong> is required; the others are optional:{' '}
            <code>Version</code>, <code>Release date</code>, <code>Status</code>, <code>Planned release</code>,{' '}
            <code>Category</code> (New, Improved, Fixed or Security), <code>Jira ID</code>, <code>Description</code>.
            The &ldquo;Release changes (CSV)&rdquo; export uses the same columns. After the wording loads, add
            screenshots, highlights and notes in the review. See the <a href={SAMPLE_CSV_URL} download>sample CSV</a>.
          </p>
        </div>
      </div>
    </div>
  );
}

function ImageStrip({ images, onChange, label, addLabel = 'Add screenshot' }) {
  const inputRef = useRef(null);
  const [error, setError] = useState(null);

  const add = async (files) => {
    setError(null);
    try {
      onChange([...images, ...(await Promise.all(files.map(readImage)))]);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <>
      <div className="image-strip" aria-label={label}>
        {images.map((image, index) => (
          <figure key={index} className="image-edit">
            <img src={image.dataUrl} alt={image.caption || `Screenshot ${index + 1}`} />
            <input
              className="input input-subtle"
              value={image.caption ?? ''}
              placeholder="Caption (optional)"
              aria-label={`Caption for screenshot ${index + 1}`}
              maxLength={255}
              onChange={(event) =>
                onChange(images.map((img, i) => (i === index ? { ...img, caption: event.target.value } : img)))
              }
            />
            <button
              type="button"
              className="icon-button image-remove"
              aria-label={`Remove screenshot ${index + 1}`}
              onClick={() => onChange(images.filter((_, i) => i !== index))}
            >
              ×
            </button>
          </figure>
        ))}
      </div>
      <div className="screenshot-add">
        <button type="button" className="link-button" onClick={() => inputRef.current?.click()}>
          + {addLabel}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={IMAGE_TYPES.join(',')}
          multiple
          hidden
          onChange={(event) => {
            const files = [...(event.target.files ?? [])];
            event.target.value = '';
            if (files.length) {
              add(files);
            }
          }}
        />
        {error && (
          <span className="form-error" role="alert">
            {error}
          </span>
        )}
      </div>
    </>
  );
}

function UploadPage() {
  const { user, checking } = useAuth();
  const { product } = useProduct();
  const productName = product?.label ?? 'iCRM';
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState(null);
  const [publishing, setPublishing] = useState(false);
  const [published, setPublished] = useState(null);

  useEffect(() => {
    if (!checking && !user) {
      navigate('/login?next=/upload', { replace: true });
    }
  }, [checking, user]);

  if (checking || !user) {
    return <p className="status-text page">Checking your access…</p>;
  }

  if (!user.isAdmin) {
    return (
      <div className="page">
        <div className="notice-card">
          <h1>Admin access required</h1>
          <p>
            You are signed in as <strong>{user.email ?? user.username}</strong>, but uploading release notes needs
            membership in the <code>FULLADMIN</code> security group. Ask an administrator to grant it.
          </p>
          <Link to="/" className="button button-secondary">
            Back to release notes
          </Link>
        </div>
      </div>
    );
  }

  const handleFile = async (file) => {
    setError(null);
    setPublished(null);
    if (!/\.(docx|csv)$/i.test(file.name)) {
      setError('Please choose a Word document (.docx) or a CSV file (.csv). Save older .doc files as .docx first.');
      return;
    }
    setParsing(true);
    try {
      setDraft(toDraft(await parseReleaseDocument(file)));
    } catch (err) {
      setError(err.message);
    } finally {
      setParsing(false);
    }
  };

  const updateDraft = (changes) => setDraft((current) => ({ ...current, ...changes }));
  const updateItem = (key, changes) =>
    setDraft((current) => ({
      ...current,
      items: current.items.map((item) => (item.key === key ? { ...item, ...changes } : item)),
    }));
  const removeItem = (key) =>
    setDraft((current) => ({ ...current, items: current.items.filter((item) => item.key !== key) }));

  const handlePublish = async (event) => {
    event.preventDefault();
    setError(null);
    setPublishing(true);
    try {
      const upcoming = draft.status === 'UPCOMING';
      const release = await publishRelease({
        fileName: draft.fileName,
        version: draft.version.trim(),
        releaseDate: draft.releaseDate,
        status: draft.status,
        plannedLabel: upcoming ? draft.plannedLabel.trim() || null : null,
        summary: draft.summary.trim(),
        highlights: toLines(draft.highlightsText),
        knownIssues: toLines(draft.knownIssuesText),
        upgradeNotes: toLines(draft.upgradeNotesText),
        images: draft.images,
        items: draft.items.map(({ category, title, description, jiraId, images }) => ({
          category,
          title: title.trim(),
          description: description?.trim() || null,
          jiraId: jiraId?.trim() || null,
          images,
        })),
        // Drafted from Bitbucket: the screens are limited to these release branches once it's published.
        branches: (draft.source?.repositories ?? []).map(({ repository, branch }) => ({ repository, branch })),
      });
      setPublished(release);
      setDraft(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setPublishing(false);
    }
  };

  const countByCategory = (key) => draft?.items.filter((item) => item.category === key).length ?? 0;
  const screenshotCount = draft ? draft.images.length + draft.items.reduce((n, i) => n + i.images.length, 0) : 0;
  // Uploads only create new versions; the server refuses an existing one too.
  const versionTaken = Boolean(draft?.existingVersion && draft.version.trim() === draft.parsedVersion);
  const missing = draft
    ? [
        !draft.version.trim() && 'a version number',
        versionTaken && 'a version number that doesn’t exist yet',
        draft.items.length === 0 && 'at least one change',
        draft.items.some((i) => !i.title.trim()) && 'a title for every change',
      ].filter(Boolean)
    : [];

  return (
    <div className="page upload-page">
      <section className="page-hero">
        <p className="eyebrow">Admin</p>
        <h1>Upload release notes</h1>
        <p className="page-lede">
          Upload a Word document with what&apos;s new, improvements, bug fixes and screenshots, or a CSV file with just
          the wording. Review what was found, add or change screenshots, then publish it, as a released version or as
          one that&apos;s coming soon.
        </p>
        <p className="field-hint">
          Publishing to <strong>{productName}</strong>. Pick another product in the header to publish there.
        </p>
      </section>

      {published && (
        <div className="success-card" role="status">
          <p>
            <strong>
              {productName} {published.version}
            </strong>{' '}
            is published
            {published.status === 'UPCOMING' ? ' as coming soon' : ''} with {published.items.length} changes.
          </p>
          <Link to={`/#${versionAnchor(published.version)}`} className="button button-primary">
            View release notes
          </Link>
        </div>
      )}

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {!draft && (
        <>
          <DropZone onFile={handleFile} busy={parsing} />
          <BitbucketDraft
            onDraft={(parsed) => {
              setError(null);
              setPublished(null);
              setDraft(toDraft(parsed));
            }}
          />
          <FormatGuide />
        </>
      )}

      {draft && (
        <form className="review" onSubmit={handlePublish}>
          <div className="review-header">
            <div>
              <h2>Review {draft.fileName}</h2>
              <p className="review-counts">
                {draft.items.length} changes
                {CATEGORY_ORDER.map((key) =>
                  countByCategory(key) ? (
                    <span key={key} className={`note-label note-label-${key.toLowerCase()}`}>
                      {countByCategory(key)} {CATEGORIES[key].label}
                    </span>
                  ) : null
                )}
                {screenshotCount > 0 && <span className="note-count">{screenshotCount} screenshots</span>}
              </p>
            </div>
            <button type="button" className="button button-ghost" onClick={() => setDraft(null)}>
              Start over
            </button>
          </div>

          {draft.warnings.length > 0 && (
            <ul className="warning-list">
              {draft.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
          {draft.source?.repositories.length > 0 && (
            <p className="settings-hint">
              Once published, the Bitbucket, Commits &amp; Pull Requests and Dashboard pages show only the release
              branches ({[...new Set(draft.source.repositories.map((r) => r.branch))].join(', ')}), with each
              version&apos;s own commits. Deleting the release takes them out again.
            </p>
          )}

          <fieldset className="review-block">
            <legend>Release details</legend>
            <div className="review-meta review-meta-wide">
              <label className="field">
                <span>
                  Version <em className="required">required</em>
                </span>
                <input
                  className="input"
                  value={draft.version}
                  onChange={(event) => updateDraft({ version: event.target.value })}
                  placeholder="11.1"
                  required
                />
              </label>
              <label className="field">
                <span>Status</span>
                <select
                  className="input"
                  value={draft.status}
                  onChange={(event) => updateDraft({ status: event.target.value })}
                >
                  <option value="RELEASED">Released</option>
                  <option value="UPCOMING">Coming soon</option>
                </select>
              </label>
              {draft.status === 'UPCOMING' && (
                <label className="field">
                  <span>Planned for</span>
                  <input
                    className="input"
                    value={draft.plannedLabel}
                    onChange={(event) => updateDraft({ plannedLabel: event.target.value })}
                    placeholder="October 2026"
                    maxLength={100}
                  />
                </label>
              )}
              <label className="field">
                <span>{draft.status === 'UPCOMING' ? 'Expected date' : 'Release date'}</span>
                <input
                  className="input"
                  type="date"
                  value={draft.releaseDate}
                  onChange={(event) => updateDraft({ releaseDate: event.target.value })}
                  required
                />
              </label>
              <label className="field field-wide">
                <span>Summary</span>
                <textarea
                  className="input"
                  rows={3}
                  value={draft.summary}
                  onChange={(event) => updateDraft({ summary: event.target.value })}
                  maxLength={1000}
                />
              </label>
            </div>

            {versionTaken && (
              <p className="form-error" role="alert">
                Version {draft.version} already exists. An upload can only add a new version. To change {draft.version}, use
                Edit / Delete next to its changes on the Release Notes page, or delete the whole version there first and
                upload it again.
              </p>
            )}

            <p className="field-hint">The released version with the highest number is marked Latest automatically.</p>
          </fieldset>

          <fieldset className="review-block">
            <legend>Highlights, known issues and upgrade notes (one per line, optional)</legend>
            <div className="review-meta review-meta-three">
              <label className="field">
                <span>Highlights</span>
                <textarea
                  className="input"
                  rows={4}
                  value={draft.highlightsText}
                  onChange={(event) => updateDraft({ highlightsText: event.target.value })}
                />
              </label>
              <label className="field">
                <span>Known issues</span>
                <textarea
                  className="input"
                  rows={4}
                  value={draft.knownIssuesText}
                  onChange={(event) => updateDraft({ knownIssuesText: event.target.value })}
                />
              </label>
              <label className="field">
                <span>Upgrade notes</span>
                <textarea
                  className="input"
                  rows={4}
                  value={draft.upgradeNotesText}
                  onChange={(event) => updateDraft({ upgradeNotesText: event.target.value })}
                />
              </label>
            </div>
          </fieldset>

          <fieldset className="review-block">
            <legend>Screenshot gallery (optional)</legend>
            <ImageStrip
              images={draft.images}
              label="Release screenshots"
              addLabel="Add to gallery"
              onChange={(images) => updateDraft({ images })}
            />
          </fieldset>

          <div className="review-table-wrap">
            <table className="review-table">
              <thead>
                <tr>
                  <th scope="col">Type</th>
                  <th scope="col">Jira</th>
                  <th scope="col">Title, description and screenshots</th>
                  <th scope="col">
                    <span className="visually-hidden">Remove</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {draft.items.map((item) => (
                  <tr key={item.key}>
                    <td>
                      <select
                        className="input"
                        value={item.category}
                        aria-label="Type"
                        onChange={(event) => updateItem(item.key, { category: event.target.value })}
                      >
                        {CATEGORY_ORDER.map((key) => (
                          <option key={key} value={key}>
                            {CATEGORIES[key].label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        className="input input-mono"
                        value={item.jiraId ?? ''}
                        aria-label="Jira ID"
                        placeholder="—"
                        maxLength={20}
                        onChange={(event) => updateItem(item.key, { jiraId: event.target.value })}
                      />
                    </td>
                    <td className="review-text">
                      <input
                        className="input"
                        value={item.title}
                        aria-label="Title"
                        maxLength={500}
                        onChange={(event) => updateItem(item.key, { title: event.target.value })}
                      />
                      <input
                        className="input input-subtle"
                        value={item.description ?? ''}
                        aria-label="Description"
                        placeholder="Add a description (optional)"
                        maxLength={1000}
                        onChange={(event) => updateItem(item.key, { description: event.target.value })}
                      />
                      <ImageStrip
                        images={item.images}
                        label={`Screenshots for ${item.title}`}
                        onChange={(images) => updateItem(item.key, { images })}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Remove ${item.title}`}
                        onClick={() => removeItem(item.key)}
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
                {draft.items.length === 0 && (
                  <tr>
                    <td colSpan={4} className="empty-cell">
                      No changes found. At least one is required.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="review-actions">
            {missing.length > 0 && <p className="field-hint">Still needed: {missing.join(', ')}.</p>}
            <button type="submit" className="button button-primary" disabled={missing.length > 0 || publishing}>
              {publishing
                ? 'Publishing…'
                : `Publish ${productName} ${draft.version || ''}${draft.status === 'UPCOMING' ? ' as coming soon' : ''}`}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

export default UploadPage;

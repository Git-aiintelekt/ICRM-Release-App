import { useState } from 'react';
import { CATEGORIES, CATEGORY_ORDER, JIRA_BROWSE_URL, formatReleaseDate, versionAnchor } from '../lib/releaseFormat';
import { deleteItem } from '../services/adminReleaseEditService';
import { CsvImportButton, DeleteReleaseButton, ItemEditor, ReleaseDetailsEditor, ReleaseEmailPanel, ScreenshotManager } from './ReleaseEditors';
import ScreenshotMedia from './ScreenshotMedia';

const COLLAPSED_COUNT = 8;

function Screenshots({ images, className = 'screenshot-grid' }) {
  if (!images?.length) {
    return null;
  }
  return (
    <div className={className}>
      {images.map((image) => (
        <figure key={image.id} className="screenshot">
          <ScreenshotMedia image={image} className="screenshot-video" lazy />
          {image.caption && <figcaption>{image.caption}</figcaption>}
        </figure>
      ))}
    </div>
  );
}

function NoteList({ title, lines, className }) {
  if (!lines?.length) {
    return null;
  }
  return (
    <section className={`note-section ${className}`}>
      <h3 className="note-section-heading">{title}</h3>
      <ul className="plain-list">
        {lines.map((line, index) => (
          <li key={index}>{line}</li>
        ))}
      </ul>
    </section>
  );
}

function ReleaseItemRow({ item, canEdit, onEdit, onDelete, busy }) {
  return (
    <li className="note-item">
      <span className={`note-label note-label-${item.category.toLowerCase()}`}>
        {CATEGORIES[item.category]?.label ?? item.category}
      </span>
      <div className="note-body">
        <p className="note-title">
          {item.title}
          {/* The Jira number links to Jira for the release manager (admin) only; others see it as plain text. */}
          {item.jiraId &&
            (canEdit ? (
              <a
                className="jira-chip"
                href={`${JIRA_BROWSE_URL}${item.jiraId}`}
                target="_blank"
                rel="noreferrer"
                title={`Open ${item.jiraId} in Jira`}
              >
                {item.jiraId}
              </a>
            ) : (
              <span className="jira-chip jira-chip-plain">{item.jiraId}</span>
            ))}
          {canEdit && (
            <>
              <button type="button" className="edit-chip" onClick={onEdit} disabled={busy} aria-label={`Edit ${item.title}`}>
                Edit
              </button>
              <button
                type="button"
                className="edit-chip edit-chip-danger"
                onClick={onDelete}
                disabled={busy}
                aria-label={`Delete ${item.title}`}
              >
                Delete
              </button>
            </>
          )}
        </p>
        {item.description && <p className="note-description">{item.description}</p>}
        <Screenshots images={item.images} className="screenshot-row" />
      </div>
    </li>
  );
}

function CategorySection({ category, items, forceExpanded, canEdit, editingItemId, setEditingItemId, releaseId, onSaved }) {
  const [expanded, setExpanded] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState(null);
  const showAll = expanded || forceExpanded || items.length <= COLLAPSED_COUNT;
  const visible = showAll ? items : items.slice(0, COLLAPSED_COUNT);

  // Admins: remove one change (and its screenshots) straight from the list.
  const remove = async (item) => {
    if (!window.confirm(`Delete "${item.title}" and its screenshots from this release? This can't be undone.`)) {
      return;
    }
    setDeletingId(item.id);
    setError(null);
    try {
      onSaved(await deleteItem(item.id));
    } catch (err) {
      setError(err.message);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <section className="note-section">
      <h3 className="note-section-heading">
        {CATEGORIES[category].heading}
        <span className="note-count">{items.length}</span>
      </h3>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <ul className="note-list">
        {visible.map((item) =>
          canEdit && editingItemId === item.id ? (
            <li key={item.id} className="note-item-editing">
              <ItemEditor releaseId={releaseId} item={item} onSaved={onSaved} onClose={() => setEditingItemId(null)} />
            </li>
          ) : (
            <ReleaseItemRow
              key={item.id}
              item={item}
              canEdit={canEdit}
              busy={deletingId === item.id}
              onEdit={() => setEditingItemId(item.id)}
              onDelete={() => remove(item)}
            />
          )
        )}
      </ul>
      {!showAll && (
        <button type="button" className="link-button" onClick={() => setExpanded(true)}>
          Show all {items.length} {CATEGORIES[category].heading.toLowerCase()}
        </button>
      )}
    </section>
  );
}

function releaseWhen(release) {
  if (release.status === 'UPCOMING') {
    return release.plannedLabel ? `Planned for ${release.plannedLabel}` : 'Coming soon';
  }
  return `Released on ${formatReleaseDate(release.releaseDate)}`;
}

function ReleaseEntry({ release, items, filtering, canEdit, onChange, onDeleted }) {
  const anchor = versionAnchor(release.version);
  const upcoming = release.status === 'UPCOMING';
  const [editing, setEditing] = useState(false);
  const [editingDetails, setEditingDetails] = useState(false);
  const [editingItemId, setEditingItemId] = useState(null); // an item id, 'new', or null
  const [emailing, setEmailing] = useState(false);

  const stopEditing = () => {
    setEditing(false);
    setEditingDetails(false);
    setEditingItemId(null);
  };

  return (
    <article
      className={[
        'release-entry',
        upcoming && 'release-entry-upcoming',
        editing && 'release-entry-editing',
      ]
        .filter(Boolean)
        .join(' ')}
      id={anchor}
      aria-labelledby={`${anchor}-title`}
    >
      <header className="release-entry-header">
        <h2 id={`${anchor}-title`}>
          <a href={`#${anchor}`} className="anchor-link">
            Version {release.version}
          </a>
          {upcoming && <span className="upcoming-badge">Coming soon</span>}
          {release.isLatest && !upcoming && <span className="latest-badge">Latest</span>}
          {canEdit && (
            <button
              type="button"
              className={emailing ? 'button button-primary edit-toggle' : 'button button-secondary edit-toggle'}
              onClick={() => setEmailing((open) => !open)}
              aria-expanded={emailing}
            >
              Email / download
            </button>
          )}
          {canEdit && (
            <button
              type="button"
              className={editing ? 'button button-primary edit-toggle-next' : 'button button-secondary edit-toggle-next'}
              onClick={() => (editing ? stopEditing() : setEditing(true))}
            >
              {editing ? 'Done editing' : 'Edit release'}
            </button>
          )}
        </h2>
        <p className="release-date">
          {upcoming ? (
            releaseWhen(release)
          ) : (
            <>
              Released on <time dateTime={release.releaseDate}>{formatReleaseDate(release.releaseDate)}</time>
            </>
          )}
          <span className="dot" aria-hidden="true">·</span>
          {release.items.length} {upcoming ? 'planned changes' : 'changes'}
        </p>
        {canEdit && emailing && <ReleaseEmailPanel release={release} onClose={() => setEmailing(false)} />}
        {editing && editingDetails ? (
          <ReleaseDetailsEditor
            release={release}
            onSaved={onChange}
            onDeleted={onDeleted}
            onClose={() => setEditingDetails(false)}
          />
        ) : (
          <>
            {release.description && <p className="release-summary">{release.description}</p>}
            {upcoming && (
              <p className="upcoming-note">This release hasn&apos;t shipped yet. Details may change before it does.</p>
            )}
            {editing && (
              <div className="edit-bar">
                <button type="button" className="button button-secondary" onClick={() => setEditingDetails(true)}>
                  Edit details, highlights and notes
                </button>
                <button type="button" className="button button-secondary" onClick={() => setEditingItemId('new')}>
                  Add a change
                </button>
                <CsvImportButton release={release} onSaved={onChange} />
                <DeleteReleaseButton release={release} onDeleted={onDeleted} />
                <span className="field-hint">Use Edit or Delete next to any change to update or remove just that one.</span>
              </div>
            )}
          </>
        )}
      </header>

      {editing && editingItemId === 'new' && (
        <div className="note-section">
          <ItemEditor releaseId={release.id} onSaved={onChange} onClose={() => setEditingItemId(null)} />
        </div>
      )}

      {!filtering && release.highlights?.length > 0 && (
        <section className="highlights" aria-label="Highlights">
          <h3>Highlights</h3>
          <ul>
            {release.highlights.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        </section>
      )}

      {editing ? (
        <section className="note-section">
          <h3 className="note-section-heading">Screenshot gallery</h3>
          <ScreenshotManager releaseId={release.id} images={release.images} onSaved={onChange} label="Add to gallery" />
        </section>
      ) : (
        !filtering && <Screenshots images={release.images} />
      )}

      {CATEGORY_ORDER.map((category) => {
        const categoryItems = items.filter((item) => item.category === category);
        return categoryItems.length > 0 ? (
          <CategorySection
            key={category}
            category={category}
            items={categoryItems}
            forceExpanded={filtering || editing}
            canEdit={canEdit}
            editingItemId={editingItemId}
            setEditingItemId={setEditingItemId}
            releaseId={release.id}
            onSaved={onChange}
          />
        ) : null;
      })}

      {!filtering && (
        <>
          <NoteList title="Known issues" lines={release.knownIssues} className="known-issues" />
          <NoteList title="Upgrade notes" lines={release.upgradeNotes} className="upgrade-notes" />
        </>
      )}
    </article>
  );
}

export default ReleaseEntry;

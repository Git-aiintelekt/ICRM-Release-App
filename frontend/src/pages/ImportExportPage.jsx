import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { SAMPLE_DOC_URL } from '../lib/releaseFormat';
import { getReleases } from '../services/releaseService';
import UploadPage from './UploadPage';

function download(fileName, type, text) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

const csvCell = (value) => {
  const text = value === null || value === undefined ? '' : String(value);
  // Quote every cell; a leading = + - @ is prefixed so spreadsheets don't run it as a formula.
  return `"${(/^[=+\-@]/.test(text) ? `'${text}` : text).replace(/"/g, '""')}"`;
};

function toCsv(releases) {
  const rows = [['Version', 'Release date', 'Status', 'Latest', 'Category', 'Jira ID', 'Title', 'Description']];
  releases.forEach((release) =>
    release.items.forEach((item) =>
      rows.push([release.version, release.releaseDate, release.status, release.isLatest ? 'yes' : '', item.category, item.jiraId, item.title, item.description])
    )
  );
  return `﻿${rows.map((row) => row.map(csvCell).join(',')).join('\r\n')}\r\n`;
}

// Export: release notes as JSON/CSV (from the same /api/releases the Release Notes page reads) and the
// sample Word document. Nothing here changes data.
function ExportPanel() {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const stamp = new Date().toISOString().slice(0, 10);

  const exportAs = async (format) => {
    setBusy(format);
    setError(null);
    try {
      const releases = await getReleases();
      if (format === 'json') {
        download(`icrm-release-notes-${stamp}.json`, 'application/json', JSON.stringify(releases, null, 2));
      } else {
        download(`icrm-release-notes-${stamp}.csv`, 'text/csv;charset=utf-8', toCsv(releases));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="page export-panel" aria-labelledby="export-heading">
      <h2 id="export-heading">Export</h2>
      <p className="settings-hint">Download the release notes.</p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="export-actions">
        <button type="button" className="button button-secondary" disabled={busy !== null} onClick={() => exportAs('json')}>
          {busy === 'json' ? 'Preparing…' : 'Release notes (JSON)'}
        </button>
        <button type="button" className="button button-secondary" disabled={busy !== null} onClick={() => exportAs('csv')}>
          {busy === 'csv' ? 'Preparing…' : 'Release changes (CSV)'}
        </button>
        <a className="button button-ghost" href={SAMPLE_DOC_URL} download>
          Sample Word document
        </a>
      </div>
    </section>
  );
}

// Import / Export: the existing Word upload, unchanged, followed by the export options.
function ImportExportPage() {
  const { user } = useAuth();
  return (
    <>
      <UploadPage />
      {user?.isAdmin && <ExportPanel />}
    </>
  );
}

export default ImportExportPage;

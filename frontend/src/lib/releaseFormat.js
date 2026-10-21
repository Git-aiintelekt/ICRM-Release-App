export const JIRA_BROWSE_URL = 'https://groupfio.atlassian.net/browse/';

// Downloadable example for the Upload page (public/samples/).
export const SAMPLE_DOC_URL = '/samples/iCRM-Release-11.1-sample.docx';
export const SAMPLE_CSV_URL = '/samples/iCRM-Release-sample.csv';

export const CATEGORY_ORDER = ['NEW_FEATURE', 'IMPROVEMENT', 'BUG_FIX', 'SECURITY'];

export const CATEGORIES = {
  NEW_FEATURE: { label: 'New', heading: "What's new" },
  IMPROVEMENT: { label: 'Improved', heading: 'Improvements' },
  BUG_FIX: { label: 'Fixed', heading: 'Bug fixes' },
  SECURITY: { label: 'Security', heading: 'Security' },
};

export function versionAnchor(version) {
  return `icrm-v${version.replace(/[^0-9A-Za-z]/g, '')}`;
}

export function formatReleaseDate(isoDate) {
  const [year, month, day] = isoDate.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

// Per-browser page theme: follow the system, white, black, or any custom background colour.
const STORAGE_KEY = 'icrm-theme';

export const PRESET_COLORS = ['#0f172a', '#1e3a5f', '#14532d', '#4a1d2e', '#f5f0e6', '#e8f1fb'];

export function loadTheme() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null');
    if (saved?.mode) {
      return { mode: saved.mode, color: saved.color ?? '#1e3a5f' };
    }
  } catch {
    // Storage blocked or corrupted: fall back to the system theme.
  }
  return { mode: 'system', color: '#1e3a5f' };
}

// WCAG relative luminance; above ~0.179 dark text reads better than light text.
function isLightColor(hex) {
  const n = parseInt(hex.slice(1), 16);
  const lin = (c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(n >> 16) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255) > 0.179;
}

export function applyTheme({ mode, color }) {
  const root = document.documentElement;
  delete root.dataset.custom;
  root.style.removeProperty('--custom-bg');
  if (mode === 'light' || mode === 'dark') {
    root.dataset.theme = mode;
  } else if (mode === 'custom' && /^#[0-9a-f]{6}$/i.test(color)) {
    root.dataset.theme = isLightColor(color) ? 'light' : 'dark';
    root.dataset.custom = '';
    root.style.setProperty('--custom-bg', color);
  } else {
    delete root.dataset.theme;
  }
}

export function saveTheme(theme) {
  applyTheme(theme);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(theme));
  } catch {
    // The choice still applies for this visit.
  }
}

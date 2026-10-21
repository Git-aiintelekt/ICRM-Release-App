import { useEffect, useRef, useState } from 'react';
import { PRESET_COLORS, loadTheme, saveTheme } from '../lib/theme';

const MODES = [
  { id: 'system', label: 'System' },
  { id: 'light', label: 'White' },
  { id: 'dark', label: 'Black' },
  { id: 'custom', label: 'Custom colour' },
];

function ThemeMenu() {
  const [theme, setTheme] = useState(loadTheme);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onPointer = (event) => {
      if (!wrapRef.current?.contains(event.target)) {
        setOpen(false);
      }
    };
    const onKey = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const update = (changes) => {
    const next = { ...theme, ...changes };
    setTheme(next);
    saveTheme(next);
  };

  return (
    <div className="theme-menu" ref={wrapRef}>
      <button
        type="button"
        className="icon-button theme-toggle"
        aria-label="Change background colour"
        aria-expanded={open}
        aria-haspopup="dialog"
        title="Background colour"
        onClick={() => setOpen((value) => !value)}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="8.5" />
          <path d="M12 3.5a8.5 8.5 0 0 1 0 17z" className="theme-toggle-fill" />
        </svg>
      </button>

      {open && (
        <div className="theme-popover" role="dialog" aria-label="Background colour">
          <p className="theme-popover-title">Background</p>
          <div className="theme-modes" role="radiogroup" aria-label="Background">
            {MODES.map((mode) => (
              <button
                key={mode.id}
                type="button"
                role="radio"
                aria-checked={theme.mode === mode.id}
                className={theme.mode === mode.id ? 'theme-mode active' : 'theme-mode'}
                onClick={() => update({ mode: mode.id })}
              >
                <span className={`theme-swatch theme-swatch-${mode.id}`} style={mode.id === 'custom' ? { background: theme.color } : undefined} />
                {mode.label}
              </button>
            ))}
          </div>

          {theme.mode === 'custom' && (
            <div className="theme-custom">
              <div className="theme-presets">
                {PRESET_COLORS.map((color) => (
                  <button
                    key={color}
                    type="button"
                    className={theme.color === color ? 'theme-preset active' : 'theme-preset'}
                    style={{ background: color }}
                    aria-label={`Use ${color}`}
                    onClick={() => update({ color })}
                  />
                ))}
              </div>
              <label className="theme-picker">
                <input type="color" value={theme.color} onChange={(event) => update({ color: event.target.value })} />
                <span>Pick any colour</span>
                <code>{theme.color}</code>
              </label>
            </div>
          )}
          <p className="theme-note">Saved in this browser only.</p>
        </div>
      )}
    </div>
  );
}

export default ThemeMenu;

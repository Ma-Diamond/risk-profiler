import { useState } from "react";
import { LANGUAGES, t } from "./i18n";

// Global language control, lives in the header — changes the AI
// chat's language (via the backend, mid-conversation if one's already
// running) and the app's own UI text together, so the two never fall
// out of sync the way a chat-only or landing-only picker would.
export default function LanguagePicker({ language, onChange }) {
  const [open, setOpen] = useState(false);
  const current = LANGUAGES.find((l) => l.code === language) || LANGUAGES[0];

  return (
    <div className="language-picker">
      <button
        type="button"
        className="language-picker__trigger"
        onClick={() => setOpen((o) => !o)}
        aria-label={t(language, "header.chooseLanguage")}
      >
        <span>{current.flag}</span>
      </button>

      {open && (
        <>
          <div className="language-picker__scrim" onClick={() => setOpen(false)} />
          <div className="language-picker__dropdown card">
            {LANGUAGES.map((l) => (
              <button
                key={l.code}
                type="button"
                className={`language-picker__option ${l.code === language ? "language-picker__option--active" : ""}`}
                onClick={() => {
                  onChange(l.code);
                  setOpen(false);
                }}
              >
                <span className="language-picker__flag">{l.flag}</span>
                {l.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

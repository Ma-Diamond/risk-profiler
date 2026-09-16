import { useState } from "react";
import { t } from "./i18n";
import ShieldMark from "./ShieldMark";

export default function LandingPage({ onStart, language }) {
  const [input, setInput] = useState("");

  const submit = (text) => {
    onStart(text);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    submit(input.trim());
  };

  const pills = t(language, "landing.pills");

  return (
    <div className="landing-shell">
      <div className="landing-content">
        <div className="landing-mark">
          <ShieldMark />
        </div>

        <h1 className="landing-headline">{t(language, "landing.headline")}</h1>
        <p className="landing-subtext">{t(language, "landing.subtext")}</p>

        <form className="landing-search" onSubmit={handleSubmit}>
          <input
            className="landing-search__input"
            placeholder={t(language, "landing.placeholder")}
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button type="submit" className="landing-search__submit" aria-label="Send">
            →
          </button>
        </form>

        <div className="landing-pills">
          {Object.entries(pills).map(([key, label]) => (
            <button key={key} type="button" className="landing-pill" onClick={() => submit(label)}>
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

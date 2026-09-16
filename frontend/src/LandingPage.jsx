import { useState } from "react";
import { t } from "./i18n";
import ShieldMark from "./ShieldMark";

const SpeechRecognitionAPI =
  typeof window !== "undefined" ? window.SpeechRecognition || window.webkitSpeechRecognition : null;

export default function LandingPage({ onStart, language }) {
  const [input, setInput] = useState("");
  const [listening, setListening] = useState(false);

  const submit = (text) => {
    onStart(text);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    submit(input.trim());
  };

  // One-shot voice input for the very first message — speak, and it
  // submits automatically once you stop talking. This is the entry
  // point into the chat, not a full voice conversation yet; once
  // inside the chat, tapping its own mic button starts the ongoing
  // back-and-forth voice mode.
  const startVoiceInput = () => {
    if (!SpeechRecognitionAPI || listening) return;
    const recognition = new SpeechRecognitionAPI();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    let transcript = "";

    recognition.onresult = (event) => {
      transcript = "";
      for (let i = 0; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      setInput(transcript);
    };

    recognition.onerror = () => setListening(false);

    recognition.onend = () => {
      setListening(false);
      if (transcript.trim()) submit(transcript.trim());
    };

    try {
      recognition.start();
      setListening(true);
    } catch {
      setListening(false);
    }
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
            placeholder={listening ? t(language, "chat.listening") : t(language, "landing.placeholder")}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={listening}
          />
          {SpeechRecognitionAPI && (
            <button
              type="button"
              className={`landing-search__mic ${listening ? "landing-search__mic--active" : ""}`}
              onClick={startVoiceInput}
              aria-label={listening ? "Listening" : "Speak instead"}
              title={listening ? "Listening…" : "Speak instead"}
            >
              {listening ? "🔴" : "🎙️"}
            </button>
          )}
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

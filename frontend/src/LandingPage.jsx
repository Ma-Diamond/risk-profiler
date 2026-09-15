import { useState } from "react";

// Placeholder mark — a clean generic shield, not a trace of the real
// Standard Bank logo (that's proprietary artwork; if you have the
// actual logo file, drop it in and swap this for an <img>).
function ShieldMark() {
  return (
    <svg viewBox="0 0 48 48" width="40" height="40" aria-hidden="true">
      <path
        d="M24 4 L42 10 V22 C42 33 34.5 41.5 24 45 C13.5 41.5 6 33 6 22 V10 Z"
        fill="var(--accent)"
      />
      <path d="M24 4 L42 10 V22 C42 33 34.5 41.5 24 45 Z" fill="var(--accent-ink)" opacity="0.25" />
    </svg>
  );
}

const LANGUAGES = [
  { code: "en", label: "English", flag: "🇬🇧" },
  { code: "zu", label: "isiZulu", flag: "🇿🇦" },
  { code: "sw", label: "Swahili", flag: "🇰🇪" },
  { code: "ig", label: "Igbo", flag: "🇳🇬" },
  { code: "pt", label: "Portuguese", flag: "🇵🇹" },
];

// Static copy for the landing page itself, per language. The rest of
// the app isn't translated yet (see /topics/risk-profiler-app.md-style
// notes) — this is deliberately scoped to just this screen for now.
const COPY = {
  en: {
    headline: "Hi! I'm your Standard Bank AI Financial Guide.",
    subtext: "Tell me what you're hoping to achieve, and I'll help you understand your options, in your language.",
    placeholder: "How can I help you today?",
    chooseLanguage: "Choose your language",
    pills: { retirement: "Retirement", investments: "Investments", protection: "Protection", savings: "Savings" },
  },
  pt: {
    headline: "Olá! Sou o seu Guia Financeiro de IA do Standard Bank.",
    subtext: "Diga-me o que espera alcançar, e eu ajudo a entender as suas opções, no seu idioma.",
    placeholder: "Como posso ajudar hoje?",
    chooseLanguage: "Escolha o seu idioma",
    pills: { retirement: "Reforma", investments: "Investimentos", protection: "Proteção", savings: "Poupança" },
  },
  sw: {
    headline: "Habari! Mimi ni Mwongozo wako wa Kifedha wa AI wa Standard Bank.",
    subtext: "Niambie unachotaka kufikia, nami nitakusaidia kuelewa chaguo zako, kwa lugha yako.",
    placeholder: "Ninawezaje kukusaidia leo?",
    chooseLanguage: "Chagua lugha yako",
    pills: { retirement: "Ustaafu", investments: "Uwekezaji", protection: "Ulinzi", savings: "Akiba" },
  },
  zu: {
    headline: "Sawubona! Ngingumhlahlandlela wakho we-AI wezezimali we-Standard Bank.",
    subtext: "Ngitshele ofuna ukukufeza, futhi ngizokusiza uqonde izinketho zakho, ngolimi lwakho.",
    placeholder: "Ngingakusiza kanjani namuhla?",
    chooseLanguage: "Khetha ulimi lwakho",
    pills: { retirement: "Umhlalaphansi", investments: "Ukutshala imali", protection: "Ukuvikela", savings: "Ukonga" },
  },
  ig: {
    headline: "Ndewo! Abụ m Onye Ndụmọdụ Ego AI nke Standard Bank gị.",
    subtext: "Gwa m ihe ị na-achọ imezu, m ga-enyere gị aka ịghọta nhọrọ gị, n'asụsụ gị.",
    placeholder: "Kedu ka m ga-esi nyere gị aka taa?",
    chooseLanguage: "Họrọ asụsụ gị",
    pills: { retirement: "Ezumike ọgụgụ", investments: "Itinye ego", protection: "Nchekwa", savings: "Ịchekwa ego" },
  },
};

export default function LandingPage({ onStart }) {
  const [language, setLanguage] = useState("en");
  const [input, setInput] = useState("");
  const [showLanguagePicker, setShowLanguagePicker] = useState(false);

  const copy = COPY[language] || COPY.en;
  const currentLanguage = LANGUAGES.find((l) => l.code === language);

  const submit = (text) => {
    onStart(text, language);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    submit(input.trim());
  };

  return (
    <div className="landing-shell">
      <div className="landing-content">
        <div className="landing-mark">
          <ShieldMark />
        </div>

        <h1 className="landing-headline">{copy.headline}</h1>
        <p className="landing-subtext">{copy.subtext}</p>

        <form className="landing-search" onSubmit={handleSubmit}>
          <input
            className="landing-search__input"
            placeholder={copy.placeholder}
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button type="submit" className="landing-search__submit" aria-label="Send">
            →
          </button>
        </form>

        <div className="landing-pills">
          {Object.entries(copy.pills).map(([key, label]) => (
            <button key={key} type="button" className="landing-pill" onClick={() => submit(label)}>
              {label}
            </button>
          ))}
        </div>

        <div className="landing-language">
          <button
            type="button"
            className="landing-language__trigger"
            onClick={() => setShowLanguagePicker((v) => !v)}
          >
            <span>{currentLanguage.flag}</span>
            <span>{copy.chooseLanguage}</span>
          </button>
          {showLanguagePicker && (
            <div className="landing-language__options">
              {LANGUAGES.map((l) => (
                <button
                  key={l.code}
                  type="button"
                  className={`landing-language__option ${l.code === language ? "landing-language__option--active" : ""}`}
                  onClick={() => {
                    setLanguage(l.code);
                    setShowLanguagePicker(false);
                  }}
                >
                  <span className="landing-language__flag">{l.flag}</span>
                  {l.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

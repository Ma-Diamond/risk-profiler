import { useEffect, useRef, useState } from "react";

const API_BASE = "http://localhost:8000";

const TRACKED_FIELDS = [
  { key: "goals", label: "Goals" },
  { key: "dependents", label: "Dependents" },
  { key: "gross_monthly_income", label: "Income" },
  { key: "monthly_expenses", label: "Expenses" },
  { key: "tax_bracket", label: "Tax bracket" },
];

export default function ChatPanel({ quickProfile, sessionId, setSessionId, extracted, setExtracted, onContinue }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (sessionId) return;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/chat/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ known_context: quickProfile }),
        });
        const data = await res.json();
        setSessionId(data.session_id);
        setMessages([{ role: "assistant", text: data.reply }]);
      } catch {
        setError("Couldn't start the conversation — check the API is running.");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setSending(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/chat/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Request failed");
      const data = await res.json();
      setMessages((m) => [...m, { role: "assistant", text: data.reply }]);
      setExtracted(data.extracted);
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  };

  const uploadStatement = async (file) => {
    setSending(true);
    setError(null);
    setMessages((m) => [...m, { role: "user", text: `Uploaded: ${file.name}`, isFile: true }]);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/chat/sessions/${sessionId}/upload-statement`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Upload failed");
      const data = await res.json();
      setMessages((m) => [...m, { role: "assistant", text: data.reply }]);
      setExtracted(data.extracted);
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  };

  const fieldsKnown = TRACKED_FIELDS.filter((f) => extracted[f.key] != null && extracted[f.key] !== "");

  return (
    <div className="step-content step-content--enter">
      <header className="step-header">
        <span className="pill">Step 2 of 3</span>
        <h2>A few more details</h2>
        <p className="step-subtitle">
          Tell us in your own words — or upload a bank statement and we'll estimate income and expenses for you to confirm.
        </p>
      </header>

      <div className="chat-layout">
        <div className="chat-panel card">
          <div className="chat-panel__messages" ref={scrollRef}>
            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble chat-bubble--${m.role} ${m.isFile ? "chat-bubble--file" : ""}`}>
                {m.text}
              </div>
            ))}
            {sending && (
              <div className="chat-bubble chat-bubble--assistant chat-bubble--typing">
                <span /><span /><span />
              </div>
            )}
          </div>

          {error && <p className="field-error chat-panel__error">{error}</p>}

          <div className="chat-panel__composer">
            <button
              type="button"
              className="btn btn-ghost chat-panel__upload-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={!sessionId || sending}
              title="Upload bank statement (PDF)"
            >
              📎
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              hidden
              onChange={(e) => {
                if (e.target.files?.[0]) uploadStatement(e.target.files[0]);
                e.target.value = "";
              }}
            />
            <input
              className="text-input chat-panel__input"
              placeholder="Type your answer…"
              value={input}
              disabled={!sessionId || sending}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            />
            <button className="btn btn-primary" onClick={sendMessage} disabled={!sessionId || sending}>
              Send
            </button>
          </div>
        </div>

        <aside className="extracted-panel card">
          <h4 className="extracted-panel__title">What we've learned</h4>
          {fieldsKnown.length === 0 && (
            <p className="extracted-panel__empty">Nothing yet — keep chatting.</p>
          )}
          <ul className="extracted-panel__list">
            {fieldsKnown.map((f) => (
              <li key={f.key}>
                <span className="extracted-panel__check">✓</span>
                <span className="extracted-panel__label">{f.label}</span>
                <span className="extracted-panel__value mono">
                  {Array.isArray(extracted[f.key]) ? extracted[f.key].join(", ") : String(extracted[f.key])}
                </span>
              </li>
            ))}
          </ul>
        </aside>
      </div>

      <div className="step-actions">
        <button className="btn btn-primary" onClick={onContinue} disabled={!sessionId}>
          See my risk matrix
        </button>
      </div>
    </div>
  );
}

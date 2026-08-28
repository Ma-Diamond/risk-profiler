import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import RiskRatingWidget from "./RiskRatingWidget";

const API_BASE = "http://localhost:8000";

/**
 * The chat is now the entire interaction — before results exist it
 * fills the screen collecting the client's full profile; after
 * results exist, the same component gets docked into a sidebar
 * (desktop) or a bottom sheet (mobile) by App.jsx, and switches to
 * answering "what if" questions instead.
 *
 * Exposes via ref:
 *  - sendProgrammaticMessage(text) — used by the summary popup's
 *    "Looks good" button.
 *  - resumeSession(sessionId, messages) — used when continuing a past
 *    profile from history: loads an existing session's reconstructed
 *    transcript instead of starting a new one.
 *  - startFresh() — used on login/logout to reset to a brand new guest
 *    (or newly-authenticated) session rather than leaving the UI
 *    pointed at a session the current identity may not own.
 */
const ChatPanel = forwardRef(function ChatPanel(
  { sessionId, setSessionId, authToken, onFinalized, onRecalculated, onSummary, hasResults },
  ref
) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [pendingRiskWidget, setPendingRiskWidget] = useState(null);
  const fileInputRef = useRef(null);
  const scrollRef = useRef(null);

  const authHeaders = () => (authToken ? { Authorization: `Bearer ${authToken}` } : {});

  useEffect(() => {
    if (sessionId) return;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/chat/sessions`, {
          method: "POST",
          headers: authHeaders(),
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
  }, [messages, pendingRiskWidget]);

  const handleTurnResponse = (data) => {
    setMessages((m) => [...m, { role: "assistant", text: data.reply }]);
    if (data.risk_widget) {
      setPendingRiskWidget(data.risk_widget);
    }
    if (data.profile_summary) {
      onSummary(data.profile_summary);
    }
    if (data.finalized_result) {
      onFinalized(data.finalized_result);
      setMessages((m) => [
        ...m,
        {
          role: "hint",
          text: 'You can keep asking questions here — try things like "What if I invested R500 more a month?", "What if I only invested for 10 years?", or "Which product has the lowest fees?"',
        },
      ]);
    }
    if (data.recalculated_projections && data.recalculated_projections.length > 0) {
      onRecalculated(data.recalculated_projections);
    }
  };

  const sendRaw = async (text) => {
    setMessages((m) => [...m, { role: "user", text }]);
    setSending(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/chat/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ message: text }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Request failed");
      handleTurnResponse(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  };

  useImperativeHandle(ref, () => ({
    sendProgrammaticMessage: (text) => sendRaw(text),

    resumeSession: (newSessionId, newMessages) => {
      setSessionId(newSessionId);
      setMessages(newMessages);
      setPendingRiskWidget(null);
      setError(null);
    },

    startFresh: () => {
      setSessionId(null);
      setMessages([]);
      setPendingRiskWidget(null);
      setError(null);
      (async () => {
        try {
          const res = await fetch(`${API_BASE}/chat/sessions`, {
            method: "POST",
            headers: authHeaders(),
          });
          const data = await res.json();
          setSessionId(data.session_id);
          setMessages([{ role: "assistant", text: data.reply }]);
        } catch {
          setError("Couldn't start the conversation — check the API is running.");
        }
      })();
    },
  }));

  const sendMessage = () => {
    if (!input.trim() || sending || !sessionId) return;
    const text = input.trim();
    setInput("");
    sendRaw(text);
  };

  const submitRiskRatings = async (ratings) => {
    setMessages((m) => [
      ...m,
      { role: "user", text: `Risk ratings: ${ratings.join(", ")}` },
    ]);
    setPendingRiskWidget(null);
    setSending(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/chat/sessions/${sessionId}/risk-ratings`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ ratings }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Request failed");
      handleTurnResponse(await res.json());
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
        headers: authHeaders(),
        body: formData,
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Upload failed");
      handleTurnResponse(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="chat-panel-wrap">
      <div className="chat-panel__messages" ref={scrollRef}>
        {messages.map((m, i) => (
          <div key={i} className={`chat-bubble chat-bubble--${m.role} ${m.isFile ? "chat-bubble--file" : ""}`}>
            {m.text}
          </div>
        ))}
        {pendingRiskWidget && (
          <RiskRatingWidget
            questions={pendingRiskWidget.questions}
            onSubmit={submitRiskRatings}
            disabled={sending}
          />
        )}
        {sending && (
          <div className="chat-bubble chat-bubble--assistant chat-bubble--typing">
            <span /><span /><span />
          </div>
        )}
      </div>

      {error && <p className="field-error chat-panel__error">{error}</p>}

      <div className="chat-panel__composer">
        {!hasResults && (
          <>
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
          </>
        )}
        <input
          className="text-input chat-panel__input"
          placeholder={hasResults ? "Ask a question, e.g. what if I invest more?" : "Type your answer…"}
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
  );
});

export default ChatPanel;

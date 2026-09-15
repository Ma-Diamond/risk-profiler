import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import RiskRatingWidget from "./RiskRatingWidget";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

const SpeechRecognitionAPI =
  typeof window !== "undefined" ? window.SpeechRecognition || window.webkitSpeechRecognition : null;

const ChatPanel = forwardRef(function ChatPanel(
  { sessionId, setSessionId, authToken, onFinalized, onRecalculated, onSummary, hasResults },
  ref
) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [pendingRiskWidget, setPendingRiskWidget] = useState(null);
  const [isListening, setIsListening] = useState(false);
  const [voiceOutputEnabled, setVoiceOutputEnabled] = useState(false);
  const [intakeProgress, setIntakeProgress] = useState(null); // { completed, total } | null
  const fileInputRef = useRef(null);
  const scrollRef = useRef(null);
  const recognitionRef = useRef(null);
  const audioRef = useRef(null);
  const transcriptRef = useRef("");

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

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
      audioRef.current?.pause();
    };
  }, []);

  const sendRawRef = useRef(null);

  const toggleListening = () => {
    if (!SpeechRecognitionAPI) return;

    if (isListening) {
      recognitionRef.current?.stop();
      return;
    }

    transcriptRef.current = "";
    const recognition = new SpeechRecognitionAPI();
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onresult = (event) => {
      let transcript = "";
      for (let i = 0; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      transcriptRef.current = transcript;
      setInput(transcript);
    };

    recognition.onerror = () => setIsListening(false);

    recognition.onend = () => {
      setIsListening(false);
      const finalText = transcriptRef.current.trim();
      if (finalText) {
        setInput("");
        sendRawRef.current?.(finalText);
      }
    };

    try {
      recognition.start();
      recognitionRef.current = recognition;
      setIsListening(true);
    } catch {
      setIsListening(false);
    }
  };

  const speakText = async (text) => {
    if (!voiceOutputEnabled || !text) return;
    try {
      audioRef.current?.pause();
      const res = await fetch(`${API_BASE}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        setError(`Voice output failed: ${detail.detail || res.status}`);
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      audioRef.current = audio;
      try {
        await audio.play();
      } catch (playErr) {
        setError(`Voice output couldn't play: ${playErr.message}`);
      }
    } catch (e) {
      setError(`Voice output failed: ${e.message}`);
    }
  };

  const handleTurnResponse = (data) => {
    setMessages((m) => [...m, { role: "assistant", text: data.reply }]);
    speakText(data.reply);
    setIntakeProgress(data.intake_progress || null);
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
    if (data.nudge) {
      const amount = data.nudge.surplus_amount;
      const rounded = Math.round(amount).toLocaleString();
      setMessages((m) => [
        ...m,
        {
          role: "nudge",
          text: `💰 Looks like you could have about R${rounded} left over this month.`,
          ctaLabel: "Show me what that could grow into",
          ctaMessage: `What would investing an extra R${amount} a month grow into?`,
        },
      ]);
    }
  };

  const sendRaw = async (text, overrideSessionId) => {
    const sid = overrideSessionId ?? sessionId;
    setMessages((m) => [...m, { role: "user", text }]);
    setSending(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/chat/sessions/${sid}/messages`, {
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

  sendRawRef.current = sendRaw;

  useImperativeHandle(ref, () => ({
    sendProgrammaticMessage: (text) => sendRaw(text),

    resumeSession: (newSessionId, newMessages) => {
      setSessionId(newSessionId);
      setMessages(newMessages);
      setPendingRiskWidget(null);
      setError(null);
      setIntakeProgress(null); // a resumed session either already has results, or the next turn will re-report it
    },

    startFresh: () => {
      setSessionId(null);
      setMessages([]);
      setPendingRiskWidget(null);
      setError(null);
      setIntakeProgress(null);
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

    // Used by the landing page: starts a brand-new session in the
    // chosen language, and — if the person typed something or tapped a
    // suggestion pill instead of leaving it blank — immediately sends
    // that as the first message. Passing the new session id straight
    // into sendRaw (rather than relying on the sessionId state, which
    // wouldn't have updated yet inside this same synchronous flow)
    // avoids sending to a stale/missing session.
    startWithMessage: (text, language) => {
      setSessionId(null);
      setMessages([]);
      setPendingRiskWidget(null);
      setError(null);
      setIntakeProgress(null);
      (async () => {
        try {
          const res = await fetch(`${API_BASE}/chat/sessions`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...authHeaders() },
            body: JSON.stringify({ language: language || "en" }),
          });
          const data = await res.json();
          setSessionId(data.session_id);
          setMessages([{ role: "assistant", text: data.reply }]);
          if (text && text.trim()) {
            sendRaw(text.trim(), data.session_id);
          }
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

  const simulateMonthEnd = () => {
    if (!sessionId || sending) return;
    sendRaw("It's the end of the month — can you check if I have any spare cash to invest?");
  };

  const toggleVoiceOutput = () => {
    setVoiceOutputEnabled((v) => {
      if (v) audioRef.current?.pause();
      return !v;
    });
  };

  return (
    <div className="chat-panel-wrap">
      {!hasResults && intakeProgress && (
        <div className="intake-progress" title={`${intakeProgress.completed} of ${intakeProgress.total} done`}>
          <div
            className="intake-progress__bar"
            style={{ width: `${Math.round((intakeProgress.completed / intakeProgress.total) * 100)}%` }}
          />
        </div>
      )}
      <div className="chat-panel__messages" ref={scrollRef}>
        {messages.map((m, i) =>
          m.role === "nudge" ? (
            <div key={i} className="chat-bubble chat-bubble--nudge">
              <p>{m.text}</p>
              <button
                type="button"
                className="btn btn-primary chat-nudge__cta"
                onClick={() => sendRaw(m.ctaMessage)}
                disabled={sending}
              >
                {m.ctaLabel}
              </button>
            </div>
          ) : (
            <div key={i} className={`chat-bubble chat-bubble--${m.role} ${m.isFile ? "chat-bubble--file" : ""}`}>
              {m.text}
            </div>
          )
        )}
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
        {hasResults && (
          <button
            type="button"
            className="btn btn-ghost chat-panel__upload-btn"
            onClick={simulateMonthEnd}
            disabled={!sessionId || sending}
            title="Simulate month-end balance check"
          >
            💰
          </button>
        )}
        <button
          type="button"
          className={`btn btn-ghost chat-panel__voice-toggle ${voiceOutputEnabled ? "chat-panel__voice-toggle--active" : ""}`}
          onClick={toggleVoiceOutput}
          title={voiceOutputEnabled ? "Turn off spoken replies" : "Turn on spoken replies"}
        >
          {voiceOutputEnabled ? "🔊" : "🔇"}
        </button>
        {SpeechRecognitionAPI && (
          <button
            type="button"
            className={`btn btn-ghost chat-panel__mic-btn ${isListening ? "chat-panel__mic-btn--active" : ""}`}
            onClick={toggleListening}
            disabled={!sessionId || sending}
            title={isListening ? "Stop listening (sends automatically)" : "Speak your message"}
          >
            {isListening ? "🔴" : "🎤"}
          </button>
        )}
        <input
          className="text-input chat-panel__input"
          placeholder={
            isListening ? "Listening…" : hasResults ? "Ask a question, e.g. what if I invest more?" : "Type your answer…"
          }
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

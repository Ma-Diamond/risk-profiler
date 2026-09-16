import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import RiskRatingWidget from "./RiskRatingWidget";
import { t } from "./i18n";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

const SpeechRecognitionAPI =
  typeof window !== "undefined" ? window.SpeechRecognition || window.webkitSpeechRecognition : null;

const ChatPanel = forwardRef(function ChatPanel(
  { sessionId, setSessionId, authToken, onFinalized, onRecalculated, onSummary, hasResults, language },
  ref
) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [pendingRiskWidget, setPendingRiskWidget] = useState(null);
  const [voiceMode, setVoiceMode] = useState(false);
  const [intakeProgress, setIntakeProgress] = useState(null); // { completed, total } | null
  const fileInputRef = useRef(null);
  const scrollRef = useRef(null);
  const textareaRef = useRef(null);
  const recognitionRef = useRef(null);
  const audioRef = useRef(null);
  const transcriptRef = useRef("");
  const voiceModeRef = useRef(false);
  const autoNudgeFiredRef = useRef(false);

  const authHeaders = () => (authToken ? { Authorization: `Bearer ${authToken}` } : {});

  useEffect(() => {
    if (sessionId) return;
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

  // Auto-grow the composer textarea to fit what's typed, instead of
  // scrolling the text sideways/cutting it off — capped so a very long
  // paste doesn't take over the screen; it scrolls internally past that.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [input]);

  // Once results are shown, simulate a proactive "we noticed you have
  // spare cash" check a couple of seconds in — this replaces the old
  // manual money-icon trigger, which people couldn't tell the purpose
  // of. Fires at most once per results view.
  useEffect(() => {
    if (!hasResults || !sessionId || autoNudgeFiredRef.current) return;
    autoNudgeFiredRef.current = true;
    const timer = setTimeout(() => {
      sendRawRef.current?.("It's the end of the month — can you check if I have any spare cash to invest?", undefined, true);
    }, 2500);
    return () => clearTimeout(timer);
  }, [hasResults, sessionId]);

  const sendRawRef = useRef(null);

  const startListening = () => {
    if (!SpeechRecognitionAPI) return;
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

    recognition.onerror = () => {
      recognitionRef.current = null;
      if (voiceModeRef.current) {
        // Transient errors (e.g. a brief silence timeout) shouldn't
        // drop the whole conversation out of voice mode — just retry.
        setTimeout(() => {
          if (voiceModeRef.current) startListening();
        }, 800);
      }
    };

    recognition.onend = () => {
      recognitionRef.current = null;
      const finalText = transcriptRef.current.trim();
      setInput("");
      if (finalText) {
        sendRawRef.current?.(finalText);
        // Listening resumes automatically once the reply has been
        // spoken — see speakText's onended handler below.
      } else if (voiceModeRef.current) {
        setTimeout(() => {
          if (voiceModeRef.current) startListening();
        }, 500);
      }
    };

    try {
      recognition.start();
      recognitionRef.current = recognition;
    } catch {
      // Already running or briefly unavailable — the retry paths above cover it.
    }
  };

  const stopListening = () => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
  };

  // Browsers block audio.play() calls that don't happen inside a
  // direct user-gesture handler (a click) — by the time a TTS reply
  // comes back, it's arriving from an async fetch chain that started
  // from speech recognition ending, which no longer counts as a
  // direct gesture as far as autoplay policy is concerned. Playing a
  // silent clip synchronously right here, inside the actual button
  // click, unlocks this SAME <audio> element for the rest of the
  // session so later programmatic play() calls (from speakText) are
  // allowed.
  const unlockAudioPlayback = () => {
    const el = getAudioEl();
    el.src =
      "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
    el.play().catch(() => {
      // If even this is blocked, speakText's own play() will fail
      // too and surface a clear message rather than failing silently.
    });
  };

  const getAudioEl = () => {
    if (!audioRef.current) {
      audioRef.current = new Audio();
    }
    return audioRef.current;
  };

  const toggleVoiceMode = () => {
    setVoiceMode((v) => {
      const next = !v;
      voiceModeRef.current = next;
      if (next) {
        unlockAudioPlayback();
        startListening();
      } else {
        stopListening();
        audioRef.current?.pause();
      }
      return next;
    });
  };

  const speakText = async (text) => {
    if (!voiceModeRef.current || !text) return;
    try {
      const res = await fetch(`${API_BASE}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        setError(`Voice output failed: ${detail.detail || res.status}`);
        if (voiceModeRef.current) startListening();
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const el = getAudioEl();
      el.onended = () => {
        URL.revokeObjectURL(url);
        // Continue the voice conversation: listen again once the
        // reply has finished playing, unless voice mode was turned
        // off while it was speaking.
        if (voiceModeRef.current) startListening();
      };
      el.src = url;
      try {
        await el.play();
      } catch (playErr) {
        URL.revokeObjectURL(url);
        setError(
          "Your browser blocked voice playback — tap the mic button again to restart the voice conversation (the text reply is still shown above)."
        );
        // Keep the conversation going even without audio — the reply
        // text is already in the chat, so listening again still works.
        if (voiceModeRef.current) startListening();
      }
    } catch (e) {
      setError(`Voice output failed: ${e.message}`);
      if (voiceModeRef.current) startListening();
    }
  };

  const handleTurnResponse = (data, silent) => {
    if (!silent) {
      setMessages((m) => [...m, { role: "assistant", text: data.reply }]);
    }
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
    if (data.recalculated_products) {
      onRecalculated(data.recalculated_products, data.recalculated_note);
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

  // `silent`: used by the automatic end-of-month nudge check — the
  // trigger phrase itself isn't shown as a user bubble (it wasn't
  // something the person actually said), but the AI's reply/nudge
  // still shows normally if it finds something worth mentioning.
  const sendRaw = async (text, overrideSessionId, silent) => {
    const sid = overrideSessionId ?? sessionId;
    if (!silent) {
      setMessages((m) => [...m, { role: "user", text }]);
    }
    setSending(!silent ? true : sending);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/chat/sessions/${sid}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ message: text }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Request failed");
      handleTurnResponse(await res.json(), silent);
    } catch (e) {
      if (!silent) setError(e.message);
    } finally {
      if (!silent) setSending(false);
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
      setIntakeProgress(null);
      autoNudgeFiredRef.current = false;
    },

    startFresh: () => {
      setSessionId(null);
      setMessages([]);
      setPendingRiskWidget(null);
      setError(null);
      setIntakeProgress(null);
      autoNudgeFiredRef.current = false;
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
        } catch {
          setError("Couldn't start the conversation — check the API is running.");
        }
      })();
    },

    startWithMessage: (text, language) => {
      setSessionId(null);
      setMessages([]);
      setPendingRiskWidget(null);
      setError(null);
      setIntakeProgress(null);
      autoNudgeFiredRef.current = false;
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
        {SpeechRecognitionAPI && (
          <button
            type="button"
            className={`btn btn-ghost chat-panel__voice-toggle ${voiceMode ? "chat-panel__voice-toggle--active" : ""}`}
            onClick={toggleVoiceMode}
            disabled={!sessionId || sending}
            title={voiceMode ? "End voice conversation" : "Start voice conversation"}
          >
            {voiceMode ? "🔴" : "🎙️"}
          </button>
        )}
        <textarea
          ref={textareaRef}
          rows={1}
          className="text-input chat-panel__input"
          placeholder={
            voiceMode
              ? t(language, "chat.listening")
              : hasResults
              ? t(language, "chat.placeholderResults")
              : t(language, "chat.placeholderIntake")
          }
          value={input}
          disabled={!sessionId || sending}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
            }
          }}
        />
        <button className="btn btn-primary" onClick={sendMessage} disabled={!sessionId || sending}>
          {t(language, "chat.send")}
        </button>
      </div>
    </div>
  );
});

export default ChatPanel;

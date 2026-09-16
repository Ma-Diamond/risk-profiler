import { useEffect, useState } from "react";
import { formatNotification, NOTIFICATION_TEMPLATES } from "./i18n";
import { BellIcon } from "./Icons";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

// Proactive nudges about EXISTING accounts (age, income growth vs.
// what's on file, a demo-only "worth a look" prompt) — distinct from
// the in-chat "spare cash" nudge, which only ever shows inside an
// already-open post-results session. Fetches once per mount/auth
// change; not real-time, refreshing the page picks up any change.
export default function NotificationBell({ authToken, language, onAsk }) {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);

  const copyDict = NOTIFICATION_TEMPLATES[language] || NOTIFICATION_TEMPLATES.en;

  useEffect(() => {
    if (!authToken) {
      setNotifications([]);
      return;
    }
    fetch(`${API_BASE}/notifications`, { headers: { Authorization: `Bearer ${authToken}` } })
      .then((r) => (r.ok ? r.json() : []))
      .then(setNotifications)
      .catch(() => setNotifications([]));
  }, [authToken]);

  if (!authToken) return null;

  return (
    <div className="notification-bell">
      <button
        type="button"
        className="notification-bell__trigger"
        onClick={() => setOpen((o) => !o)}
        aria-label={copyDict.title}
      >
        <BellIcon size={17} />
        {notifications.length > 0 && <span className="notification-bell__badge">{notifications.length}</span>}
      </button>

      {open && (
        <>
          <div className="notification-bell__scrim" onClick={() => setOpen(false)} />
          <div className="notification-bell__dropdown card">
            <p className="notification-bell__title">{copyDict.title}</p>
            {notifications.length === 0 && <p className="notification-bell__empty">{copyDict.empty}</p>}
            {notifications.map((n) => {
              const copy = formatNotification(language, n);
              return (
                <div key={n.id} className="notification-bell__item">
                  <p className="notification-bell__message">{copy.message}</p>
                  <button
                    type="button"
                    className="btn btn-primary notification-bell__cta"
                    onClick={() => {
                      setOpen(false);
                      onAsk(n.client_id, copy.ctaMessage);
                    }}
                  >
                    {copy.ctaLabel}
                  </button>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

import { useState } from "react";
import Portal from "./Portal";
import Toast from "./Toast";
import { t } from "./i18n";

// Placeholder number — swap for the real advisor line when available.
const ADVISOR_NUMBER = "0800 123 456";
const ADVISOR_TEL = "0800123456";

export default function AdvisorButton({ language }) {
  const [open, setOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  const requestCallback = () => {
    setOpen(false);
    setToastMessage(t(language, "advisor.requested"));
  };

  return (
    <div className="advisor-button">
      <button type="button" className="advisor-button__trigger" onClick={() => setOpen((o) => !o)}>
        <span className="advisor-button__icon">💬</span>
        <span className="advisor-button__label">{t(language, "advisor.trigger")}</span>
      </button>

      {open && (
        <Portal>
          <div className="modal-overlay" onClick={() => setOpen(false)}>
            <div className="modal-card card advisor-popover" onClick={(e) => e.stopPropagation()}>
              <h3 className="modal-card__title">{t(language, "advisor.title")}</h3>
              <p className="step-subtitle">{t(language, "advisor.subtitle")}</p>

              <a href={`tel:${ADVISOR_TEL}`} className="advisor-option" onClick={() => setOpen(false)}>
                <span className="advisor-option__icon">📞</span>
                <div className="advisor-option__text">
                  <strong>{t(language, "advisor.call")}</strong>
                  <span>{ADVISOR_NUMBER}</span>
                </div>
              </a>

              <button type="button" className="advisor-option" onClick={requestCallback}>
                <span className="advisor-option__icon">📲</span>
                <div className="advisor-option__text">
                  <strong>{t(language, "advisor.callback")}</strong>
                  <span>{t(language, "advisor.callbackSub")}</span>
                </div>
              </button>

              <div className="modal-card__actions">
                <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>
                  {t(language, "advisor.close")}
                </button>
              </div>
            </div>
          </div>
        </Portal>
      )}

      {toastMessage && <Toast message={toastMessage} onDismiss={() => setToastMessage(null)} />}
    </div>
  );
}

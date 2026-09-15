import { useState } from "react";
import Portal from "./Portal";
import Toast from "./Toast";

// Placeholder number — swap for the real advisor line when available.
const ADVISOR_NUMBER = "0800 123 456";
const ADVISOR_TEL = "0800123456";

export default function AdvisorButton() {
  const [open, setOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  const requestCallback = () => {
    setOpen(false);
    setToastMessage("Request received — an advisor will call you back shortly.");
  };

  return (
    <div className="advisor-button">
      <button type="button" className="advisor-button__trigger" onClick={() => setOpen((o) => !o)}>
        <span className="advisor-button__icon">💬</span>
        <span className="advisor-button__label">Talk to an Advisor</span>
      </button>

      {open && (
        <Portal>
          <div className="modal-overlay" onClick={() => setOpen(false)}>
            <div className="modal-card card advisor-popover" onClick={(e) => e.stopPropagation()}>
              <h3 className="modal-card__title">Talk to an advisor</h3>
              <p className="step-subtitle">Choose how you'd like to connect.</p>

              <a href={`tel:${ADVISOR_TEL}`} className="advisor-option" onClick={() => setOpen(false)}>
                <span className="advisor-option__icon">📞</span>
                <div className="advisor-option__text">
                  <strong>Call us</strong>
                  <span>{ADVISOR_NUMBER}</span>
                </div>
              </a>

              <button type="button" className="advisor-option" onClick={requestCallback}>
                <span className="advisor-option__icon">📲</span>
                <div className="advisor-option__text">
                  <strong>Request a callback</strong>
                  <span>We'll call you back shortly</span>
                </div>
              </button>

              <div className="modal-card__actions">
                <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>
                  Close
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

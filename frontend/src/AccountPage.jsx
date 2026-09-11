export default function AccountPage({ currentUser, onBack, onLogout, onGoToLogin }) {
  return (
    <div className="history-shell">
      <div className="history-card card">
        <div className="history-card__header">
          <h2>My account</h2>
          <button className="btn btn-ghost" onClick={onBack}>
            Back
          </button>
        </div>

        {currentUser ? (
          <>
            <div className="account-detail-row">
              <span className="field-label">Name</span>
              <span>{currentUser.full_name || "—"}</span>
            </div>
            <div className="account-detail-row">
              <span className="field-label">Email</span>
              <span>{currentUser.email}</span>
            </div>
            <button className="btn btn-ghost" onClick={onLogout}>
              Log out
            </button>
          </>
        ) : (
          <>
            <p className="step-subtitle">You're not logged in.</p>
            <button className="btn btn-primary" onClick={onGoToLogin}>
              Log in
            </button>
          </>
        )}
      </div>
    </div>
  );
}

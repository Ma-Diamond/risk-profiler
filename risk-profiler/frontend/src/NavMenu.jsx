import { useState } from "react";

export default function NavMenu({ currentUser, onNavigate, onLogout }) {
  const [open, setOpen] = useState(false);

  const go = (view) => {
    setOpen(false);
    onNavigate(view);
  };

  return (
    <div className="nav-menu">
      <button
        type="button"
        className="nav-menu__trigger"
        onClick={() => setOpen((o) => !o)}
        aria-label="Menu"
        aria-expanded={open}
      >
        <span className="nav-menu__bar" />
        <span className="nav-menu__bar" />
        <span className="nav-menu__bar" />
      </button>

      {open && (
        <>
          <div className="nav-menu__scrim" onClick={() => setOpen(false)} />
          <div className="nav-menu__dropdown card">
            <button className="nav-menu__item" onClick={() => go("home")}>
              Home
            </button>
            {currentUser && (
              <button className="nav-menu__item" onClick={() => go("history")}>
                My Profiles
              </button>
            )}
            <button className="nav-menu__item" onClick={() => go("account")}>
              Account
            </button>
            {currentUser ? (
              <button
                className="nav-menu__item nav-menu__item--danger"
                onClick={() => {
                  setOpen(false);
                  onLogout();
                }}
              >
                Log out
              </button>
            ) : (
              <button className="nav-menu__item" onClick={() => go("login")}>
                Log in
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

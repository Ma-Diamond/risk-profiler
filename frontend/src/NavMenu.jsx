import { useState } from "react";
import ShieldMark from "./ShieldMark";

const ITEMS = [
  { view: "home", label: "Home", icon: "🏠" },
  { view: "history", label: "My Profiles", icon: "📋", requiresAuth: true },
  { view: "accounts", label: "My Accounts", icon: "💼", requiresAuth: true },
  { view: "account", label: "Profile settings", icon: "⚙️" },
];

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
        {currentUser ? (
          <span className="nav-menu__trigger-avatar">{currentUser.full_name?.[0]?.toUpperCase() || "👤"}</span>
        ) : (
          <>
            <span className="nav-menu__bar" />
            <span className="nav-menu__bar" />
            <span className="nav-menu__bar" />
          </>
        )}
      </button>

      {open && (
        <>
          <div className="nav-menu__scrim" onClick={() => setOpen(false)} />
          <div className="nav-menu__dropdown card">
            <div className="nav-menu__header">
              <ShieldMark size={30} />
              <div className="nav-menu__header-text">
                <strong>{currentUser?.full_name || "Guest"}</strong>
                <span>{currentUser?.email || "Not logged in"}</span>
              </div>
            </div>

            <div className="nav-menu__items">
              {ITEMS.filter((item) => !item.requiresAuth || currentUser).map((item) => (
                <button key={item.view} className="nav-menu__item" onClick={() => go(item.view)}>
                  <span className="nav-menu__item-icon">{item.icon}</span>
                  {item.label}
                </button>
              ))}
            </div>

            <div className="nav-menu__footer">
              {currentUser ? (
                <button
                  className="nav-menu__item nav-menu__item--danger"
                  onClick={() => {
                    setOpen(false);
                    onLogout();
                  }}
                >
                  <span className="nav-menu__item-icon">🚪</span>
                  Log out
                </button>
              ) : (
                <button className="nav-menu__item nav-menu__item--primary" onClick={() => go("login")}>
                  <span className="nav-menu__item-icon">🔑</span>
                  Log in
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

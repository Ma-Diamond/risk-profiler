import { useEffect } from "react";

export default function Toast({ message, onDismiss }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 3200);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <div className="toast" role="status">
      <span className="toast__icon">✓</span>
      {message}
    </div>
  );
}

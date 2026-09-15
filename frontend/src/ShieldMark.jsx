// Placeholder mark — a clean generic shield, not a trace of the real
// Standard Bank logo (that's proprietary artwork; if you have the
// actual logo file, drop it in and swap this for an <img>). Shared
// between the landing page and the header so the brand mark is
// consistent everywhere it appears, not a different shape per screen.
export default function ShieldMark({ size = 40 }) {
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} aria-hidden="true">
      <path
        d="M24 4 L42 10 V22 C42 33 34.5 41.5 24 45 C13.5 41.5 6 33 6 22 V10 Z"
        fill="var(--accent)"
      />
      <path d="M24 4 L42 10 V22 C42 33 34.5 41.5 24 45 Z" fill="var(--accent-ink)" opacity="0.25" />
    </svg>
  );
}

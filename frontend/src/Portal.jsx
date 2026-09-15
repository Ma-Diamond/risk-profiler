// Renders children directly into document.body, bypassing whatever
// ancestor happens to be in the tree. This matters specifically
// because position: fixed is relative to the nearest ancestor with a
// CSS transform (not just the viewport) — and several of our card/
// step entrance animations apply a transform, so a "fixed" modal or
// toast nested inside one of those was rendering centered on THAT
// element's box instead of the actual viewport. A portal sidesteps
// this categorically rather than requiring every animated ancestor to
// avoid transform forever.
import { createPortal } from "react-dom";

export default function Portal({ children }) {
  return createPortal(children, document.body);
}

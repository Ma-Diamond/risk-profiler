import "./RiskLadder.css";

const BAND_LABELS = ["Conservative", "Cautious", "Balanced", "Growth", "Aggressive"];

/**
 * A 5-segment vertical ladder representing risk bands 1-5.
 * - `activeBand`: the governed band to fill up to (0 = nothing known yet)
 * - `markers`: optional { tolerance, capacity, horizon } bands (1-5) to show
 *    as small dots against the ladder, so the person can see which
 *    dimension is the binding constraint.
 * - `orientation`: 'vertical' (desktop rail) or 'horizontal' (mobile top bar)
 */
export default function RiskLadder({ activeBand = 0, markers = null, orientation = "vertical" }) {
  const bands = [5, 4, 3, 2, 1]; // top to bottom for vertical (aggressive at top)
  const displayBands = orientation === "horizontal" ? [1, 2, 3, 4, 5] : bands;

  return (
    <div className={`risk-ladder risk-ladder--${orientation}`}>
      {displayBands.map((band) => {
        const filled = activeBand >= band;
        const markerHere = markers
          ? Object.entries(markers).filter(([, v]) => v === band)
          : [];
        return (
          <div key={band} className="risk-ladder__segment">
            <div
              className={`risk-ladder__bar band-bg-${band} ${filled ? "is-filled" : "is-empty"}`}
              title={`Band ${band} — ${BAND_LABELS[band - 1]}`}
            >
              {markerHere.map(([dim]) => (
                <span key={dim} className="risk-ladder__marker" title={`${dim} lands here`} />
              ))}
            </div>
            {orientation === "vertical" && (
              <span className="risk-ladder__label">{BAND_LABELS[band - 1]}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

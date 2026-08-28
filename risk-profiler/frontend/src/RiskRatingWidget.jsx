import { useState } from "react";

const LABELS = ["Disagree", "", "", "", "Agree"];

export default function RiskRatingWidget({ questions, onSubmit, disabled }) {
  const [ratings, setRatings] = useState(Array(questions.length).fill(null));

  const setRating = (i, value) => {
    setRatings((r) => {
      const next = [...r];
      next[i] = value;
      return next;
    });
  };

  const allAnswered = ratings.every((r) => r !== null);

  return (
    <div className="risk-widget">
      {questions.map((q, i) => (
        <div key={i} className="risk-widget__row">
          <p className="risk-widget__question">{q}</p>
          <div className="risk-widget__scale">
            {[1, 2, 3, 4, 5].map((value) => (
              <label key={value} className="risk-widget__option">
                <input
                  type="radio"
                  name={`risk-q-${i}`}
                  checked={ratings[i] === value}
                  onChange={() => setRating(i, value)}
                  disabled={disabled}
                />
                <span className="risk-widget__radio-dot">{value}</span>
                {LABELS[value - 1] && <span className="risk-widget__scale-label">{LABELS[value - 1]}</span>}
              </label>
            ))}
          </div>
        </div>
      ))}
      <button
        className="btn btn-primary risk-widget__submit"
        disabled={!allAnswered || disabled}
        onClick={() => onSubmit(ratings)}
      >
        Submit ratings
      </button>
    </div>
  );
}

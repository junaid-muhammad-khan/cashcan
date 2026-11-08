"use client";

import { useState } from "react";

type Props = {
  id: string;
  label: string;
  hint?: string;
  type?: "text" | "email" | "password";
  value: string;
  error?: string;
  autoComplete?: string;
  onChange: (v: string) => void;
  onBlur?: () => void;
};

export default function Field({ id, label, hint, type = "text", value, error, autoComplete, onChange, onBlur }: Props) {
  const [show, setShow] = useState(false);
  const isPw = type === "password";
  const errId = `${id}-err`;
  const input = (
    <input
      id={id}
      name={id}
      type={isPw && show ? "text" : type}
      value={value}
      autoComplete={autoComplete}
      spellCheck={false}
      aria-invalid={error ? true : undefined}
      aria-describedby={error ? errId : undefined}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
    />
  );
  return (
    <div className="field">
      <label htmlFor={id}>
        {label} {hint && <span className="hint">({hint})</span>}
      </label>
      {isPw ? (
        <div className="pw-wrap">
          {input}
          <button type="button" className="pw-toggle" aria-pressed={show} aria-controls={id} onClick={() => setShow((s) => !s)}>
            {show ? "Hide" : "Show"}
          </button>
        </div>
      ) : (
        input
      )}
      {error && <p className="err" id={errId}>{error}</p>}
    </div>
  );
}

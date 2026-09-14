import { useId } from "react";

import { clampValue } from "./bounds";
import "./numeric-input.css";

export interface NumericInputProps {
  label: string;
  value: number;
  unit: string;
  min: number;
  max: number;
  step: number;
  onChange(value: number): void;
}

export function NumericInput({ label, value, unit, min, max, step, onChange }: NumericInputProps) {
  const id = useId();
  const helpId = `${id}-staged-help`;
  return (
    <div className="bw-numeric">
      <label className="bw-numeric__label" htmlFor={id}>{label}</label>
      <span className="bw-numeric__field">
        <input
          id={id}
          type="number"
          value={value}
          min={min}
          max={max}
          step={step}
          aria-describedby={helpId}
          onChange={(event) => {
            const candidate = event.currentTarget.valueAsNumber;
            if (Number.isFinite(candidate)) onChange(clampValue(candidate, min, max));
          }}
        />
        <span className="bw-numeric__unit">{unit}</span>
      </span>
      <span className="bw-numeric__help" id={helpId}>Staged value; use Apply to request the change</span>
    </div>
  );
}

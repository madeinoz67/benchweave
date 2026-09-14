import { stepValue } from "../inputs/bounds";
import "./rotary-control.css";

export interface RotaryControlProps {
  label: string;
  value: number;
  unit: string;
  min: number;
  max: number;
  step: number;
  onStage(value: number): void;
}

export function RotaryControl({ label, value, unit, min, max, step, onStage }: RotaryControlProps) {
  const angle = -135 + ((value - min) / (max - min)) * 270;
  return (
    <div className="bw-rotary">
      <button
        className="bw-rotary__knob"
        type="button"
        role="slider"
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={`${value} ${unit}, staged`}
        onKeyDown={(event) => {
          if (event.key === "ArrowUp" || event.key === "ArrowRight") onStage(stepValue(value, step, min, max, 1));
          if (event.key === "ArrowDown" || event.key === "ArrowLeft") onStage(stepValue(value, step, min, max, -1));
        }}
      >
        <span className="bw-rotary__indicator" style={{ transform: `rotate(${angle}deg)` }} />
      </button>
      <output className="bw-rotary__value">{value} <small>{unit}</small></output>
      <span className="bw-rotary__state">Staged</span>
    </div>
  );
}

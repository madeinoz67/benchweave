import { useState } from "react";

import { Button } from "./Button";
import type { ButtonVariant } from "./Button";
import type { DisabledReason } from "./disabledReasons";
import "./ConfirmAction.css";

export interface ConfirmActionProps {
  /** The initial control's label; it only STAGES the action. */
  label: string;
  /** R-ENERGISE-1 (i): the effect, e.g. "the output will be energised". */
  effect: string;
  /** R-ENERGISE-1 (ii): the exact value to be applied, with unit. */
  value?: { amount: number | string; unit: string };
  /** R-ENERGISE-1 (iii): the target — which output or channel. */
  target: string;
  onConfirm(): void;
  variant?: ButtonVariant;
  disabled?: boolean;
  disabledReason?: DisabledReason;
}

/** The contract's confirm-action pattern (§C.1 R-ENERGISE-1): the initial
 *  control only stages intent; the confirm step — a second explicit action —
 *  states the effect, the exact values to be applied, and the target. This is
 *  for ENERGY-SOURCING actions only; an energy-removing action (output off) is
 *  one action, never confirmed, never gated (R-DEENERGISE-1) and must not use
 *  this component. */
export function ConfirmAction({ label, effect, value, target, onConfirm, variant = "primary", disabled, disabledReason }: ConfirmActionProps) {
  const [armed, setArmed] = useState(false);
  const appliedValue = value === undefined ? "" : ` ${value.amount} ${value.unit}`;
  return (
    <div className="bw-confirm" data-bw-confirm={armed ? "armed" : "idle"}>
      <Button
        variant={variant}
        disabled={disabled}
        disabledReason={disabledReason}
        onClick={() => setArmed(true)}
        aria-expanded={armed}
      >
        {label}
      </Button>
      {armed ? (
        <div className="bw-confirm__step">
          <p className="bw-confirm__text">
            {effect}:{appliedValue} to {target}. Confirm to proceed.
          </p>
          <div className="bw-confirm__actions">
            <Button
              variant="primary"
              onClick={() => {
                setArmed(false);
                onConfirm();
              }}
            >
              Confirm: {label}
            </Button>
            <Button variant="tertiary" onClick={() => setArmed(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

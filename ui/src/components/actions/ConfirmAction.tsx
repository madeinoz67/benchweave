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
  /** R-ENERGISE-1 (ii): the exact value to be applied, with unit. Required —
   *  an energy-sourcing confirm that cannot state the exact values it will
   *  apply is not a conforming confirm. */
  value: { amount: number | string; unit: string };
  /** R-ENERGISE-1 (iii): the target — which output or channel. */
  target: string;
  onConfirm(): void;
  variant?: ButtonVariant;
  disabled?: boolean;
  disabledReason?: DisabledReason;
  /** Story/test seam: render the ARMED presentation directly (the armed step
   *  is the safety-critical state; a static story or the contract fixture
   *  should not need to synthesize the staging click). */
  initiallyArmed?: boolean;
}

/** The contract's confirm-action pattern (§C.1 R-ENERGISE-1): the initial
 *  control only stages intent; the confirm step — a second explicit action —
 *  states the effect, the exact values to be applied, and the target. This is
 *  for ENERGY-SOURCING actions only; an energy-removing action (output off) is
 *  one action, never confirmed, never gated (R-DEENERGISE-1) and must not use
 *  this component.
 *
 *  The guard holds at FIRE time, not only at stage time: `disabled` /
 *  `disabledReason` apply to the armed Confirm button too, so a guard that
 *  arrives while armed (a protective trip, loss of authority) blocks the
 *  dispatch with its required visible reason. The staged intent is never
 *  silently discarded — there is no auto-disarm; Cancel stays enabled and is
 *  the operator's way out, and a departing guard re-enables the confirm. */
export function ConfirmAction({ label, effect, value, target, onConfirm, variant = "primary", disabled, disabledReason, initiallyArmed = false }: ConfirmActionProps) {
  const [armed, setArmed] = useState(initiallyArmed);
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
            {effect}: {value.amount} {value.unit} to {target}. Confirm to proceed.
          </p>
          <div className="bw-confirm__actions">
            <Button
              variant="primary"
              disabled={disabled}
              disabledReason={disabledReason}
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

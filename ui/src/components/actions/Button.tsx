import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

import { disabledReasonLabel, type DisabledReason } from "./disabledReasons";
import "./button.css";

export type ButtonVariant = "primary" | "secondary" | "tertiary" | "destructive" | "protective";

export interface ButtonProps extends PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement>> {
  variant?: ButtonVariant;
  busy?: boolean;
  /** Contract §C.2: a disabled control carries its reason key and renders the
   *  required label text VISIBLY beside the control, not aria-only. */
  disabledReason?: DisabledReason;
}

export function Button({ variant = "secondary", busy = false, disabledReason, disabled, children, ...props }: ButtonProps) {
  const reason = disabledReason !== undefined && disabled ? disabledReason : undefined;
  const button = (
    <button
      className="bw-button"
      data-variant={variant}
      aria-busy={busy}
      data-bw-disabled-reason={reason?.key}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
  if (reason === undefined) return button;
  return (
    <span className="bw-button__reason">
      {button}
      <small className="bw-button__reason-text" data-bw-disabled-label="">
        {disabledReasonLabel(reason)}
      </small>
    </span>
  );
}

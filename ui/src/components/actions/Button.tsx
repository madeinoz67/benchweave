import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

import "./button.css";

export type ButtonVariant = "primary" | "secondary" | "tertiary" | "destructive" | "protective";

export interface ButtonProps extends PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement>> {
  variant?: ButtonVariant;
  busy?: boolean;
}

export function Button({ variant = "secondary", busy = false, children, ...props }: ButtonProps) {
  return (
    <button className="bw-button" data-variant={variant} aria-busy={busy} {...props}>
      {children}
    </button>
  );
}

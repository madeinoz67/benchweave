/** The contract's disabled-reason enum (docs/internal/ui-contract.md §C.2): five
 *  keys with REQUIRED label text, rendered visibly beside the disabled control
 *  (`data-bw-disabled-label`), never aria-only. `device-state` carries the
 *  blocking state as its parameter; the contract's canonical example is `idle`. */
export type DisabledReasonKey =
  | "capability-absent"
  | "device-state"
  | "protection-active"
  | "invalid-staged-input"
  | "no-authority";

export interface DisabledReason {
  key: DisabledReasonKey;
  /** The blocking state, for the `device-state` key only. */
  state?: string;
}

export function disabledReasonLabel(reason: DisabledReason): string {
  switch (reason.key) {
    case "capability-absent":
      return "Not available on this device";
    case "device-state":
      return `Device must be ${reason.state ?? "idle"}`;
    case "protection-active":
      return "Protection trip active";
    case "invalid-staged-input":
      return "Staged value is invalid";
    case "no-authority":
      return "No lease or policy authority";
  }
}

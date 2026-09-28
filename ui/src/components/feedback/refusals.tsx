import { AlertBubble } from "./AlertBubble";
import type { Severity } from "./severity";
import "./refusals.css";

/** The contract's refusal mapping (§C.3): one row per interface 0.1.0 error
 *  code plus the no-response row. Every interface error code means the
 *  operation was not accepted and NOTHING was dispatched (sent NO); the
 *  no-response row — transport failure or timeout, no interface answer at all —
 *  is UNKNOWN, the request may have been sent (A06). */
export type RefusalCode =
  | "invalid_request"
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "policy_denied"
  | "not_ready"
  | "gone"
  | "cursor_expired"
  | "event_gap"
  | "payload_too_large"
  | "rate_limited"
  | "unavailable"
  | "internal_error"
  | "no-response";

export interface RefusalRow {
  severity: Severity;
  whatHappened: string;
  sent: "NO" | "UNKNOWN";
  operatorAction: string;
}

export const REFUSALS: Record<RefusalCode, RefusalRow> = {
  invalid_request: { severity: "warning", whatHappened: "The request was not accepted: it failed validation.", sent: "NO", operatorAction: "Correct the staged input and submit it again." },
  unauthenticated: { severity: "warning", whatHappened: "The request was not accepted: the caller is not authenticated.", sent: "NO", operatorAction: "Authenticate and submit again." },
  forbidden: { severity: "warning", whatHappened: "The request was not accepted: the caller lacks the required permission.", sent: "NO", operatorAction: "Have an operator with the required authority act, or request the role." },
  not_found: { severity: "advisory", whatHappened: "The addressed resource is unavailable to this caller.", sent: "NO", operatorAction: "Check the identifier and the caller's scope; do not infer existence from the answer." },
  conflict: { severity: "warning", whatHappened: "The request was not accepted: the addressed revision or state has moved on.", sent: "NO", operatorAction: "Re-read current state and re-stage the request." },
  policy_denied: { severity: "warning", whatHappened: "The request was not accepted: policy refuses this action.", sent: "NO", operatorAction: "Request a policy change or an authorised path; do not retry unchanged." },
  not_ready: { severity: "advisory", whatHappened: "The request was not accepted: the target is not ready for this action.", sent: "NO", operatorAction: "Wait for readiness and submit again." },
  gone: { severity: "advisory", whatHappened: "The request was not accepted: the addressed resource is gone.", sent: "NO", operatorAction: "Refresh the view and address a current resource." },
  cursor_expired: { severity: "advisory", whatHappened: "The listing cursor expired or its snapshot was superseded.", sent: "NO", operatorAction: "Restart the listing and deduplicate by stable resource identity." },
  event_gap: { severity: "warning", whatHappened: "Retention overtook the event cursor; events are missing from the stream.", sent: "NO", operatorAction: "Re-read the affected snapshots from a new cursor; do not skip the gap." },
  payload_too_large: { severity: "warning", whatHappened: "The request was not accepted: its payload exceeds the limit.", sent: "NO", operatorAction: "Reduce the payload and submit again." },
  rate_limited: { severity: "advisory", whatHappened: "The request was not accepted: the rate limit was hit.", sent: "NO", operatorAction: "Wait the advertised interval and submit again." },
  unavailable: { severity: "critical", whatHappened: "The gateway is unavailable.", sent: "NO", operatorAction: "Restore or await the gateway; treat observation and protection visibility as degraded." },
  internal_error: { severity: "warning", whatHappened: "The request was not accepted: an internal error occurred.", sent: "NO", operatorAction: "Retry from known state or contact the operator; the correlation ID links diagnostics." },
  "no-response": { severity: "critical", whatHappened: "No interface answer arrived (transport failure or timeout).", sent: "UNKNOWN", operatorAction: "Do not retry blindly; reconcile via run identity and duplicate suppression before acting again." },
};

const sentText = (sent: RefusalRow["sent"]): string =>
  sent === "NO" ? "Nothing was sent." : "It is unknown whether anything was sent — the request may have been sent.";

/** Render a refusal at the presentation boundary: the row's severity, and the
 *  three required message elements — what happened, whether anything was sent,
 *  and what the operator can do (contract §C.3). */
export function RefusalMessage({ code }: { code: RefusalCode }) {
  const row = REFUSALS[code];
  return (
    <AlertBubble
      severity={row.severity}
      title={code === "no-response" ? "No response" : `Request refused: ${code}`}
      message={`${row.whatHappened} ${sentText(row.sent)} ${row.operatorAction}`}
      source={code}
    />
  );
}

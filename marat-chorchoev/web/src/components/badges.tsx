import { fmtDateTime, fmtDuration, statusLabel, titleCase } from "@/lib/format";
import type { Priority, Sla, Status } from "@/lib/types";

// Color is never the only signal: every badge also carries a glyph and a text label (WEB-06).
const STATUS_GLYPH: Record<Status, string> = {
  SUBMITTED: "○",
  TRIAGED: "◔",
  SCHEDULED: "◑",
  ACCEPTED: "◕",
  IN_PROGRESS: "▶",
  BLOCKED: "■",
  COMPLETED: "✓",
  REOPENED: "↺",
  CLOSED: "●",
  CANCELED: "✕",
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`badge status-${status}`}>
      <span aria-hidden="true">{STATUS_GLYPH[status]}</span> {statusLabel(status)}
    </span>
  );
}

const PRIORITY_GLYPH: Record<Priority, string> = { LOW: "↓", NORMAL: "→", HIGH: "↑" };

export function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <span className={`badge priority-${priority}`}>
      <span aria-hidden="true">{PRIORITY_GLYPH[priority]}</span> {titleCase(priority)}
    </span>
  );
}

const SLA_GLYPH = { ON_TRACK: "✓", AT_RISK: "!", OVERDUE: "⚠" } as const;

export function SlaBadge({ sla, timeZone, detailed }: { sla: Sla; timeZone: string; detailed?: boolean }) {
  const text = sla.state === "OVERDUE" ? "Overdue" : sla.state === "AT_RISK" ? "At risk" : "On track";
  const remaining = sla.remaining_seconds;
  let extra = "";
  if (sla.stopped_at) extra = "final outcome";
  else if (sla.paused) extra = "paused";
  else extra = remaining >= 0 ? `${fmtDuration(remaining)} left` : `${fmtDuration(remaining)} over`;
  return (
    <span className={`badge sla-${sla.state}`} title={sla.due_at ? `Due ${fmtDateTime(sla.due_at, timeZone)}` : undefined}>
      <span aria-hidden="true">{SLA_GLYPH[sla.state]}</span> {text}
      {detailed ? <span className="badge-extra"> · {extra}</span> : null}
    </span>
  );
}

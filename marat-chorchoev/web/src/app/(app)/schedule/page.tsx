"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Button, Card, Empty, ErrorNote, PageHeader, SelectField, Spinner } from "@/components/ui";
import { addDays, fmtDay, fmtTime, localDate, WEEKDAYS, zonedToUtc } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import { useMembership } from "@/lib/session";

interface Appointment {
  assignment_id: string;
  technician_id: string;
  request_id: string;
  reference: string;
  title: string;
  request_status: string;
  priority: string;
  assignment_status: string;
  is_active: boolean;
  start_at: string;
  end_at: string;
}
interface ScheduleData {
  timezone: string;
  technicians: {
    id: string;
    full_name: string;
    is_active: boolean;
    availability: { weekday: number; starts_at: string; ends_at: string }[];
    time_off: { start_at: string; end_at: string; reason: string | null }[];
  }[];
  appointments: Appointment[];
}

const overlaps = (a: Appointment, b: Appointment) => a.start_at < b.end_at && b.start_at < a.end_at;

export default function SchedulePage() {
  const membership = useMembership();
  const tz = membership?.timezone ?? "UTC";
  const [view, setView] = useState<"day" | "week">("week");
  const [anchor, setAnchor] = useState(() => localDate(new Date(), tz));

  const days = useMemo(() => {
    if (view === "day") return [anchor];
    const date = new Date(`${anchor}T12:00:00Z`);
    const monday = addDays(anchor, -((date.getUTCDay() + 6) % 7));
    return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
  }, [anchor, view]);

  const query = useApiQuery<ScheduleData>("/schedule", { date_from: days[0], date_to: days[days.length - 1] });
  const data = query.data;

  const cell = (techId: string, day: string) => {
    const from = zonedToUtc(day, "00:00", tz).toISOString();
    const to = zonedToUtc(addDays(day, 1), "00:00", tz).toISOString();
    return (data?.appointments ?? []).filter((a) => a.technician_id === techId && a.start_at < to && a.end_at > from);
  };

  return (
    <>
      <PageHeader
        title="Schedule"
        subtitle={`Planned technician workload · times in ${tz}`}
        actions={
          <div className="row">
            <SelectField label="View" value={view} onChange={(e) => setView(e.target.value as "day" | "week")}>
              <option value="day">Day</option>
              <option value="week">Week</option>
            </SelectField>
            <Button variant="secondary" onClick={() => setAnchor(addDays(anchor, view === "day" ? -1 : -7))}>
              Previous
            </Button>
            <Button variant="secondary" onClick={() => setAnchor(localDate(new Date(), tz))}>
              Today
            </Button>
            <Button variant="secondary" onClick={() => setAnchor(addDays(anchor, view === "day" ? 1 : 7))}>
              Next
            </Button>
          </div>
        }
      />
      {query.isLoading ? <Spinner /> : null}
      <ErrorNote error={query.error} onRetry={() => void query.refetch()} />
      {data && data.technicians.length === 0 ? <Empty title="No technicians" /> : null}
      {data && data.technicians.length > 0 ? (
        <Card>
          <div className="board" style={{ gridTemplateColumns: `160px repeat(${days.length}, minmax(${view === "day" ? 320 : 130}px, 1fr))` }} role="table" aria-label="Technician schedule">
            <div className="board-cell board-head" role="columnheader">
              Technician
            </div>
            {days.map((day) => (
              <div className="board-cell board-head" role="columnheader" key={day}>
                {fmtDay(zonedToUtc(day, "12:00", tz).toISOString(), tz)}
              </div>
            ))}
            {data.technicians.map((tech) => (
              <div key={tech.id} style={{ display: "contents" }} role="row">
                <div className="board-cell" role="rowheader">
                  <strong>{tech.full_name}</strong>
                  {!tech.is_active ? <div className="muted small">inactive</div> : null}
                </div>
                {days.map((day) => {
                  const weekday = (new Date(`${day}T12:00:00Z`).getUTCDay() + 6) % 7;
                  const hours = tech.availability.filter((a) => a.weekday === weekday);
                  const off = tech.time_off.filter((t) => {
                    const from = zonedToUtc(day, "00:00", tz).toISOString();
                    const to = zonedToUtc(addDays(day, 1), "00:00", tz).toISOString();
                    return t.start_at < to && t.end_at > from;
                  });
                  const appts = cell(tech.id, day);
                  return (
                    <div className="board-cell" role="cell" key={day}>
                      <div className="muted small">
                        {hours.length ? hours.map((h) => `${h.starts_at}–${h.ends_at}`).join(", ") : `${WEEKDAYS[weekday]} off`}
                      </div>
                      {off.map((t, i) => (
                        <span className="appt off" key={i}>
                          Time off{t.reason ? `: ${t.reason}` : ""}
                        </span>
                      ))}
                      {appts.map((a) => {
                        const clash = appts.some((b) => b !== a && b.is_active && a.is_active && overlaps(a, b));
                        return (
                          <Link key={a.assignment_id} href={`/requests/${a.request_id}`} className={`appt${clash ? " conflict" : ""}`}>
                            <strong>
                              {fmtTime(a.start_at, tz)}–{fmtTime(a.end_at, tz)}
                            </strong>{" "}
                            {a.reference}
                            <div className="small">
                              {a.title} · {a.request_status.replace("_", " ").toLowerCase()}
                              {clash ? " · CONFLICT" : ""}
                            </div>
                          </Link>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </Card>
      ) : null}
    </>
  );
}

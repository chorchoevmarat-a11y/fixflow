"use client";

import { useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Button, Card, ConfirmButton, ErrorNote, Modal, PageHeader, Spinner, TextField } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime, WEEKDAYS } from "@/lib/format";
import { useAction, useApiQuery } from "@/lib/hooks";
import { useMembership } from "@/lib/session";
import type { Technician } from "@/lib/types";

interface Skill {
  id: string;
  name: string;
}
type Day = { open: boolean; starts_at: string; ends_at: string };

function Editor({ tech, skills, onDone }: { tech: Technician; skills: Skill[]; onDone: () => void }) {
  const [title, setTitle] = useState(tech.title ?? "");
  const [phone, setPhone] = useState(tech.phone ?? "");
  const [selected, setSelected] = useState(tech.skills.map((s) => s.id));
  const [days, setDays] = useState<Day[]>(
    WEEKDAYS.map((_, i) => {
      const slot = tech.availability.find((a) => a.weekday === i);
      return { open: !!slot, starts_at: slot?.starts_at ?? "09:00", ends_at: slot?.ends_at ?? "18:00" };
    }),
  );
  const [error, setError] = useState<string | null>(null);
  const save = useAction(
    () =>
      api.put(`/technicians/${tech.id}`, {
        title: title.trim() || null,
        phone: phone.trim() || null,
        skill_ids: selected,
        availability: days.flatMap((d, weekday) => (d.open ? [{ weekday, starts_at: d.starts_at, ends_at: d.ends_at }] : [])),
      }),
    { success: "Technician saved.", onSuccess: onDone },
  );
  return (
    <div className="stack">
      <div className="grid cols-2">
        <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <TextField label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
      </div>
      <fieldset style={{ border: "1px solid var(--border)", borderRadius: 8 }}>
        <legend>Skills</legend>
        <div className="row">
          {skills.map((s) => (
            <label className="check" key={s.id}>
              <input type="checkbox" checked={selected.includes(s.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, s.id] : selected.filter((x) => x !== s.id))} />
              {s.name}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset style={{ border: "1px solid var(--border)", borderRadius: 8 }}>
        <legend>Weekly availability (organization time)</legend>
        {days.map((d, i) => (
          <div className="row" key={WEEKDAYS[i]} style={{ marginBottom: 4 }}>
            <label className="check" style={{ width: 90 }}>
              <input type="checkbox" checked={d.open} onChange={(e) => setDays(days.map((x, j) => (j === i ? { ...x, open: e.target.checked } : x)))} />
              {WEEKDAYS[i]}
            </label>
            {d.open ? (
              <>
                <input aria-label={`${WEEKDAYS[i]} from`} type="time" value={d.starts_at} onChange={(e) => setDays(days.map((x, j) => (j === i ? { ...x, starts_at: e.target.value } : x)))} style={{ width: 120 }} />
                <input aria-label={`${WEEKDAYS[i]} to`} type="time" value={d.ends_at} onChange={(e) => setDays(days.map((x, j) => (j === i ? { ...x, ends_at: e.target.value } : x)))} style={{ width: 120 }} />
              </>
            ) : (
              <span className="muted">Off</span>
            )}
          </div>
        ))}
      </fieldset>
      {error ? <p className="error-text" role="alert">{error}</p> : null}
      {save.error ? <ErrorNote error={save.error} /> : null}
      <div className="row end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button
          loading={save.isPending}
          onClick={() => {
            const bad = days.findIndex((d) => d.open && d.ends_at <= d.starts_at);
            if (bad >= 0) return setError(`${WEEKDAYS[bad]}: end must be after start.`);
            setError(null);
            save.mutate(undefined);
          }}
        >
          Save
        </Button>
      </div>
    </div>
  );
}

function TimeOff({ tech }: { tech: Technician }) {
  const tz = useMembership()?.timezone ?? "UTC";
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = useAction(
    () => api.post(`/technicians/${tech.id}/time-off`, { start_at: new Date(start).toISOString(), end_at: new Date(end).toISOString(), reason: reason.trim() || null }),
    { success: "Time off recorded." },
  );
  const remove = useAction((id: string) => api.del(`/technicians/${tech.id}/time-off/${id}`), { success: "Time off removed." });
  return (
    <div className="stack">
      {tech.time_off.map((t) => (
        <div className="row between" key={t.id}>
          <span>
            {fmtDateTime(t.start_at, tz)} → {fmtDateTime(t.end_at, tz)} {t.reason ? `· ${t.reason}` : ""}
          </span>
          <ConfirmButton small variant="secondary" label="Remove" title="Remove time off?" message="The technician becomes bookable again." onConfirm={() => remove.mutate(t.id)} />
        </div>
      ))}
      <div className="grid cols-4">
        <TextField label="From" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
        <TextField label="To" type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
        <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        <div style={{ alignSelf: "end" }}>
          <Button
            small
            loading={add.isPending}
            onClick={() => {
              if (!start || !end || end <= start) return setError("Choose a start and a later end.");
              setError(null);
              add.mutate(undefined);
            }}
          >
            Add time off
          </Button>
        </div>
      </div>
      {error ? <p className="error-text" role="alert">{error}</p> : null}
      {add.error ? <ErrorNote error={add.error} /> : null}
    </div>
  );
}

function View() {
  const technicians = useApiQuery<Technician[]>("/technicians");
  const skills = useApiQuery<Skill[]>("/skills");
  const [editing, setEditing] = useState<Technician | null>(null);
  return (
    <>
      <PageHeader title="Technicians" subtitle="Skills, weekly availability, and time off decide who can be scheduled." />
      {technicians.isLoading ? <Spinner /> : null}
      <ErrorNote error={technicians.error} />
      <div className="stack">
        {technicians.data?.map((t) => (
          <Card key={t.id} title={t.full_name} actions={<Button small variant="secondary" onClick={() => setEditing(t)}>Edit skills & hours</Button>}>
            <p className="muted">
              {t.email} {t.is_active ? "" : "· deactivated"}
            </p>
            <p>
              <strong>Skills:</strong> {t.skills.map((s) => s.name).join(", ") || "none"}
            </p>
            <p>
              <strong>Hours:</strong>{" "}
              {t.availability.map((a) => `${WEEKDAYS[a.weekday]} ${a.starts_at}–${a.ends_at}`).join(" · ") || "no availability set"}
            </p>
            <details>
              <summary>Time off ({t.time_off.length})</summary>
              <TimeOff tech={t} />
            </details>
          </Card>
        ))}
      </div>
      <Modal title={`Edit ${editing?.full_name ?? ""}`} open={editing !== null} onClose={() => setEditing(null)}>
        {editing ? <Editor tech={editing} skills={skills.data ?? []} onDone={() => setEditing(null)} /> : null}
      </Modal>
    </>
  );
}

export default function TechniciansPage() {
  return (
    <AuthGuard roles={["ADMIN"]}>
      <View />
    </AuthGuard>
  );
}

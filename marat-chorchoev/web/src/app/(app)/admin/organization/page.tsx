"use client";

import { useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Button, Card, ConfirmButton, ErrorNote, Notice, PageHeader, Spinner, TextField } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { WEEKDAYS } from "@/lib/format";
import { useAction, useApiQuery } from "@/lib/hooks";

interface Org {
  name: string;
  slug: string;
  timezone: string;
  currency: string;
  business_hours: { weekday: number; opens_at: string; closes_at: string }[];
  holidays: { id: string; day: string; name: string }[];
  sla_policy_hours: Record<string, number>;
}

type Day = { open: boolean; opens_at: string; closes_at: string };

function Settings({ org }: { org: Org }) {
  const [name, setName] = useState(org.name);
  const [timezone, setTimezone] = useState(org.timezone);
  const save = useAction(() => api.patch("/organization", { name: name.trim(), timezone: timezone.trim() }), { success: "Settings saved.", silentError: true });
  const server = save.error instanceof ApiError ? save.error.fields : {};
  return (
    <Card title="Organization settings">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          if (!save.isPending) save.mutate(undefined);
        }}
      >
        <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={server.name} />
        <TextField label="IANA timezone" value={timezone} onChange={(e) => setTimezone(e.target.value)} error={server.timezone} hint="e.g. Asia/Bishkek. Changing it re-plans every running SLA clock." />
        <p className="muted small">Currency: {org.currency} (integer tyiyn, 100 tyiyn = 1 KGS)</p>
        {save.error && !Object.keys(server).length ? <ErrorNote error={save.error} /> : null}
        <div>
          <Button type="submit" loading={save.isPending}>
            Save settings
          </Button>
        </div>
      </form>
    </Card>
  );
}

function Hours({ org }: { org: Org }) {
  const initial: Day[] = WEEKDAYS.map((_, i) => {
    const first = org.business_hours.find((h) => h.weekday === i);
    return { open: !!first, opens_at: first?.opens_at ?? "09:00", closes_at: first?.closes_at ?? "18:00" };
  });
  const [days, setDays] = useState<Day[]>(initial);
  const [error, setError] = useState<string | null>(null);
  const save = useAction(
    () =>
      api.put("/organization/business-hours", {
        intervals: days.flatMap((d, weekday) => (d.open ? [{ weekday, opens_at: d.opens_at, closes_at: d.closes_at }] : [])),
      }),
    { success: "Business hours saved. Open SLA clocks were re-planned." },
  );
  return (
    <Card title="Business hours (SLA time only counts inside these)">
      <div className="stack">
        {days.map((d, i) => (
          <div className="row" key={WEEKDAYS[i]}>
            <label className="check" style={{ width: 110 }}>
              <input type="checkbox" checked={d.open} onChange={(e) => setDays(days.map((x, j) => (j === i ? { ...x, open: e.target.checked } : x)))} />
              {WEEKDAYS[i]}
            </label>
            {d.open ? (
              <>
                <input aria-label={`${WEEKDAYS[i]} opens`} type="time" value={d.opens_at} onChange={(e) => setDays(days.map((x, j) => (j === i ? { ...x, opens_at: e.target.value } : x)))} style={{ width: 130 }} />
                <span>to</span>
                <input aria-label={`${WEEKDAYS[i]} closes`} type="time" value={d.closes_at} onChange={(e) => setDays(days.map((x, j) => (j === i ? { ...x, closes_at: e.target.value } : x)))} style={{ width: 130 }} />
              </>
            ) : (
              <span className="muted">Closed</span>
            )}
          </div>
        ))}
        {error ? <p className="error-text" role="alert">{error}</p> : null}
        <div>
          <Button
            loading={save.isPending}
            onClick={() => {
              const bad = days.findIndex((d) => d.open && d.closes_at <= d.opens_at);
              if (bad >= 0) return setError(`${WEEKDAYS[bad]}: closing time must be after opening time.`);
              setError(null);
              save.mutate(undefined);
            }}
          >
            Save business hours
          </Button>
        </div>
      </div>
    </Card>
  );
}

function Holidays({ org }: { org: Org }) {
  const [day, setDay] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = useAction(() => api.post("/organization/holidays", { day, name: name.trim() }), {
    success: "Holiday added. SLA clocks skip it.",
    onSuccess: () => { setDay(""); setName(""); },
  });
  const remove = useAction((id: string) => api.del(`/organization/holidays/${id}`), { success: "Holiday removed." });
  return (
    <Card title="Holidays (business time does not advance)">
      <div className="stack">
        {org.holidays.length === 0 ? <p className="muted">No holidays configured.</p> : null}
        {org.holidays.map((h) => (
          <div className="row between" key={h.id}>
            <span>
              <strong>{h.day}</strong> {h.name}
            </span>
            <ConfirmButton label="Remove" small variant="secondary" title="Remove this holiday?" message={`${h.day} ${h.name} will count as business time again.`} onConfirm={() => remove.mutate(h.id)} />
          </div>
        ))}
        <div className="grid cols-3">
          <TextField label="Date" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <div style={{ alignSelf: "end" }}>
            <Button
              loading={add.isPending}
              onClick={() => {
                if (!day || name.trim().length < 2) return setError("Pick a date and give the holiday a name.");
                setError(null);
                add.mutate(undefined);
              }}
            >
              Add holiday
            </Button>
          </div>
        </div>
        {error ? <p className="error-text" role="alert">{error}</p> : null}
      </div>
    </Card>
  );
}

function View() {
  const org = useApiQuery<Org>("/organization");
  if (org.isLoading) return <Spinner />;
  if (org.error) return <ErrorNote error={org.error} onRetry={() => void org.refetch()} />;
  if (!org.data) return null;
  const o = org.data;
  return (
    <>
      <PageHeader title="Organization" subtitle={o.name} />
      <Notice>
        SLA budgets in business hours: high {o.sla_policy_hours.HIGH}, normal {o.sla_policy_hours.NORMAL}, low {o.sla_policy_hours.LOW}. Time outside business hours and on holidays does not count, and the clock pauses while an estimate awaits approval.
      </Notice>
      <div className="stack">
        <Settings key={`${o.name}-${o.timezone}`} org={o} />
        <Hours key={JSON.stringify(o.business_hours)} org={o} />
        <Holidays org={o} />
      </div>
    </>
  );
}

export default function OrganizationPage() {
  return (
    <AuthGuard roles={["ADMIN"]}>
      <View />
    </AuthGuard>
  );
}

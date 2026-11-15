import { fmtDay } from "@/lib/format";

export interface DailyPoint {
  date: string;
  new: number;
  completed: number;
}

/** Grouped bars: new vs completed requests per day. Each bar exposes its value as text. */
export function DailyChart({ series, unit, range }: { series: DailyPoint[]; unit: string; range: string }) {
  const max = Math.max(1, ...series.flatMap((p) => [p.new, p.completed]));
  return (
    <figure style={{ margin: 0 }}>
      <figcaption className="muted small">
        {range} · unit: {unit}
      </figcaption>
      <div className="bar-chart" role="img" aria-label={`Daily new and completed requests, ${range}`}>
        {series.map((p) => (
          <div
            key={p.date}
            className="bar-group"
            title={`${fmtDay(`${p.date}T12:00:00Z`, "UTC")}: ${p.new} new, ${p.completed} completed`}
          >
            <div className="bar new" style={{ height: `${(p.new / max) * 100}%` }} />
            <div className="bar done" style={{ height: `${(p.completed / max) * 100}%` }} />
          </div>
        ))}
      </div>
      <div className="row between small muted">
        <span>{series[0]?.date}</span>
        <span>{series[series.length - 1]?.date}</span>
      </div>
      <div className="legend">
        <span>
          <span className="swatch" style={{ background: "var(--primary)" }} />
          New reports
        </span>
        <span>
          <span className="swatch" style={{ background: "var(--ok)" }} />
          Completed reports
        </span>
      </div>
      <table className="sr-only">
        <caption>Daily reports ({unit})</caption>
        <thead>
          <tr>
            <th>Date</th>
            <th>New</th>
            <th>Completed</th>
          </tr>
        </thead>
        <tbody>
          {series.map((p) => (
            <tr key={p.date}>
              <td>{p.date}</td>
              <td>{p.new}</td>
              <td>{p.completed}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

export function DistributionChart({ rows, title }: { rows: { label: string; count: number }[]; title: string }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  const total = rows.reduce((sum, r) => sum + r.count, 0);
  return (
    <figure style={{ margin: 0 }} aria-label={title}>
      {rows.length === 0 ? <p className="muted">No requests in this period.</p> : null}
      {rows.map((row) => (
        <div className="hbar" key={row.label} title={`${row.label}: ${row.count} request${row.count === 1 ? "" : "s"}`}>
          <span>{row.label}</span>
          <div className="hbar-track">
            <div className="hbar-fill" style={{ width: `${(row.count / max) * 100}%` }} />
          </div>
          <strong>{row.count}</strong>
        </div>
      ))}
      <figcaption className="muted small">Unit: requests created in the selected range · total {total}</figcaption>
    </figure>
  );
}

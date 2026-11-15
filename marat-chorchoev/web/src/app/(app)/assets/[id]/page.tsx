"use client";

import Link from "next/link";
import { use, useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Button, Card, ConfirmButton, Empty, ErrorNote, PageHeader, Pagination, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime, fmtMoney } from "@/lib/format";
import { useAction, useApiQuery } from "@/lib/hooks";
import { useMembership } from "@/lib/session";
import type { AssetItem, Page } from "@/lib/types";

interface AssetDetail extends AssetItem {
  property_address: string | null;
  open_requests: { id: string; reference: string; title: string; status: string; priority: string }[];
  last_service: { request_id: string; reference: string; title: string; technician_name: string; serviced_at: string; outcome: string } | null;
  next_maintenance: { plan_id: string; title: string; date: string } | null;
}
interface HistoryItem {
  id: string;
  request_id: string;
  reference: string;
  title: string;
  technician_name: string;
  serviced_at: string;
  outcome: string;
  materials: { item_name: string; unit: string; quantity: number; total_minor: number }[];
  attachments: { id: string; kind: string; original_name: string }[];
}

function AssetView({ id }: { id: string }) {
  const tz = useMembership()?.timezone ?? "UTC";
  const [page, setPage] = useState(1);
  const asset = useApiQuery<AssetDetail>(`/assets/${id}`);
  const history = useApiQuery<Page<HistoryItem>>(`/assets/${id}/history`, { page, page_size: 5 });
  const setStatus = useAction((status: string) => api.patch(`/assets/${id}`, { status }), { success: "Asset updated." });
  const a = asset.data;
  if (asset.isLoading) return <Spinner />;
  if (asset.error) return <ErrorNote error={asset.error} onRetry={() => void asset.refetch()} />;
  if (!a) return null;
  return (
    <>
      <PageHeader
        title={`${a.code} · ${a.name}`}
        subtitle={`${a.asset_type} at ${a.property_name} — ${a.property_address}`}
        actions={
          <>
            <Link className="btn btn-secondary" href="/properties">
              Back
            </Link>
            {a.status !== "RETIRED" ? (
              <>
                <Button variant="secondary" loading={setStatus.isPending} onClick={() => setStatus.mutate(a.status === "ACTIVE" ? "OUT_OF_SERVICE" : "ACTIVE")}>
                  {a.status === "ACTIVE" ? "Mark out of service" : "Mark active"}
                </Button>
                <ConfirmButton
                  label="Retire asset"
                  title="Retire this asset?"
                  message="History is kept, but no new maintenance plans or reports can use it."
                  onConfirm={() => setStatus.mutate("RETIRED")}
                />
              </>
            ) : null}
          </>
        }
      />
      <div className="grid cols-3">
        <Card title="Status">
          <p className="stat">{a.status.replace("_", " ").toLowerCase()}</p>
          <p className="muted small">Serial: {a.serial_number ?? "—"} · Installed: {a.installed_on ?? "—"}</p>
        </Card>
        <Card title="Open work">
          {a.open_requests.length === 0 ? <p className="muted">None</p> : null}
          {a.open_requests.map((r) => (
            <div key={r.id}>
              <Link href={`/requests/${r.id}`}>
                {r.reference} · {r.title}
              </Link>{" "}
              <span className="badge">{r.status.replace("_", " ").toLowerCase()}</span>
            </div>
          ))}
        </Card>
        <Card title="Service">
          <p>
            <strong>Last completed:</strong>{" "}
            {a.last_service ? (
              <>
                <Link href={`/requests/${a.last_service.request_id}`}>{a.last_service.reference}</Link> on {fmtDateTime(a.last_service.serviced_at, tz)}
              </>
            ) : (
              "never"
            )}
          </p>
          <p>
            <strong>Next preventive:</strong> {a.next_maintenance ? `${a.next_maintenance.date} (${a.next_maintenance.title})` : "none scheduled"}
          </p>
        </Card>
      </div>
      <Card title="Service history" className="history">
        {history.data?.items.length === 0 ? <Empty title="No completed service yet" /> : null}
        {history.data?.items.map((h) => (
          <div key={h.id} className="note" style={{ marginBottom: "0.6rem" }}>
            <div className="row between">
              <Link href={`/requests/${h.request_id}`}>
                {h.reference} · {h.title}
              </Link>
              <span className="muted small">
                {fmtDateTime(h.serviced_at, tz)} · {h.technician_name}
              </span>
            </div>
            <p>{h.outcome}</p>
            {h.materials.length ? (
              <p className="muted small">
                Materials: {h.materials.map((m) => `${m.quantity} ${m.unit} ${m.item_name} (${fmtMoney(m.total_minor)})`).join("; ")}
              </p>
            ) : null}
            {h.attachments.length ? <p className="muted small">{h.attachments.length} photo(s) attached</p> : null}
          </div>
        ))}
        {history.data ? <Pagination page={history.data.page} totalPages={history.data.total_pages} total={history.data.total} onChange={setPage} /> : null}
      </Card>
    </>
  );
}

export default function AssetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <AuthGuard roles={["ADMIN", "DISPATCHER"]}>
      <AssetView id={id} />
    </AuthGuard>
  );
}

"use client";

import { useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Card, Empty, ErrorNote, PageHeader, Pagination, Spinner, TextField } from "@/components/ui";
import { fmtDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import { useMembership } from "@/lib/session";
import type { Page } from "@/lib/types";

interface AuditItem {
  id: string;
  action: string;
  summary: string;
  actor_name: string;
  target_type: string;
  created_at: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

function View() {
  const tz = useMembership()?.timezone ?? "UTC";
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const list = useApiQuery<Page<AuditItem>>("/audit", { page, page_size: 25, action, date_from: from, date_to: to });
  return (
    <>
      <PageHeader title="Audit history" subtitle="Immutable, organization-scoped. Secrets are never recorded." />
      <Card>
        <div className="grid cols-3">
          <TextField label="Action prefix" placeholder="e.g. staff. or request." value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} />
          <TextField label="From" type="date" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1); }} />
          <TextField label="To" type="date" value={to} onChange={(e) => { setTo(e.target.value); setPage(1); }} />
        </div>
        {list.isLoading ? <Spinner /> : null}
        <ErrorNote error={list.error} onRetry={() => void list.refetch()} />
        {list.data?.items.length === 0 ? <Empty title="No audit events match" /> : null}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>Action</th>
                <th>What happened</th>
              </tr>
            </thead>
            <tbody>
              {list.data?.items.map((e) => (
                <tr key={e.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{fmtDateTime(e.created_at, tz)}</td>
                  <td>{e.actor_name}</td>
                  <td>
                    <code>{e.action}</code>
                  </td>
                  <td>
                    {e.summary}
                    {e.before || e.after ? (
                      <details>
                        <summary className="small muted">Before / after</summary>
                        <pre className="small" style={{ whiteSpace: "pre-wrap", margin: 0 }}>
                          {JSON.stringify({ before: e.before, after: e.after }, null, 2)}
                        </pre>
                      </details>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {list.data ? <Pagination page={list.data.page} totalPages={list.data.total_pages} total={list.data.total} onChange={setPage} /> : null}
      </Card>
    </>
  );
}

export default function AuditPage() {
  return (
    <AuthGuard roles={["ADMIN"]}>
      <View />
    </AuthGuard>
  );
}

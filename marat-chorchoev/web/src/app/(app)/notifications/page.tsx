"use client";

import Link from "next/link";
import { useState } from "react";
import { Button, Card, Empty, ErrorNote, PageHeader, Pagination, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useAction, useApiQuery } from "@/lib/hooks";
import { useMembership } from "@/lib/session";
import type { NotificationItem, Page } from "@/lib/types";

export default function NotificationsPage() {
  const tz = useMembership()?.timezone ?? "UTC";
  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const list = useApiQuery<Page<NotificationItem> & { unread_count: number }>("/notifications", { page, page_size: 15, unread_only: unreadOnly || undefined });
  const read = useAction((id: string) => api.post(`/notifications/${id}/read`));
  const readAll = useAction(() => api.post("/notifications/read-all"), { success: "All notifications marked as read." });
  return (
    <>
      <PageHeader
        title="Notifications"
        subtitle={list.data ? `${list.data.unread_count} unread` : undefined}
        actions={
          <>
            <label className="check">
              <input type="checkbox" checked={unreadOnly} onChange={(e) => { setUnreadOnly(e.target.checked); setPage(1); }} />
              Unread only
            </label>
            <Button variant="secondary" loading={readAll.isPending} disabled={!list.data?.unread_count} onClick={() => readAll.mutate(undefined)}>
              Mark all as read
            </Button>
          </>
        }
      />
      {list.isLoading ? <Spinner /> : null}
      <ErrorNote error={list.error} onRetry={() => void list.refetch()} />
      {list.data?.items.length === 0 ? <Empty title="You are all caught up" /> : null}
      <div className="stack">
        {list.data?.items.map((n) => (
          <Card key={n.id} className={n.read_at ? "" : "unread"}>
            <div className="row between">
              <div>
                <strong>{n.read_at ? "" : "● "}{n.title}</strong>
                {n.body ? <p className="muted">{n.body}</p> : null}
                <p className="muted small">{fmtDateTime(n.created_at, tz)}</p>
              </div>
              <div className="row">
                {n.request_id ? (
                  <Link className="btn btn-secondary btn-sm" href={`/requests/${n.request_id}`} onClick={() => !n.read_at && read.mutate(n.id)}>
                    Open report
                  </Link>
                ) : null}
                {!n.read_at ? (
                  <Button small variant="ghost" loading={read.isPending && read.variables === n.id} onClick={() => read.mutate(n.id)}>
                    Mark as read
                  </Button>
                ) : null}
              </div>
            </div>
          </Card>
        ))}
      </div>
      {list.data ? <Pagination page={list.data.page} totalPages={list.data.total_pages} total={list.data.total} onChange={setPage} /> : null}
    </>
  );
}

"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { initialFilters, RequestList } from "@/components/request-list";
import { PageHeader, Spinner } from "@/components/ui";
import { useMembership } from "@/lib/session";

function Content() {
  const membership = useMembership();
  const search = useSearchParams();
  const canCreate = membership?.role !== "TECHNICIAN";
  const title = membership?.role === "REQUESTER" ? "My reports" : membership?.role === "TECHNICIAN" ? "My assigned jobs" : "Report queue";
  return (
    <>
      <PageHeader
        title={title}
        actions={
          canCreate ? (
            <Link className="btn btn-primary" href="/requests/new">
              New request
            </Link>
          ) : undefined
        }
      />
      <RequestList initial={initialFilters(search)} />
    </>
  );
}

export default function RequestsPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Content />
    </Suspense>
  );
}

"use client";

import { AuthGuard } from "@/components/auth-guard";
import { RequestForm } from "@/components/request-form";
import { PageHeader } from "@/components/ui";

export default function NewRequestPage() {
  return (
    <AuthGuard roles={["REQUESTER", "DISPATCHER", "ADMIN"]}>
      <PageHeader title="New service report" subtitle="Describe the problem; a dispatcher will accept and schedule it." />
      <RequestForm />
    </AuthGuard>
  );
}

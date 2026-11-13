"use client";

import { AuthGuard } from "@/components/auth-guard";
import { RequestForm } from "@/components/request-form";
import { PageHeader } from "@/components/ui";

export default function NewRequestPage() {
  return (
    <AuthGuard roles={["REQUESTER", "DISPATCHER", "ADMIN"]}>
      <PageHeader title="New service request" subtitle="Describe the problem; a dispatcher will triage and schedule it." />
      <RequestForm />
    </AuthGuard>
  );
}

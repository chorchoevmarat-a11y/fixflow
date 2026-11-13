"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Spinner } from "@/components/ui";
import { homeFor } from "@/lib/nav";
import { currentMembership, useSession } from "@/lib/session";

export default function Index() {
  const router = useRouter();
  const session = useSession();
  useEffect(() => {
    const membership = currentMembership(session);
    router.replace(membership ? homeFor(membership.role) : "/login");
  }, [session, router]);
  return <Spinner />;
}

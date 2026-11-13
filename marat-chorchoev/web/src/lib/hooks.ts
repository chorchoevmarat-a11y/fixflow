"use client";

import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useToast } from "@/components/ui";
import { api, ApiError, type Query } from "@/lib/api";
import { useSession } from "@/lib/session";

/** Every cache key starts with the organization id, so switching organizations can never show stale data. */
export function useOrgId(): string {
  return useSession()?.orgId ?? "none";
}

export function useApiQuery<T>(path: string | null, query?: Query, options?: { refetchInterval?: number }) {
  const orgId = useOrgId();
  return useQuery<T, ApiError>({
    queryKey: [orgId, path, query ?? {}] as QueryKey,
    queryFn: ({ signal }) => api.get<T>(path as string, query, signal),
    enabled: path !== null && orgId !== "none",
    refetchInterval: options?.refetchInterval,
    retry: (count, error) => error.status >= 500 && count < 1,
  });
}

/**
 * Mutation that surfaces failures as toasts, blocks double submits through `isPending`,
 * and refetches everything for the organization on success (WEB-08).
 */
export function useAction<TVars, TResult = unknown>(
  fn: (vars: TVars) => Promise<TResult>,
  options?: { success?: string; onSuccess?: (result: TResult, vars: TVars) => void; silentError?: boolean },
) {
  const client = useQueryClient();
  const orgId = useOrgId();
  const toast = useToast();
  return useMutation<TResult, ApiError, TVars>({
    mutationFn: fn,
    onSuccess: async (result, vars) => {
      await client.invalidateQueries({ queryKey: [orgId] });
      if (options?.success) toast("success", options.success);
      options?.onSuccess?.(result, vars);
    },
    onError: (error) => {
      if (!options?.silentError) toast("error", error.message);
    },
  });
}

"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { API, raw } from "./api";
import { useSession } from "./session";

/**
 * Subscribe to organization-scoped Server-Sent Events (API-06).
 *
 * EventSource cannot send an Authorization header, so the stream is read with fetch.
 * Events are only hints: any event, and every reconnect, refetches canonical state.
 */
export function useLiveUpdates(): void {
  const client = useQueryClient();
  const session = useSession();
  const orgId = session?.orgId ?? null;
  const token = session?.token ?? null;

  useEffect(() => {
    if (!orgId || !token) return;
    let stopped = false;
    let controller: AbortController | null = null;
    let delay = 1000;

    const refetch = () => void client.invalidateQueries({ queryKey: [orgId] });

    async function connect() {
      while (!stopped) {
        controller = new AbortController();
        try {
          const response = await raw("GET", "/stream", { signal: controller.signal });
          if (response.status === 401 || response.status === 403) return;
          if (!response.ok || !response.body) throw new Error("stream unavailable");
          delay = 1000;
          refetch(); // re-fetch after (re)connecting: events missed while away are never replayed
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const frames = buffer.split("\n\n");
            buffer = frames.pop() ?? "";
            for (const frame of frames) {
              if (frame.startsWith(":")) continue; // keep-alive
              if (frame.includes("event: unauthorized")) return;
              if (!frame.includes("event: ready")) refetch();
            }
          }
        } catch (error) {
          if ((error as Error).name === "AbortError") return;
        }
        if (stopped) return;
        await new Promise((resolve) => setTimeout(resolve, delay));
        delay = Math.min(delay * 2, 15000);
      }
    }

    void connect();
    return () => {
      stopped = true;
      controller?.abort();
    };
  }, [client, orgId, token]);
}

export const STREAM_URL = `${API}/stream`;

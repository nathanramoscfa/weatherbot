// frontend/src/events/useEventStream.ts
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  INVALIDATABLE_QUERY_KEYS,
  invalidatableQueryKey,
  isInvalidatableQueryKey,
} from "../api/keys.ts";
import type { components } from "../api/schema.ts";

export type StreamEvent = components["schemas"]["StreamEvent"];
export type EventKind = components["schemas"]["EventKind"];
export type EventStreamStatus = "connecting" | "connected" | "reconnecting";

export const STREAM_EVENT_DOM_NAME = "weatherbot:stream-event";

export interface UseEventStreamOptions {
  readonly onNotificationDisplay?: (event: StreamEvent) => void;
  readonly url?: string;
}

export interface UseEventStreamResult {
  readonly status: EventStreamStatus;
  readonly lastEventId: number | null;
}

const VALID_EVENT_KINDS: ReadonlySet<string> = new Set<EventKind>([
  "hello",
  "cycle",
  "snapshot",
  "assessment",
  "alert",
  "notification",
  "location",
  "health",
]);

function isStreamEvent(value: unknown): value is StreamEvent {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.id === "number" &&
    typeof record.kind === "string" &&
    VALID_EVENT_KINDS.has(record.kind) &&
    Array.isArray(record.invalidate)
  );
}

export function useEventStream(
  options: UseEventStreamOptions = {},
): UseEventStreamResult {
  const { onNotificationDisplay, url = "/api/events" } = options;
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<EventStreamStatus>("connecting");
  const [lastEventId, setLastEventId] = useState<number | null>(null);
  const hasReceivedHelloRef = useRef(false);
  const onNotificationRef = useRef(onNotificationDisplay);

  useEffect(() => {
    onNotificationRef.current = onNotificationDisplay;
  }, [onNotificationDisplay]);

  useEffect(() => {
    if (typeof EventSource === "undefined") {
      return undefined;
    }

    hasReceivedHelloRef.current = false;
    const source = new EventSource(url);

    const handleOpen = () => {
      setStatus("connected");
    };

    const handleError = () => {
      setStatus("reconnecting");
    };

    const handleMessage = (rawEvent: MessageEvent<unknown>) => {
      if (typeof rawEvent.data !== "string") {
        return;
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(rawEvent.data);
      } catch {
        return;
      }
      if (!isStreamEvent(parsed)) {
        return;
      }

      setStatus("connected");
      setLastEventId(parsed.id);

      if (parsed.kind === "hello") {
        if (!hasReceivedHelloRef.current) {
          hasReceivedHelloRef.current = true;
          return;
        }
        for (const key of INVALIDATABLE_QUERY_KEYS) {
          void queryClient.invalidateQueries({
            queryKey: invalidatableQueryKey(key),
          });
        }
        return;
      }

      for (const key of parsed.invalidate) {
        if (isInvalidatableQueryKey(key)) {
          void queryClient.invalidateQueries({
            queryKey: invalidatableQueryKey(key),
          });
        }
      }

      if (parsed.kind === "notification" && parsed.display) {
        onNotificationRef.current?.(parsed);
      }
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent<StreamEvent>(STREAM_EVENT_DOM_NAME, {
            detail: parsed,
          }),
        );
      }
    };

    source.addEventListener("open", handleOpen);
    source.addEventListener("error", handleError);
    source.addEventListener("message", handleMessage);

    return () => {
      source.removeEventListener("open", handleOpen);
      source.removeEventListener("error", handleError);
      source.removeEventListener("message", handleMessage);
      source.close();
    };
  }, [queryClient, url]);

  return { status, lastEventId };
}

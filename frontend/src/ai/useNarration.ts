// frontend/src/ai/useNarration.ts
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { postStream, readEventStream } from "./readEventStream.ts";
import type { AiUnavailableReason } from "./reasons.ts";
import {
  acquireAiStream,
  releaseAiStream,
  useAiStreamBusy,
} from "./streamLock.ts";
import { isNarrationStreamEvent } from "./streamEvents.ts";

type Basin = components["schemas"]["Basin"];
type Horizon = components["schemas"]["Horizon"];
type AiAreaResponse = components["schemas"]["AiAreaResponse"];

export interface WrittenNarration {
  readonly model: string;
  readonly modelName: string | null;
  readonly createdAt: string | null;
  readonly summary: string | null;
  readonly areas: readonly AiAreaResponse[];
  readonly caveat: string | null;
}

export type NarrationRun =
  | { readonly phase: "idle" }
  | { readonly phase: "streaming" }
  | { readonly phase: "done"; readonly narration: WrittenNarration }
  | {
      readonly phase: "withheld";
      readonly reason: string | null;
      readonly detail: string | null;
    }
  | {
      readonly phase: "unavailable";
      readonly reason: string | null;
      readonly detail: string | null;
    }
  | {
      readonly phase: "refused";
      readonly reason: AiUnavailableReason;
      readonly message: string;
    }
  | { readonly phase: "failed"; readonly status: number | null };

export interface UseNarrationResult {
  readonly run: NarrationRun;
  readonly busy: boolean;
  readonly interpret: () => void;
}

export function useNarration(basin: Basin, horizon: Horizon): UseNarrationResult {
  const queryClient = useQueryClient();
  const busy = useAiStreamBusy();
  const [run, setRun] = useState<NarrationRun>({ phase: "idle" });
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  const interpret = useCallback(() => {
    const slot = acquireAiStream();
    if (slot === null) {
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    const { signal } = controller;
    setRun({ phase: "streaming" });

    const stream = async () => {
      const outcome = await postStream(
        "/api/ai/narrations",
        { basin, horizon },
        signal,
      );
      if (outcome.kind === "aborted" || signal.aborted) {
        return;
      }
      if (outcome.kind === "refused") {
        setRun({
          phase: "refused",
          reason: outcome.reason,
          message: outcome.message,
        });
        return;
      }
      if (outcome.kind === "failed") {
        setRun({ phase: "failed", status: outcome.status });
        return;
      }
      let model = "";
      let modelName: string | null = null;
      for await (const { data } of readEventStream(
        outcome.response,
        isNarrationStreamEvent,
        signal,
      )) {
        switch (data.kind) {
          case "started":
            model = data.model ?? "";
            modelName = data.model_name;
            break;
          case "done":
            setRun({
              phase: "done",
              narration: {
                model,
                modelName,
                createdAt: data.created_at,
                summary: data.summary,
                areas: data.areas,
                caveat: data.caveat,
              },
            });
            void queryClient.invalidateQueries({
              queryKey: queryKeys.briefings(),
            });
            return;
          case "withheld":
            setRun({
              phase: "withheld",
              reason: data.reason,
              detail: data.detail,
            });
            void queryClient.invalidateQueries({
              queryKey: queryKeys.briefings(),
            });
            return;
          case "unavailable":
            setRun({
              phase: "unavailable",
              reason: data.reason,
              detail: data.detail,
            });
            return;
        }
      }
      if (!signal.aborted) {
        setRun({ phase: "failed", status: null });
      }
    };

    stream()
      .catch(() => {
        if (!signal.aborted) {
          setRun({ phase: "failed", status: null });
        }
      })
      .finally(() => {
        releaseAiStream(slot);
        if (controllerRef.current === controller) {
          controllerRef.current = null;
        }
        void queryClient.invalidateQueries({ queryKey: queryKeys.ai() });
      });
  }, [basin, horizon, queryClient]);

  return { run, busy, interpret };
}

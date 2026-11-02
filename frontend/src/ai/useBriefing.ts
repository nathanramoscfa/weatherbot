// frontend/src/ai/useBriefing.ts
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { queryKeys } from "../api/keys.ts";
import { fetchBriefings, type StoredBriefingResponse } from "./queries.ts";
import { postStream, readEventStream } from "./readEventStream.ts";
import type { AiUnavailableReason } from "./reasons.ts";
import {
  acquireAiStream,
  releaseAiStream,
  useAiStreamBusy,
} from "./streamLock.ts";
import { isBriefingStreamEvent, type SectionName } from "./streamEvents.ts";

export interface BriefingDraftSection {
  readonly name: SectionName;
  readonly text: string;
}

export interface BriefingStart {
  readonly model: string;
  readonly modelName: string | null;
  readonly asOf: string | null;
}

export type BriefingRun =
  | { readonly phase: "idle" }
  | {
      readonly phase: "streaming";
      readonly start: BriefingStart | null;
      readonly sections: readonly BriefingDraftSection[];
    }
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

export interface UseBriefingResult {
  readonly stored: StoredBriefingResponse | null;
  readonly loading: boolean;
  readonly failed: boolean;
  readonly run: BriefingRun;
  readonly running: boolean;
  readonly busy: boolean;
  readonly brief: (fresh: boolean) => void;
}

const IDLE: BriefingRun = { phase: "idle" };

export function useBriefing(location: string): UseBriefingResult {
  const queryClient = useQueryClient();
  const busy = useAiStreamBusy();
  const [run, setRun] = useState<BriefingRun>(IDLE);
  const controllerRef = useRef<AbortController | null>(null);

  const briefingsQuery = useQuery({
    queryKey: queryKeys.briefings(),
    queryFn: fetchBriefings,
  });

  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  const brief = useCallback(
    (fresh: boolean) => {
      const slot = acquireAiStream();
      if (slot === null) {
        return;
      }
      const controller = new AbortController();
      controllerRef.current = controller;
      const { signal } = controller;
      setRun({ phase: "streaming", start: null, sections: [] });

      const stream = async () => {
        const outcome = await postStream(
          "/api/ai/briefings",
          { location, new: fresh },
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
        let start: BriefingStart | null = null;
        let sections: readonly BriefingDraftSection[] = [];
        for await (const { data } of readEventStream(
          outcome.response,
          isBriefingStreamEvent,
          signal,
        )) {
          switch (data.kind) {
            case "started":
              start = {
                model: data.model ?? "",
                modelName: data.model_name,
                asOf: data.as_of,
              };
              setRun({ phase: "streaming", start, sections });
              break;
            case "section":
              if (data.section !== null && data.text !== null) {
                sections = [...sections, { name: data.section, text: data.text }];
                setRun({ phase: "streaming", start, sections });
              }
              break;
            case "done":
              await queryClient.invalidateQueries({
                queryKey: queryKeys.briefings(),
              });
              setRun(IDLE);
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
    },
    [location, queryClient],
  );

  const stored =
    briefingsQuery.data?.locations.find((item) => item.location === location)
      ?.briefing ?? null;

  return {
    stored,
    loading: briefingsQuery.isLoading,
    failed: briefingsQuery.isError,
    run,
    running: run.phase === "streaming",
    busy,
    brief,
  };
}

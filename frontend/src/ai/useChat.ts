// frontend/src/ai/useChat.ts
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { queryKeys } from "../api/keys.ts";
import { postStream, readEventStream } from "./readEventStream.ts";
import {
  acquireAiStream,
  releaseAiStream,
  useAiStreamBusy,
} from "./streamLock.ts";
import { type ChatTool, isChatStreamEvent } from "./streamEvents.ts";

export type ChatTurnStatus =
  | "streaming"
  | "done"
  | "withheld"
  | "unavailable"
  | "refused"
  | "failed";

export interface ChatTurn {
  readonly id: number;
  readonly question: string;
  readonly location: string | null;
  readonly tools: readonly ChatTool[];
  readonly sentences: readonly string[];
  readonly model: string | null;
  readonly modelName: string | null;
  readonly status: ChatTurnStatus;
  readonly finishedAt: string | null;
  readonly reason: string | null;
  readonly detail: string | null;
  readonly httpStatus: number | null;
}

export interface ChatClosure {
  readonly reason: string | null;
  readonly detail: string | null;
}

export interface UseChatResult {
  readonly conversationId: string | null;
  readonly turns: readonly ChatTurn[];
  readonly closed: ChatClosure | null;
  readonly running: boolean;
  readonly busy: boolean;
  readonly ask: (question: string, location: string | null) => boolean;
  readonly reset: () => void;
}

export function useChat(): UseChatResult {
  const queryClient = useQueryClient();
  const busy = useAiStreamBusy();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<readonly ChatTurn[]>([]);
  const [closed, setClosed] = useState<ChatClosure | null>(null);
  const [running, setRunning] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const nextIdRef = useRef(1);

  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  const ask = useCallback(
    (question: string, location: string | null): boolean => {
      if (closed !== null) {
        return false;
      }
      const slot = acquireAiStream();
      if (slot === null) {
        return false;
      }
      const controller = new AbortController();
      controllerRef.current = controller;
      const { signal } = controller;
      const id = nextIdRef.current;
      nextIdRef.current += 1;
      setRunning(true);
      setTurns((prev) => [
        ...prev,
        {
          id,
          question,
          location,
          tools: [],
          sentences: [],
          model: null,
          modelName: null,
          status: "streaming",
          finishedAt: null,
          reason: null,
          detail: null,
          httpStatus: null,
        },
      ]);

      const update = (patch: (turn: ChatTurn) => Partial<ChatTurn>) => {
        if (signal.aborted) {
          return;
        }
        setTurns((prev) =>
          prev.map((turn) => (turn.id === id ? { ...turn, ...patch(turn) } : turn)),
        );
      };

      const stream = async () => {
        const outcome = await postStream(
          "/api/ai/chat",
          { question, conversation_id: conversationId, location },
          signal,
        );
        if (outcome.kind === "aborted" || signal.aborted) {
          return;
        }
        if (outcome.kind === "refused") {
          update(() => ({
            status: "refused",
            reason: outcome.reason,
            detail: outcome.message,
            httpStatus: outcome.status,
          }));
          return;
        }
        if (outcome.kind === "failed") {
          update(() => ({ status: "failed", httpStatus: outcome.status }));
          return;
        }
        for await (const { data } of readEventStream(
          outcome.response,
          isChatStreamEvent,
          signal,
        )) {
          switch (data.kind) {
            case "started":
              if (data.conversation_id !== null) {
                setConversationId(data.conversation_id);
              }
              update(() => ({ model: data.model, modelName: data.model_name }));
              break;
            case "tool": {
              const tool = data.tool;
              if (tool !== null) {
                update((turn) => ({ tools: [...turn.tools, tool] }));
              }
              break;
            }
            case "text": {
              const sentence = data.text;
              if (sentence !== null) {
                update((turn) => ({ sentences: [...turn.sentences, sentence] }));
              }
              break;
            }
            case "done":
              update(() => ({
                status: "done",
                finishedAt: new Date().toISOString(),
              }));
              return;
            case "withheld":
            case "unavailable": {
              const status = data.kind;
              update(() => ({
                status,
                finishedAt: new Date().toISOString(),
                reason: data.reason,
                detail: data.detail,
              }));
              setClosed({ reason: data.reason, detail: data.detail });
              return;
            }
          }
        }
        update(() => ({ status: "failed" }));
      };

      stream()
        .catch(() => {
          update(() => ({ status: "failed" }));
        })
        .finally(() => {
          releaseAiStream(slot);
          if (controllerRef.current === controller) {
            controllerRef.current = null;
            setRunning(false);
          }
          void queryClient.invalidateQueries({ queryKey: queryKeys.ai() });
        });
      return true;
    },
    [closed, conversationId, queryClient],
  );

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setRunning(false);
    setConversationId(null);
    setTurns([]);
    setClosed(null);
  }, []);

  return { conversationId, turns, closed, running, busy, ask, reset };
}

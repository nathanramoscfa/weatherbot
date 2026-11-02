// frontend/src/ai/readEventStream.ts
import { apiClient } from "../api/client.ts";
import type { paths } from "../api/schema.ts";
import { type AiUnavailableReason, isAiUnavailableReason } from "./reasons.ts";

export interface ServerSentEvent<T> {
  readonly event: string;
  readonly id: string | null;
  readonly data: T;
}

export type EventGuard<T> = (value: unknown) => value is T;

export type AiStreamPath =
  | "/api/ai/briefings"
  | "/api/ai/chat"
  | "/api/ai/narrations";

export type AiStreamBody<P extends AiStreamPath> =
  paths[P]["post"]["requestBody"]["content"]["application/json"];

export type PostStreamResult =
  | { readonly kind: "stream"; readonly response: Response }
  | {
      readonly kind: "refused";
      readonly status: number;
      readonly reason: AiUnavailableReason;
      readonly message: string;
    }
  | { readonly kind: "failed"; readonly status: number | null }
  | { readonly kind: "aborted" };

const FRAME_END = "\n\n";

interface Frame {
  readonly event: string;
  readonly id: string | null;
  readonly data: string | null;
}

function parseFrame(block: string, lastId: string | null): Frame {
  let event = "";
  let id = lastId;
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) {
      continue;
    }
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }
    if (field === "event") {
      event = value;
    } else if (field === "data") {
      data.push(value);
    } else if (field === "id" && !value.includes("\0")) {
      id = value;
    }
  }
  return {
    event: event || "message",
    id,
    data: data.length > 0 ? data.join("\n") : null,
  };
}

export async function* readEventStream<T>(
  response: Response,
  guard: EventGuard<T>,
  signal?: AbortSignal,
): AsyncGenerator<ServerSentEvent<T>, void, undefined> {
  const body = response.body;
  if (body === null || signal?.aborted) {
    return;
  }
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let pendingReturn = false;
  let lastId: string | null = null;
  let finished = false;

  const append = (text: string) => {
    let chunk = pendingReturn ? `\r${text}` : text;
    pendingReturn = chunk.endsWith("\r");
    if (pendingReturn) {
      chunk = chunk.slice(0, -1);
    }
    buffer += chunk.replace(/\r\n?/g, "\n");
  };

  const onAbort = () => {
    reader.cancel().catch(() => undefined);
  };
  signal?.addEventListener("abort", onAbort, { once: true });

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        finished = true;
        break;
      }
      append(decoder.decode(value, { stream: true }));
      let end = buffer.indexOf(FRAME_END);
      while (end !== -1) {
        const frame = parseFrame(buffer.slice(0, end), lastId);
        buffer = buffer.slice(end + FRAME_END.length);
        lastId = frame.id;
        if (frame.data !== null) {
          let parsed: unknown;
          try {
            parsed = JSON.parse(frame.data);
          } catch {
            parsed = undefined;
          }
          if (guard(parsed)) {
            yield { event: frame.event, id: frame.id, data: parsed };
          }
        }
        if (signal?.aborted) {
          return;
        }
        end = buffer.indexOf(FRAME_END);
      }
    }
  } finally {
    signal?.removeEventListener("abort", onAbort);
    if (!finished) {
      reader.cancel().catch(() => undefined);
    }
  }
}

function refusalOf(
  error: unknown,
): { reason: AiUnavailableReason; message: string } | null {
  if (typeof error !== "object" || error === null) {
    return null;
  }
  const detail = new Map<string, unknown>(Object.entries(error)).get("detail");
  if (typeof detail !== "object" || detail === null) {
    return null;
  }
  const fields = new Map<string, unknown>(Object.entries(detail));
  const reason = fields.get("reason");
  const message = fields.get("message");
  if (!isAiUnavailableReason(reason) || typeof message !== "string") {
    return null;
  }
  return { reason, message };
}

type AiStreamRequest = {
  [P in AiStreamPath]: { readonly path: P; readonly body: AiStreamBody<P> };
}[AiStreamPath];

function send(request: AiStreamRequest, signal: AbortSignal) {
  const init = { parseAs: "stream", signal } as const;
  switch (request.path) {
    case "/api/ai/briefings":
      return apiClient.POST(request.path, { ...init, body: request.body });
    case "/api/ai/chat":
      return apiClient.POST(request.path, { ...init, body: request.body });
    case "/api/ai/narrations":
      return apiClient.POST(request.path, { ...init, body: request.body });
  }
}

export async function postStream<P extends AiStreamPath>(
  path: P,
  body: AiStreamBody<P>,
  signal: AbortSignal,
): Promise<PostStreamResult> {
  let result: { error?: unknown; response: Response };
  try {
    // P ties path to body, which the union spells out for the switch.
    result = await send({ path, body } as AiStreamRequest, signal);
  } catch {
    return signal.aborted ? { kind: "aborted" } : { kind: "failed", status: null };
  }
  const { response } = result;
  if (response.ok && response.body !== null) {
    return { kind: "stream", response };
  }
  if (response.status === 429 || response.status === 503) {
    const refusal = refusalOf(result.error);
    if (refusal !== null) {
      return { kind: "refused", status: response.status, ...refusal };
    }
  }
  return { kind: "failed", status: response.status };
}

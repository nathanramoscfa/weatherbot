// frontend/src/test/ai.ts
import { vi } from "vitest";
import type {
  BriefingStreamEvent,
  ChatStreamEvent,
  NarrationStreamEvent,
} from "../ai/streamEvents.ts";
import { apiClient } from "../api/client.ts";
import type { components } from "../api/schema.ts";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import aiCallsFixture from "./fixtures/ai-calls.json";
import aiFixture from "./fixtures/ai.json";
import briefingsFixture from "./fixtures/briefings.json";
import narrationsFixture from "./fixtures/narrations.json";
import outlookFixture from "./fixtures/outlook.json";
import summariesFixture from "./fixtures/summaries.json";

type Schemas = components["schemas"];

export const TYPED_AI = asSchema<Schemas["AiStatusResponse"]>(
  aiFixture satisfies JsonFixture<Schemas["AiStatusResponse"]>,
);
export const TYPED_AI_CALLS = asSchema<Schemas["AiCallsResponse"]>(
  aiCallsFixture satisfies JsonFixture<Schemas["AiCallsResponse"]>,
);
export const TYPED_BRIEFINGS = asSchema<Schemas["BriefingsResponse"]>(
  briefingsFixture satisfies JsonFixture<Schemas["BriefingsResponse"]>,
);
export const TYPED_SUMMARIES = asSchema<Schemas["SummariesResponse"]>(
  summariesFixture satisfies JsonFixture<Schemas["SummariesResponse"]>,
);
export const TYPED_NARRATIONS = asSchema<Schemas["NarrationsResponse"]>(
  narrationsFixture satisfies JsonFixture<Schemas["NarrationsResponse"]>,
);
export const TYPED_OUTLOOK = asSchema<Schemas["OutlookGraphicsResponse"]>(
  outlookFixture satisfies JsonFixture<Schemas["OutlookGraphicsResponse"]>,
);

export function aiStatus(
  patch: Partial<Schemas["AiStatusResponse"]>,
): Schemas["AiStatusResponse"] {
  return { ...TYPED_AI, ...patch };
}

export function sseFrame(data: unknown): string {
  return `data: ${JSON.stringify(data)}\n\n`;
}

export interface ControlledStream {
  readonly stream: ReadableStream<Uint8Array>;
  readonly push: (text: string) => void;
  readonly close: () => void;
}

export function controlledStream(): ControlledStream {
  const encoder = new TextEncoder();
  let controller: ReadableStreamDefaultController<Uint8Array> | undefined;
  const stream = new ReadableStream<Uint8Array>({
    start(started) {
      controller = started;
    },
  });
  return {
    stream,
    push: (text) => controller?.enqueue(encoder.encode(text)),
    close: () => controller?.close(),
  };
}

export function streamOf(...frames: unknown[]): ReadableStream<Uint8Array> {
  const sse = controlledStream();
  for (const frame of frames) {
    sse.push(sseFrame(frame));
  }
  sse.close();
  return sse.stream;
}

export function streamAnswer(stream: ReadableStream<Uint8Array>) {
  const response = new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
  return { data: response.body, response } as never;
}

export function refusalAnswer(
  status: 429 | 503,
  reason: Schemas["AiUnavailableReason"],
  message: string,
) {
  return {
    error: { detail: { reason, message } },
    response: new Response(null, { status }),
  } as never;
}

export function mockGet(responses: ReadonlyMap<string, unknown>) {
  return vi.spyOn(apiClient, "GET").mockImplementation(((path: string) => {
    const data = responses.get(path);
    return Promise.resolve(
      data === undefined
        ? { error: {}, response: new Response(null, { status: 404 }) }
        : { data, response: new Response(null, { status: 200 }) },
    );
  }) as never);
}

export function briefingEvent(
  patch: Partial<BriefingStreamEvent> & Pick<BriefingStreamEvent, "kind">,
): BriefingStreamEvent {
  return {
    model: null,
    model_name: null,
    assessment_id: null,
    as_of: null,
    prompt_version: null,
    section: null,
    text: null,
    output_id: null,
    created_at: null,
    reused: null,
    reason: null,
    detail: null,
    ...patch,
  };
}

export function chatEvent(
  patch: Partial<ChatStreamEvent> & Pick<ChatStreamEvent, "kind">,
): ChatStreamEvent {
  return {
    conversation_id: null,
    model: null,
    model_name: null,
    tool: null,
    text: null,
    call_ids: [],
    reason: null,
    detail: null,
    ...patch,
  };
}

export function narrationEvent(
  patch: Partial<NarrationStreamEvent> & Pick<NarrationStreamEvent, "kind">,
): NarrationStreamEvent {
  return {
    model: null,
    model_name: null,
    basin: null,
    horizon: null,
    graphic_sha256: null,
    two_issued_at: null,
    prompt_version: null,
    output_id: null,
    created_at: null,
    reused: null,
    summary: null,
    areas: [],
    caveat: null,
    reason: null,
    detail: null,
    ...patch,
  };
}

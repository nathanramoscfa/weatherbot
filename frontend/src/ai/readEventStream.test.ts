// frontend/src/ai/readEventStream.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import {
  briefingEvent,
  controlledStream,
  refusalAnswer,
  streamAnswer,
  streamOf,
} from "../test/ai.ts";
import {
  postStream,
  readEventStream,
  type ServerSentEvent,
} from "./readEventStream.ts";
import { isBriefingStreamEvent, isChatStreamEvent } from "./streamEvents.ts";

function isPayload(value: unknown): value is { n: number; text?: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { n?: unknown }).n === "number"
  );
}

function responseOf(...chunks: string[]): Response {
  const sse = controlledStream();
  for (const chunk of chunks) {
    sse.push(chunk);
  }
  sse.close();
  return new Response(sse.stream);
}

async function collect<T>(
  events: AsyncGenerator<ServerSentEvent<T>, void, undefined>,
): Promise<ServerSentEvent<T>[]> {
  const out: ServerSentEvent<T>[] = [];
  for await (const event of events) {
    out.push(event);
  }
  return out;
}

describe("readEventStream", () => {
  it("splits frames on blank lines and reads event, data, and id lines", async () => {
    const events = await collect(
      readEventStream(
        responseOf(
          'event: briefing\ndata: {"n": 1}\nid: 7\n\n',
          'data: {"n": 2}\n\n',
        ),
        isPayload,
      ),
    );
    expect(events).toEqual([
      { event: "briefing", id: "7", data: { n: 1 } },
      { event: "message", id: "7", data: { n: 2 } },
    ]);
  });

  it("joins multi-line data with newlines and reads frames split across chunks and CRLF line ends", async () => {
    const events = await collect(
      readEventStream(
        responseOf(
          'data: {"n": 1,\r\ndata: "text": "a',
          '"}\r',
          "\n\r\n",
          'data: {"n": 2}\n',
          "\n",
        ),
        isPayload,
      ),
    );
    expect(events.map((event) => event.data)).toEqual([
      { n: 1, text: "a" },
      { n: 2 },
    ]);
  });

  it("ignores comment lines, keep-alive pings, frames without data, malformed JSON, and data the guard refuses", async () => {
    const events = await collect(
      readEventStream(
        responseOf(
          ": ping\n\n",
          ': comment\ndata: {"n": 1}\n\n',
          "event: empty\n\n",
          "data: {not json\n\n",
          'data: {"kind": "not-a-kind"}\n\n',
          'data: {"n": 3}\n\n',
          'data: {"n": 4}',
        ),
        isPayload,
      ),
    );
    expect(events.map((event) => event.data)).toEqual([{ n: 1 }, { n: 3 }]);
  });

  it("checks each frame against the generated stream type", async () => {
    const events = await collect(
      readEventStream(
        new Response(
          streamOf(
            briefingEvent({ kind: "section", section: "situation", text: "A" }),
            { ...briefingEvent({ kind: "section" }), section: "not_a_section" },
            { ...briefingEvent({ kind: "done" }), output_id: "seven" },
            briefingEvent({ kind: "done", output_id: 7 }),
          ),
        ),
        isBriefingStreamEvent,
      ),
    );
    expect(events.map((event) => event.data.kind)).toEqual(["section", "done"]);
    expect(isChatStreamEvent({ kind: "tool", tool: "rm_rf" })).toBe(false);
    expect(isChatStreamEvent({ kind: "done", call_ids: [1, "2"] })).toBe(false);
  });

  it("stops reading and cancels the body when the signal aborts", async () => {
    const sse = controlledStream();
    const controller = new AbortController();
    const events = readEventStream(
      new Response(sse.stream),
      isPayload,
      controller.signal,
    );
    sse.push('data: {"n": 1}\n\n');
    const first = await events.next();
    expect(first.value).toEqual({ event: "message", id: null, data: { n: 1 } });
    const pending = events.next();
    controller.abort();
    expect(await pending).toEqual({ done: true, value: undefined });
    expect(() => sse.push('data: {"n": 2}\n\n')).toThrow();
  });

  it("reads nothing once the signal has already aborted", async () => {
    const controller = new AbortController();
    controller.abort();
    const events = await collect(
      readEventStream(responseOf('data: {"n": 1}\n\n'), isPayload, controller.signal),
    );
    expect(events).toEqual([]);
  });
});

describe("postStream", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends same-origin JSON through the generated client and returns the stream", async () => {
    const postSpy = vi
      .spyOn(apiClient, "POST")
      .mockResolvedValue(streamAnswer(streamOf(briefingEvent({ kind: "done" }))));
    const controller = new AbortController();

    const outcome = await postStream(
      "/api/ai/briefings",
      { location: "Miami-Dade County Hall", new: false },
      controller.signal,
    );

    expect(postSpy).toHaveBeenCalledWith("/api/ai/briefings", {
      body: { location: "Miami-Dade County Hall", new: false },
      parseAs: "stream",
      signal: controller.signal,
    });
    expect(outcome.kind).toBe("stream");
  });

  it("maps a 429 JSON answer to its reason", async () => {
    vi.spyOn(apiClient, "POST").mockResolvedValue(
      refusalAnswer(429, "capped", "today's AI cap is reached"),
    );
    const outcome = await postStream(
      "/api/ai/chat",
      { question: "Why?" },
      new AbortController().signal,
    );
    expect(outcome).toEqual({
      kind: "refused",
      status: 429,
      reason: "capped",
      message: "today's AI cap is reached",
    });
  });

  it("maps a 503 JSON answer to its reason", async () => {
    vi.spyOn(apiClient, "POST").mockResolvedValue(
      refusalAnswer(503, "paused", "AI is paused"),
    );
    const outcome = await postStream(
      "/api/ai/narrations",
      { basin: "atl", horizon: "7d0" },
      new AbortController().signal,
    );
    expect(outcome).toEqual({
      kind: "refused",
      status: 503,
      reason: "paused",
      message: "AI is paused",
    });
  });

  it("reports other failures by status, a thrown request as failed, and an aborted one as aborted", async () => {
    const postSpy = vi.spyOn(apiClient, "POST");
    postSpy.mockResolvedValueOnce({
      error: { detail: [{ msg: "bad" }] },
      response: new Response(null, { status: 422 }),
    });
    expect(
      await postStream(
        "/api/ai/chat",
        { question: "" },
        new AbortController().signal,
      ),
    ).toEqual({ kind: "failed", status: 422 });

    postSpy.mockResolvedValueOnce(
      { error: "not json", response: new Response(null, { status: 503 }) },
    );
    expect(
      await postStream(
        "/api/ai/chat",
        { question: "Why?" },
        new AbortController().signal,
      ),
    ).toEqual({ kind: "failed", status: 503 });

    postSpy.mockRejectedValueOnce(new TypeError("network"));
    expect(
      await postStream(
        "/api/ai/chat",
        { question: "Why?" },
        new AbortController().signal,
      ),
    ).toEqual({ kind: "failed", status: null });

    const controller = new AbortController();
    controller.abort();
    postSpy.mockRejectedValueOnce(new DOMException("aborted", "AbortError"));
    expect(
      await postStream("/api/ai/chat", { question: "Why?" }, controller.signal),
    ).toEqual({ kind: "aborted" });
  });
});

// frontend/src/events/useEventStream.test.tsx
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  INVALIDATABLE_QUERY_KEYS,
  queryKeys,
  STATIC_QUERY_KEYS,
} from "../api/keys.ts";
import { createAppQueryClient } from "../main.tsx";
import { type StreamEvent, useEventStream } from "./useEventStream.ts";

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  closed = false;
  private readonly listeners = new Map<string, Set<(event: Event) => void>>();

  constructor(url: string | URL) {
    this.url = String(url);
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    const set = this.listeners.get(type) ?? new Set<(event: Event) => void>();
    const fn =
      typeof listener === "function"
        ? listener
        : (ev: Event) => listener.handleEvent(ev);
    set.add(fn);
    this.listeners.set(type, set);
  }

  removeEventListener(
    type: string,
    listener: EventListenerOrEventListenerObject,
  ) {
    const set = this.listeners.get(type);
    if (!set || typeof listener !== "function") {
      return;
    }
    set.delete(listener);
  }

  close() {
    this.closed = true;
  }

  emitOpen() {
    const set = this.listeners.get("open");
    if (!set) {
      return;
    }
    const event = new Event("open");
    for (const listener of set) {
      listener(event);
    }
  }

  emitError() {
    const set = this.listeners.get("error");
    if (!set) {
      return;
    }
    const event = new Event("error");
    for (const listener of set) {
      listener(event);
    }
  }

  emitStreamEvent(payload: StreamEvent) {
    const set = this.listeners.get("message");
    if (!set) {
      return;
    }
    const event = new MessageEvent("message", {
      data: JSON.stringify(payload),
    });
    for (const listener of set) {
      listener(event);
    }
  }
}

function makeStreamEvent(overrides: Partial<StreamEvent>): StreamEvent {
  return {
    id: 1,
    kind: "hello",
    at: "2026-10-12T15:00:00Z",
    invalidate: [...INVALIDATABLE_QUERY_KEYS],
    started_at: "2026-10-12T14:00:00Z",
    cycle_id: 1,
    runner: null,
    trigger: null,
    status: null,
    snapshot_id: null,
    location: null,
    assessment_id: null,
    level: null,
    complete: null,
    notification_id: null,
    notification_kind: null,
    escalation: null,
    title: null,
    body: null,
    display: false,
    ...overrides,
  };
}

describe("useEventStream", () => {
  const originalEventSource = globalThis.EventSource;

  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  afterEach(() => {
    vi.stubGlobal("EventSource", originalEventSource);
  });

  it("refetches nothing on the first hello and invalidates every query on a reconnect hello", async () => {
    const queryClient = createAppQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const healthFetcher = vi.fn().mockResolvedValue({ ok: true });
    const replayFetcher = vi.fn().mockResolvedValue({ storms: [] });

    function Harness() {
      const { status, lastEventId } = useEventStream();
      useQuery({
        queryKey: queryKeys.health(),
        queryFn: healthFetcher,
      });
      useQuery({
        queryKey: queryKeys.replay(),
        queryFn: replayFetcher,
      });
      return (
        <div>
          <span data-testid="stream-status">{status}</span>
          <span data-testid="last-event-id">{String(lastEventId ?? "none")}</span>
        </div>
      );
    }

    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <Harness />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(healthFetcher).toHaveBeenCalledTimes(1);
      expect(replayFetcher).toHaveBeenCalledTimes(1);
    });
    expect(FakeEventSource.instances).toHaveLength(1);
    const source = FakeEventSource.instances[0]!;
    expect(source.url).toBe("/api/events");

    act(() => {
      source.emitStreamEvent(makeStreamEvent({ id: 1, kind: "hello" }));
    });

    expect(screen.getByTestId("stream-status")).toHaveTextContent("connected");
    expect(screen.getByTestId("last-event-id")).toHaveTextContent("1");
    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(healthFetcher).toHaveBeenCalledTimes(1);
    expect(replayFetcher).toHaveBeenCalledTimes(1);

    act(() => {
      source.emitError();
    });
    expect(screen.getByTestId("stream-status")).toHaveTextContent("reconnecting");

    act(() => {
      source.emitStreamEvent(makeStreamEvent({ id: 2, kind: "hello" }));
    });

    expect(screen.getByTestId("stream-status")).toHaveTextContent("connected");
    expect(screen.getByTestId("last-event-id")).toHaveTextContent("2");
    expect(invalidateSpy).toHaveBeenCalledTimes(INVALIDATABLE_QUERY_KEYS.length);
    for (const key of INVALIDATABLE_QUERY_KEYS) {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: [key] });
    }
    for (const staticKey of STATIC_QUERY_KEYS) {
      expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: [staticKey] });
    }
    await waitFor(() => {
      expect(healthFetcher).toHaveBeenCalledTimes(2);
    });
    expect(replayFetcher).toHaveBeenCalledTimes(1);

    unmount();
    expect(source.closed).toBe(true);
  });

  it("invalidates only the exact keys named on an event and invokes the display callback for display notifications", () => {
    const queryClient = createAppQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const onDisplay = vi.fn();

    function Harness() {
      useEventStream({ onNotificationDisplay: onDisplay });
      return <div>subscribed</div>;
    }

    render(
      <QueryClientProvider client={queryClient}>
        <Harness />
      </QueryClientProvider>,
    );

    const source = FakeEventSource.instances[0]!;

    act(() => {
      source.emitStreamEvent(makeStreamEvent({ id: 1, kind: "hello" }));
    });
    expect(invalidateSpy).not.toHaveBeenCalled();

    act(() => {
      source.emitStreamEvent(
        makeStreamEvent({
          id: 2,
          kind: "assessment",
          invalidate: ["assessments", "timeline"],
          location: "Miami-Dade",
          level: 3,
          complete: true,
        }),
      );
    });

    expect(invalidateSpy).toHaveBeenCalledTimes(2);
    expect(invalidateSpy).toHaveBeenNthCalledWith(1, {
      queryKey: ["assessments"],
    });
    expect(invalidateSpy).toHaveBeenNthCalledWith(2, {
      queryKey: ["timeline"],
    });
    expect(onDisplay).not.toHaveBeenCalled();

    invalidateSpy.mockClear();

    const silentNotification = makeStreamEvent({
      id: 3,
      kind: "notification",
      invalidate: ["notifications", "timeline"],
      notification_id: 10,
      notification_kind: "location",
      display: false,
    });
    act(() => {
      source.emitStreamEvent(silentNotification);
    });
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
    expect(onDisplay).not.toHaveBeenCalled();

    const shownNotification = makeStreamEvent({
      id: 4,
      kind: "notification",
      invalidate: ["notifications", "timeline"],
      notification_id: 11,
      notification_kind: "location",
      level: 5,
      escalation: true,
      title: "Level 5 — Hurricane Warning",
      body: ["Hurricane Warning in effect."],
      display: true,
    });
    act(() => {
      source.emitStreamEvent(shownNotification);
    });
    expect(onDisplay).toHaveBeenCalledTimes(1);
    expect(onDisplay).toHaveBeenCalledWith(shownNotification);
  });
});

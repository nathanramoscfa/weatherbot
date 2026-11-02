// frontend/src/ai/BriefingPanel.test.tsx
import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import {
  aiStatus,
  briefingEvent,
  controlledStream,
  mockGet,
  refusalAnswer,
  sseFrame,
  streamAnswer,
  streamOf,
  TYPED_AI,
  TYPED_BRIEFINGS,
} from "../test/ai.ts";
import { BriefingPanel } from "./BriefingPanel.tsx";

type BriefingsResponse = components["schemas"]["BriefingsResponse"];
type StoredBriefing = components["schemas"]["StoredBriefingResponse"];

const MIAMI = {
  location: "Miami-Dade County Hall",
  assessmentId: 3,
  assessedAt: "2026-10-13T01:31:00Z",
};
const LONDON = {
  location: "Parliament Square",
  assessmentId: 4,
  assessedAt: "2026-10-13T01:31:00Z",
};
const MIAMI_BRIEFING: StoredBriefing = TYPED_BRIEFINGS.locations[0]!.briefing!;

function briefings(
  miami: StoredBriefing | null,
  london: StoredBriefing | null,
): BriefingsResponse {
  return {
    ...TYPED_BRIEFINGS,
    locations: [
      { location: MIAMI.location, assessment_id: 3, briefing: miami },
      { location: LONDON.location, assessment_id: 4, briefing: london },
    ],
  };
}

function seeded(
  ai = TYPED_AI,
  stored: BriefingsResponse = TYPED_BRIEFINGS,
): QueryClient {
  const queryClient = createAppQueryClient();
  queryClient.setQueryData(queryKeys.ai(), ai);
  queryClient.setQueryData(queryKeys.briefings(), stored);
  return queryClient;
}

function renderPanels(
  queryClient: QueryClient,
  panels: readonly (typeof MIAMI)[] = [MIAMI],
) {
  return render(
    <QueryClientProvider client={queryClient}>
      {panels.map((panel) => (
        <BriefingPanel key={panel.location} {...panel} />
      ))}
    </QueryClientProvider>,
  );
}

function panelFor(location: string): HTMLElement {
  return screen.getByRole("region", { name: `AI briefing for ${location}` });
}

describe("BriefingPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the stored briefing with its label, sections, and sources, linking only the URLs the API supplied", () => {
    renderPanels(seeded());
    const panel = panelFor(MIAMI.location);

    const label = within(panel).getByTestId("ai-label");
    expect(label).toHaveTextContent("AI briefing");
    expect(label).toHaveTextContent("Claude Sonnet 5.5");
    expect(label).toHaveTextContent("written 2026-10-13 01:33 UTC");
    expect(label).toHaveTextContent("for the 2026-10-13 01:31 UTC assessment");
    expect(label).toHaveTextContent("may be wrong");

    expect(
      within(panel).getByText(/^Hurricane Simon is in the eastern Pacific/),
    ).toBeInTheDocument();
    expect(within(panel).getByText("Normal activities.")).toBeInTheDocument();
    expect(
      within(panel).getByText("NWS alert: Rip Current Statement"),
    ).toBeInTheDocument();
    const links = within(panel).getAllByRole("link", { name: /official page/ });
    expect(links).toHaveLength(MIAMI_BRIEFING.sources.length);
    for (const link of links) {
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
      expect(link).toHaveAttribute("target", "_blank");
      expect(link.getAttribute("href")).toMatch(/^https:\/\//);
    }
    expect(within(panel).getByRole("button", { name: "Brief me" })).toBeEnabled();
  });

  it("streams a new briefing section by section with a writing indicator, then replaces the draft with the stored briefing", async () => {
    const user = userEvent.setup();
    const queryClient = seeded(TYPED_AI, briefings(MIAMI_BRIEFING, null));
    const sse = controlledStream();
    const postSpy = vi
      .spyOn(apiClient, "POST")
      .mockResolvedValue(streamAnswer(sse.stream));
    const storedLondon: StoredBriefing = {
      ...MIAMI_BRIEFING,
      id: 9,
      assessment_id: 4,
      created_at: "2026-10-13T01:40:00Z",
      situation: "Stored situation for Parliament Square.",
    };
    mockGet(
      new Map<string, unknown>([
        ["/api/ai/briefings", briefings(MIAMI_BRIEFING, storedLondon)],
        ["/api/ai", TYPED_AI],
      ]),
    );
    renderPanels(queryClient, [MIAMI, LONDON]);

    const london = panelFor(LONDON.location);
    await user.click(within(london).getByRole("button", { name: "Brief me" }));
    expect(postSpy).toHaveBeenCalledWith(
      "/api/ai/briefings",
      expect.objectContaining({
        body: { location: "Parliament Square", new: false },
        parseAs: "stream",
      }),
    );
    expect(within(london).getByRole("button", { name: "Brief me" })).toBeDisabled();
    expect(
      within(panelFor(MIAMI.location)).getByRole("button", { name: "Brief me" }),
    ).toBeDisabled();

    act(() => {
      sse.push(
        sseFrame(
          briefingEvent({
            kind: "started",
            model: "claude-sonnet-5-5",
            model_name: "Claude Sonnet 5.5",
            assessment_id: 4,
            as_of: "2026-10-13T01:31:00Z",
          }),
        ),
      );
      sse.push(
        sseFrame(
          briefingEvent({
            kind: "section",
            section: "situation",
            text: "First, the situation.",
          }),
        ),
      );
    });
    expect(await within(london).findByText("First, the situation.")).toBeInTheDocument();
    expect(within(london).getByText("Writing the briefing…")).toBeInTheDocument();
    expect(within(london).queryByText("Then what it means.")).toBeNull();

    act(() => {
      sse.push(
        sseFrame(
          briefingEvent({
            kind: "section",
            section: "what_it_means_here",
            text: "Then what it means.",
          }),
        ),
      );
      sse.push(
        sseFrame(
          briefingEvent({
            kind: "section",
            section: "actions",
            text: "Normal activities.\nFollow local officials.",
          }),
        ),
      );
    });
    await within(london).findByText("Then what it means.");
    expect(
      within(london)
        .getAllByRole("heading", { level: 4 })
        .map((heading) => heading.textContent),
    ).toEqual(["Situation", "What it means here", "Actions"]);

    act(() => {
      sse.push(
        sseFrame(
          briefingEvent({
            kind: "done",
            output_id: 9,
            created_at: "2026-10-13T01:40:00Z",
            reused: false,
          }),
        ),
      );
      sse.close();
    });

    expect(
      await within(london).findByText("Stored situation for Parliament Square."),
    ).toBeInTheDocument();
    expect(within(london).queryByText("Writing the briefing…")).toBeNull();
    expect(within(london).queryByText("First, the situation.")).toBeNull();
    expect(within(london).getByTestId("ai-label")).toHaveTextContent(
      "written 2026-10-13 01:40 UTC",
    );
    await waitFor(() => {
      expect(
        within(london).getByRole("button", { name: "Brief me" }),
      ).toBeEnabled();
    });
  });

  it("removes every streamed section when the briefing is withheld and shows only the reason", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "POST").mockResolvedValue(
      streamAnswer(
        streamOf(
          briefingEvent({ kind: "started", model: "claude-sonnet-5-5" }),
          briefingEvent({
            kind: "section",
            section: "situation",
            text: "A section that will be withdrawn.",
          }),
          briefingEvent({
            kind: "withheld",
            reason: "level",
            detail: "it stated level 3, but the engine's level is 1",
            output_id: 10,
          }),
        ),
      ),
    );
    mockGet(
      new Map<string, unknown>([
        ["/api/ai/briefings", TYPED_BRIEFINGS],
        ["/api/ai", TYPED_AI],
      ]),
    );
    renderPanels(seeded(TYPED_AI, briefings(MIAMI_BRIEFING, null)), [LONDON]);

    await user.click(screen.getByRole("button", { name: "Brief me" }));

    expect(
      await screen.findByText(
        "Withheld: it stated level 3, but the engine's level is 1",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("A section that will be withdrawn.")).toBeNull();
    expect(screen.queryByText("Writing the briefing…")).toBeNull();
  });

  it("shows a stored withheld briefing's reason and none of its text", () => {
    const withheld: StoredBriefing = {
      ...MIAMI_BRIEFING,
      status: "withheld",
      withheld_reason: "level",
      situation: null,
      what_it_means_here: null,
      timeline: [],
      actions: [],
      sources: [],
    };
    renderPanels(seeded(TYPED_AI, briefings(withheld, null)));

    expect(
      screen.getByText("Withheld: it stated a level other than the engine's"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Hurricane Simon/)).toBeNull();
    expect(screen.getByRole("button", { name: "Brief me again" })).toBeEnabled();
  });

  it("says which assessment a stale briefing was written for and offers Brief me again", async () => {
    const user = userEvent.setup();
    const postSpy = vi
      .spyOn(apiClient, "POST")
      .mockResolvedValue(refusalAnswer(503, "paused", "AI is paused"));
    mockGet(new Map<string, unknown>([["/api/ai", TYPED_AI]]));
    const stale: StoredBriefing = { ...MIAMI_BRIEFING, assessment_id: 2, stale: true };
    renderPanels(seeded(TYPED_AI, briefings(stale, null)));

    expect(
      screen.getByText(/Stale: this briefing was written for assessment no\. 2/),
    ).toHaveTextContent("the newer assessment no. 3 (2026-10-13 01:31 UTC)");
    expect(screen.getByTestId("ai-label")).toHaveTextContent(
      "for assessment no. 2",
    );

    await user.click(screen.getByRole("button", { name: "Brief me again" }));
    expect(postSpy).toHaveBeenCalledWith(
      "/api/ai/briefings",
      expect.objectContaining({
        body: { location: MIAMI.location, new: false },
      }),
    );
    expect(await screen.findByTestId("ai-state-banner")).toHaveTextContent(
      "AI paused by you — resume it in Settings.",
    );
  });

  it("asks for a new briefing when the stored one is current", async () => {
    const user = userEvent.setup();
    const postSpy = vi
      .spyOn(apiClient, "POST")
      .mockResolvedValue(refusalAnswer(429, "capped", "today's AI cap is reached"));
    mockGet(new Map<string, unknown>([["/api/ai", TYPED_AI]]));
    renderPanels(seeded());

    await user.click(screen.getByRole("button", { name: "Brief me" }));
    expect(postSpy).toHaveBeenCalledWith(
      "/api/ai/briefings",
      expect.objectContaining({ body: { location: MIAMI.location, new: true } }),
    );
    expect(await screen.findByTestId("ai-state-banner")).toHaveTextContent(
      "AI paused: today's $1.00 cap is reached.",
    );
    expect(screen.getByText(/^Hurricane Simon/)).toBeInTheDocument();
  });

  it.each([
    [
      "off",
      aiStatus({ state: "off", reason: "no_credential", credential_source: "none" }),
      "AI is off: no Anthropic credential. Set ANTHROPIC_API_KEY or run ant auth login, then restart serve.",
    ],
    [
      "paused",
      aiStatus({ state: "paused", reason: "paused", paused: true }),
      "AI paused by you — resume it in Settings.",
    ],
    [
      "capped",
      aiStatus({ state: "capped", reason: "capped" }),
      "AI paused: today's $1.00 cap is reached. It resets at midnight; you can allow more in Settings.",
    ],
    [
      "unavailable",
      aiStatus({ state: "unavailable", reason: "auth_failed" }),
      "AI unavailable: authentication failed — check the credential, then restart serve.",
    ],
  ])("shows the %s banner and disables Brief me", (_name, ai, text) => {
    renderPanels(seeded(ai));
    expect(screen.getByTestId("ai-state-banner")).toHaveTextContent(text);
    expect(screen.getByRole("button", { name: "Brief me" })).toBeDisabled();
    expect(screen.getByText(/^Hurricane Simon/)).toBeInTheDocument();
  });

  it("shows an unavailable stream's banner and refreshes the AI's state", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "POST").mockResolvedValue(
      streamAnswer(
        streamOf(briefingEvent({ kind: "unavailable", reason: "auth_failed" })),
      ),
    );
    const getSpy = mockGet(
      new Map<string, unknown>([
        ["/api/ai", aiStatus({ state: "unavailable", reason: "auth_failed" })],
      ]),
    );
    renderPanels(seeded());

    await user.click(screen.getByRole("button", { name: "Brief me" }));

    expect(await screen.findByTestId("ai-state-banner")).toHaveTextContent(
      "AI unavailable: authentication failed — check the credential, then restart serve.",
    );
    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith("/api/ai");
    });
  });
});

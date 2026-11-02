// frontend/src/ai/AiText.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import {
  briefingEvent,
  controlledStream,
  sseFrame,
  streamAnswer,
  TYPED_AI,
  TYPED_BRIEFINGS,
  TYPED_NARRATIONS,
  TYPED_SUMMARIES,
} from "../test/ai.ts";
import { AiSources, AiText } from "./AiText.tsx";
import { BriefingPanel } from "./BriefingPanel.tsx";
import { ChangeSummary } from "./ChangeSummary.tsx";
import { NarrationPanel } from "./NarrationPanel.tsx";

type AiSource = components["schemas"]["AiSourceResponse"];

const HOSTILE =
  "<script>alert(1)</script> Tom &amp; Jerry <b>bold</b> [click here](https://evil.example/x)";

function expectLiteral(container: HTMLElement): void {
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("b")).toBeNull();
  expect(container.querySelector('a[href*="evil.example"]')).toBeNull();
  expect(screen.queryByRole("link", { name: "click here" })).toBeNull();
}

const SOURCE: AiSource = {
  key: "S1",
  source_id: "nhc-text-products",
  title: "NHC public advisory",
  code: "TCP",
  issuer: "KNHC",
  advisory: "22A",
  issued_at: "2026-10-13T00:00:00Z",
  why: HOSTILE,
  url: "https://www.nhc.noaa.gov/",
};

describe("AI text renders literally", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders text as typed in a pre-line paragraph", () => {
    const { container } = render(<AiText text={`${HOSTILE}\nSecond line`} />);
    const paragraph = container.querySelector("p");
    expect(paragraph).toHaveClass("whitespace-pre-line");
    expect(paragraph?.textContent).toBe(`${HOSTILE}\nSecond line`);
    expectLiteral(container);
  });

  it("links a source only to an https URL the API supplied", () => {
    const { container } = render(
      <AiSources
        sources={[
          SOURCE,
          { ...SOURCE, key: "S2", url: null },
          { ...SOURCE, key: "S3", url: "javascript:alert(1)" },
          { ...SOURCE, key: "S4", url: "http://www.nhc.noaa.gov/" },
        ]}
      />,
    );
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "https://www.nhc.noaa.gov/");
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getAllByText(`— ${HOSTILE}`, { exact: false })).toHaveLength(4);
    expectLiteral(container);
  });

  it("shows a stored briefing, a streamed section, a change summary, and a narration as typed", async () => {
    const user = userEvent.setup();
    const stored = TYPED_BRIEFINGS.locations[0]!.briefing!;
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.ai(), TYPED_AI);
    queryClient.setQueryData(queryKeys.briefings(), {
      ...TYPED_BRIEFINGS,
      locations: [
        {
          location: "Miami-Dade County Hall",
          assessment_id: 3,
          briefing: {
            ...stored,
            situation: HOSTILE,
            actions: [HOSTILE],
            timeline: [{ when: "Tonight", what: HOSTILE, sources: ["S1"] }],
            sources: [SOURCE],
          },
        },
      ],
    });
    const summary = TYPED_SUMMARIES.summaries[0]!;
    const narration = TYPED_NARRATIONS.narrations[0]!;
    const sse = controlledStream();
    vi.spyOn(apiClient, "POST").mockResolvedValue(streamAnswer(sse.stream));

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <BriefingPanel
          location="Miami-Dade County Hall"
          assessmentId={3}
          assessedAt="2026-10-13T01:31:00Z"
        />
        <ChangeSummary summary={{ ...summary, summary: HOSTILE }} />
        <NarrationPanel
          basin="atl"
          horizon="7d0"
          label={TYPED_NARRATIONS.label}
          stored={{
            ...narration,
            summary: HOSTILE,
            caveat: HOSTILE,
            areas: [{ description: HOSTILE, chance_text: "20%" }],
          }}
          ai={TYPED_AI}
        />
      </QueryClientProvider>,
    );

    const briefing = screen.getByRole("region", {
      name: "AI briefing for Miami-Dade County Hall",
    });
    expect(within(briefing).getByText(HOSTILE, { selector: "p" })).toBeInTheDocument();
    expect(within(briefing).getAllByText(HOSTILE, { exact: false })).toHaveLength(4);
    expect(
      within(screen.getByRole("region", { name: /AI summary of assessment 3/ })).getByText(
        HOSTILE,
      ),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("region", {
          name: "AI interpretation of the official graphic: Atlantic seven-day",
        }),
      ).getAllByText(HOSTILE, { exact: false }),
    ).toHaveLength(3);
    expectLiteral(container);

    await user.click(within(briefing).getByRole("button", { name: "Brief me" }));
    act(() => {
      sse.push(sseFrame(briefingEvent({ kind: "started", model: "claude-sonnet-5-5" })));
      sse.push(
        sseFrame(briefingEvent({ kind: "section", section: "situation", text: HOSTILE })),
      );
    });
    expect(await within(briefing).findByText(HOSTILE)).toBeInTheDocument();
    expectLiteral(container);
    act(() => {
      sse.close();
    });
    expect(
      await within(briefing).findByText(
        "The briefing stream ended before it finished.",
      ),
    ).toBeInTheDocument();
  });
});

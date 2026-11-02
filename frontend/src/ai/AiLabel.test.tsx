// frontend/src/ai/AiLabel.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AI_LABEL_NOTE, AiLabel } from "./AiLabel.tsx";
import { modelDisplayName } from "./format.ts";

describe("AiLabel", () => {
  it("names the model, the time in the browser's zone and in UTC, and that the level comes from official products", () => {
    render(
      <AiLabel
        kind="AI briefing"
        model="claude-sonnet-5-5"
        at="2026-10-13T01:33:00Z"
        context="for the 2026-10-13 01:30 UTC assessment"
        timeZone="America/New_York"
      />,
    );

    const label = screen.getByTestId("ai-label");
    expect(label).toHaveTextContent("AI briefing");
    expect(label).toHaveTextContent("Claude Sonnet 5.5");
    expect(label).toHaveTextContent(
      "written 2026-10-13 01:33 UTC (2026-10-12 21:33 EDT)",
    );
    expect(label).toHaveTextContent("for the 2026-10-13 01:30 UTC assessment");
    expect(label).toHaveTextContent(
      "AI-generated · may be wrong · the level above comes from official products",
    );
    expect(AI_LABEL_NOTE).toBe(
      "AI-generated · may be wrong · the level above comes from official products",
    );
    expect(label.querySelector("time")).toHaveAttribute(
      "datetime",
      "2026-10-13T01:33:00Z",
    );
  });

  it("shows UTC alone when the browser's zone is UTC, and takes another note", () => {
    render(
      <AiLabel
        kind="AI interpretation of the official graphic"
        model="claude-haiku-5-5"
        modelName="Claude Haiku 5.5"
        at="2026-10-13T01:33:00Z"
        note="AI-generated · may be wrong · the official graphic above governs"
        timeZone="UTC"
      />,
    );
    const label = screen.getByTestId("ai-label");
    expect(label).toHaveTextContent("written 2026-10-13 01:33 UTC");
    expect(label).not.toHaveTextContent("(");
    expect(label).toHaveTextContent("the official graphic above governs");
  });
});

describe("modelDisplayName", () => {
  it("reads a model id as its display name and prefers the API's name", () => {
    expect(modelDisplayName("claude-sonnet-5-5")).toBe("Claude Sonnet 5.5");
    expect(modelDisplayName("claude-opus-5")).toBe("Claude Opus 5");
    expect(modelDisplayName("claude-haiku-5-5", "Claude Haiku 5.5")).toBe(
      "Claude Haiku 5.5",
    );
    expect(modelDisplayName("claude-sonnet-5-5", "claude-sonnet-5-5")).toBe(
      "Claude Sonnet 5.5",
    );
    expect(modelDisplayName("claude-sonnet-5-5-20261001")).toBe(
      "claude-sonnet-5-5-20261001",
    );
    expect(modelDisplayName("other-model")).toBe("other-model");
  });
});

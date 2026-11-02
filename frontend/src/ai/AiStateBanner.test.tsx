// frontend/src/ai/AiStateBanner.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AiStateBanner, aiStateMessage } from "./AiStateBanner.tsx";
import { stateForReason } from "./reasons.ts";

describe("AiStateBanner", () => {
  it("says nothing when AI is ready", () => {
    const { container } = render(
      <AiStateBanner state="ready" reason={null} capMicroUsd={1_000_000} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the off, paused, capped, and unavailable texts", () => {
    expect(aiStateMessage("off", "no_credential")).toBe(
      "AI is off: no Anthropic credential. Set ANTHROPIC_API_KEY or run ant auth login, then restart serve.",
    );
    expect(aiStateMessage("off", "disabled")).toBe(
      "AI is off: [ai] enabled is false in weatherbot.toml.",
    );
    expect(aiStateMessage("paused", "paused")).toBe(
      "AI paused by you — resume it in Settings.",
    );
    expect(aiStateMessage("capped", "capped", 1_000_000)).toBe(
      "AI paused: today's $1.00 cap is reached. It resets at midnight; you can allow more in Settings.",
    );
    expect(aiStateMessage("capped", "capped", 2_500_000)).toBe(
      "AI paused: today's $2.50 cap is reached. It resets at midnight; you can allow more in Settings.",
    );
    expect(aiStateMessage("unavailable", "auth_failed")).toBe(
      "AI unavailable: authentication failed — check the credential, then restart serve.",
    );
    expect(aiStateMessage("unavailable", "overloaded")).toBe(
      "AI unavailable: Anthropic is overloaded or temporarily unavailable.",
    );
    expect(aiStateMessage("unavailable", "busy")).toBe(
      "AI busy: four AI requests are running already. Try again in a moment.",
    );

    render(<AiStateBanner state="paused" reason="paused" />);
    expect(screen.getByTestId("ai-state-banner")).toHaveTextContent(
      "AI paused by you — resume it in Settings.",
    );
  });

  it("maps a refusal's reason to the state whose banner explains it", () => {
    expect(stateForReason("no_credential")).toBe("off");
    expect(stateForReason("disabled")).toBe("off");
    expect(stateForReason("paused")).toBe("paused");
    expect(stateForReason("capped")).toBe("capped");
    expect(stateForReason("auth_failed")).toBe("unavailable");
    expect(stateForReason("busy")).toBe("unavailable");
  });
});

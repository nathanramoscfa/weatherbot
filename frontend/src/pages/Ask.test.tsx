// frontend/src/pages/Ask.test.tsx
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
  chatEvent,
  controlledStream,
  mockGet,
  refusalAnswer,
  sseFrame,
  streamAnswer,
  streamOf,
  TYPED_AI,
} from "../test/ai.ts";
import assessmentsFixture from "../test/fixtures/assessments.json";
import { Ask, QUESTION_LIMIT } from "./Ask.tsx";
import { asSchema, type JsonFixture } from "./format.ts";

const TYPED_ASSESSMENTS = asSchema<components["schemas"]["AssessmentsResponse"]>(
  assessmentsFixture satisfies JsonFixture<
    components["schemas"]["AssessmentsResponse"]
  >,
);

function seeded(ai = TYPED_AI): QueryClient {
  const queryClient = createAppQueryClient();
  queryClient.setQueryData(queryKeys.ai(), ai);
  queryClient.setQueryData(queryKeys.assessments(), TYPED_ASSESSMENTS);
  return queryClient;
}

function renderAsk(queryClient: QueryClient = seeded()) {
  mockGet(new Map<string, unknown>([["/api/ai", TYPED_AI]]));
  return render(
    <QueryClientProvider client={queryClient}>
      <Ask />
    </QueryClientProvider>,
  );
}

describe("Ask", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the engine's level badge for every location, a location picker, and a bounded question box", async () => {
    const user = userEvent.setup();
    renderAsk();

    expect(screen.getByRole("heading", { name: "Ask" })).toBeInTheDocument();
    const levels = screen.getByRole("list", { name: "Engine levels" });
    expect(within(levels).getByText("Miami-Dade County Hall")).toBeInTheDocument();
    expect(within(levels).getByText("Parliament Square")).toBeInTheDocument();
    expect(within(levels).getAllByText("Level 1")).toHaveLength(2);

    const picker = screen.getByLabelText("About");
    expect(
      within(picker)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Every location", "Miami-Dade County Hall", "Parliament Square"]);

    const box = screen.getByLabelText("Your question");
    expect(box).toHaveAttribute("maxLength", String(QUESTION_LIMIT));
    expect(screen.getByText("0 / 2,000")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    await user.click(box);
    await user.paste("x".repeat(QUESTION_LIMIT + 5));
    expect(screen.getByText("2,000 / 2,000")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });

  it("streams an answer sentence by sentence with a chip per lookup, then continues the conversation", async () => {
    const user = userEvent.setup();
    const sse = controlledStream();
    const postSpy = vi
      .spyOn(apiClient, "POST")
      .mockResolvedValueOnce(streamAnswer(sse.stream))
      .mockResolvedValueOnce(
        streamAnswer(
          streamOf(
            chatEvent({ kind: "started", conversation_id: "c-1", model: "claude-sonnet-5-5" }),
            chatEvent({ kind: "text", text: "It is quiet." }),
            chatEvent({ kind: "done", call_ids: [3] }),
          ),
        ),
      );
    renderAsk();

    await user.selectOptions(screen.getByLabelText("About"), "Miami-Dade County Hall");
    await user.type(screen.getByLabelText("Your question"), "Which storms are active?");
    expect(screen.getByText("24 / 2,000")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(postSpy).toHaveBeenLastCalledWith(
      "/api/ai/chat",
      expect.objectContaining({
        body: {
          question: "Which storms are active?",
          conversation_id: null,
          location: "Miami-Dade County Hall",
        },
        parseAs: "stream",
      }),
    );
    expect(screen.getByLabelText("Your question")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();

    act(() => {
      sse.push(
        sseFrame(
          chatEvent({
            kind: "started",
            conversation_id: "c-1",
            model: "claude-sonnet-5-5",
            model_name: "Claude Sonnet 5.5",
          }),
        ),
      );
      sse.push(sseFrame(chatEvent({ kind: "tool", tool: "get_storms" })));
    });
    const transcript = await screen.findByRole("list", { name: "Transcript" });
    expect(await within(transcript).findByText("Reading storms")).toBeInTheDocument();
    expect(within(transcript).getByText("Answering…")).toBeInTheDocument();
    expect(
      within(transcript).getByText("You asked about Miami-Dade County Hall"),
    ).toBeInTheDocument();

    act(() => {
      sse.push(sseFrame(chatEvent({ kind: "text", text: "Simon is in the eastern Pacific." })));
    });
    const answer = await within(transcript).findByTestId("chat-answer");
    expect(answer).toHaveTextContent(/^Simon is in the eastern Pacific\.$/);

    act(() => {
      sse.push(sseFrame(chatEvent({ kind: "text", text: "No storm threatens the location." })));
      sse.push(sseFrame(chatEvent({ kind: "done", call_ids: [1, 2] })));
      sse.close();
    });
    await waitFor(() => {
      expect(answer).toHaveTextContent(
        "Simon is in the eastern Pacific. No storm threatens the location.",
      );
    });
    expect(await within(transcript).findByTestId("ai-label")).toHaveTextContent(
      "AI answer · Claude Sonnet 5.5",
    );
    expect(within(transcript).queryByText("Answering…")).toBeNull();

    await user.type(screen.getByLabelText("Your question"), "And tomorrow?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(postSpy).toHaveBeenLastCalledWith(
      "/api/ai/chat",
      expect.objectContaining({
        body: { question: "And tomorrow?", conversation_id: "c-1", location: "Miami-Dade County Hall" },
      }),
    );
    expect(await screen.findByText("It is quiet.")).toBeInTheDocument();
  });

  it("closes the conversation when an answer is withheld, and New conversation starts afresh", async () => {
    const user = userEvent.setup();
    const postSpy = vi
      .spyOn(apiClient, "POST")
      .mockResolvedValueOnce(
        streamAnswer(
          streamOf(
            chatEvent({ kind: "started", conversation_id: "c-2", model: "claude-sonnet-5-5" }),
            chatEvent({ kind: "text", text: "The first sentence passed." }),
            chatEvent({
              kind: "withheld",
              reason: "level",
              detail: "a sentence stated a level other than the engine's",
              call_ids: [4],
            }),
          ),
        ),
      )
      .mockResolvedValueOnce(refusalAnswer(429, "busy", "too many AI requests are running"));
    renderAsk();

    await user.type(screen.getByLabelText("Your question"), "What is my level?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(
      await screen.findByText(
        /^Withheld: a sentence stated a level other than the engine's\. The rest of the answer was held back/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("The first sentence passed.")).toBeInTheDocument();
    expect(
      screen.getByText("This conversation is closed. Start a new conversation to ask again."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Your question")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "New conversation" }));
    expect(screen.queryByRole("list", { name: "Transcript" })).toBeNull();
    expect(screen.queryByText(/This conversation is closed/)).toBeNull();

    await user.type(screen.getByLabelText("Your question"), "Again?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(postSpy).toHaveBeenLastCalledWith(
      "/api/ai/chat",
      expect.objectContaining({
        body: { question: "Again?", conversation_id: null, location: null },
      }),
    );
    expect(await screen.findByTestId("ai-state-banner")).toHaveTextContent(
      "AI busy: four AI requests are running already.",
    );
  });

  it("closes the conversation when the answer is unavailable", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "POST").mockResolvedValue(
      streamAnswer(
        streamOf(
          chatEvent({
            kind: "unavailable",
            reason: "conversation_full",
            detail: "the conversation reached its 20 questions; start a new one",
          }),
        ),
      ),
    );
    renderAsk();

    await user.type(screen.getByLabelText("Your question"), "One more?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(
      await screen.findByText(
        "Not answered: the conversation reached its 20 questions; start a new one.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/This conversation is closed/)).toBeInTheDocument();
    expect(screen.getByLabelText("Your question")).toBeDisabled();
  });

  it("renders a sentence holding markup or a Markdown link as typed", async () => {
    const user = userEvent.setup();
    const hostile = "<script>alert(1)</script> &amp; [click here](https://evil.example/x)";
    vi.spyOn(apiClient, "POST").mockResolvedValue(
      streamAnswer(
        streamOf(
          chatEvent({ kind: "started", conversation_id: "c-3", model: "claude-sonnet-5-5" }),
          chatEvent({ kind: "text", text: hostile }),
          chatEvent({ kind: "done" }),
        ),
      ),
    );
    const { container } = renderAsk();

    await user.type(screen.getByLabelText("Your question"), "Test?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(hostile)).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.queryByRole("link", { name: "click here" })).toBeNull();
  });

  it("shows the state banner and keeps Ask disabled when AI is not ready", async () => {
    const user = userEvent.setup();
    renderAsk(seeded(aiStatus({ state: "capped", reason: "capped" })));

    expect(screen.getByTestId("ai-state-banner")).toHaveTextContent(
      "AI paused: today's $1.00 cap is reached.",
    );
    await user.type(screen.getByLabelText("Your question"), "Anything?");
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
  });
});

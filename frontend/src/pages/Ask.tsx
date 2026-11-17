// frontend/src/pages/Ask.tsx
import { useQuery } from "@tanstack/react-query";
import { MessagesSquare, RotateCcw, Send, Sparkles, Wrench } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";
import { AiLabel } from "../ai/AiLabel.tsx";
import { AiStateBanner } from "../ai/AiStateBanner.tsx";
import { AiText } from "../ai/AiText.tsx";
import { WritingIndicator } from "../ai/BriefingPanel.tsx";
import { formatCount, toolChipText } from "../ai/format.ts";
import { isAiUnavailableReason, stateForReason } from "../ai/reasons.ts";
import { useAiStatus } from "../ai/useAiStatus.ts";
import { type ChatTurn, useChat } from "../ai/useChat.ts";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { ThreatLevelBadge } from "../app/ThreatLevelBadge.tsx";
import { Card } from "../ui/Card.tsx";
import { Chip } from "../ui/Chip.tsx";
import { PageHeader } from "../ui/PageHeader.tsx";
import { formatBothTimes, formatRouteError } from "./format.ts";

export type AssessmentsResponse =
  components["schemas"]["AssessmentsResponse"];
export type LocationAssessmentItem =
  AssessmentsResponse["locations"][number];

export const QUESTION_LIMIT = 2000;

export interface StarterPromptChip {
  readonly id: 1 | 2 | 3 | 4;
  readonly testId:
    | "ask-chip-1"
    | "ask-chip-2"
    | "ask-chip-3"
    | "ask-chip-4";
  readonly question: string;
}

export function buildStarterPrompts(
  target: LocationAssessmentItem | null,
): readonly StarterPromptChip[] {
  const placeName = target?.name ?? "my watched location";
  const levelPhrase = target?.assessment
    ? `Level ${String(target.assessment.level.number)} (${target.assessment.level.label})`
    : "its current threat level";

  return [
    {
      id: 1,
      testId: "ask-chip-1",
      question: `Why is ${placeName} at ${levelPhrase}?`,
    },
    {
      id: 2,
      testId: "ask-chip-2",
      question: `What should I do at ${levelPhrase} for ${placeName}?`,
    },
    {
      id: 3,
      testId: "ask-chip-3",
      question: `When could tropical-storm-force winds arrive at ${placeName}?`,
    },
    {
      id: 4,
      testId: "ask-chip-4",
      question: `What does the forecast cone mean for ${placeName}?`,
    },
  ];
}

async function fetchAssessments(): Promise<AssessmentsResponse> {
  const { data, response } = await apiClient.GET("/api/assessments");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/assessments", response.status);
  }
  return data;
}

function TurnOutcome({
  turn,
  capMicroUsd,
}: {
  readonly turn: ChatTurn;
  readonly capMicroUsd: number | undefined;
}) {
  switch (turn.status) {
    case "streaming":
      return <WritingIndicator label="Answering…" />;
    case "done":
      return turn.model ? (
        <AiLabel
          kind="AI answer"
          model={turn.model}
          modelName={turn.modelName}
          at={turn.finishedAt}
        />
      ) : null;
    case "withheld":
      return (
        <p className="rounded-md border border-slate-300 bg-white px-3 py-2 font-medium text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
          Withheld: {turn.detail ?? turn.reason ?? "a validator refused it"}. The
          rest of the answer was held back, and this conversation is closed.
        </p>
      );
    case "unavailable":
    case "refused":
      if (isAiUnavailableReason(turn.reason)) {
        return (
          <AiStateBanner
            state={stateForReason(turn.reason)}
            reason={turn.reason}
            capMicroUsd={capMicroUsd}
          />
        );
      }
      return (
        <p className="text-slate-700 dark:text-slate-300">
          Not answered: {turn.detail ?? turn.reason ?? "unavailable"}.
        </p>
      );
    case "failed":
      return (
        <p className="text-slate-700 dark:text-slate-300">
          {turn.httpStatus === null
            ? "The answer stream ended before it finished."
            : formatRouteError("/api/ai/chat", turn.httpStatus)}
        </p>
      );
  }
}

export function Ask() {
  const assessmentsQuery = useQuery({
    queryKey: queryKeys.assessments(),
    queryFn: fetchAssessments,
  });
  const status = useAiStatus();
  const chat = useChat();
  const [question, setQuestion] = useState("");
  const [location, setLocation] = useState("");
  const questionInputRef = useRef<HTMLTextAreaElement | null>(null);

  const ai = status.data;
  const ready = ai?.state === "ready";
  const locations = assessmentsQuery.data?.locations ?? [];
  const chosenLocationItem =
    (location !== ""
      ? locations.find((item) => item.name === location)
      : locations[0]) ??
    locations[0] ??
    null;
  const starterPrompts = buildStarterPrompts(chosenLocationItem);

  const chipsDisabled = !ready || chat.busy || chat.closed !== null;
  const trimmed = question.trim();
  const canAsk =
    ready &&
    !chat.busy &&
    chat.closed === null &&
    trimmed.length > 0 &&
    question.length <= QUESTION_LIMIT;

  const handleSelectChip = (promptText: string) => {
    if (chipsDisabled) {
      return;
    }
    setQuestion(promptText);
    questionInputRef.current?.focus();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canAsk) {
      return;
    }
    if (chat.ask(trimmed, location === "" ? null : location)) {
      setQuestion("");
    }
  };

  return (
    <div className="space-y-5">
      <Card as="section" aria-labelledby="ask-heading">
        <PageHeader
          title="Ask"
          titleId="ask-heading"
          summary={
            <>
              Ask Claude about the stored assessments, alerts, storms, and
              outlook. The levels below come from official NHC and NWS products;
              the answers only explain them.
            </>
          }
        />

        {assessmentsQuery.isError ? (
          <p role="alert" className="mt-3 text-sm text-red-800 dark:text-red-300">
            {formatRouteError(
              "/api/assessments",
              assessmentsQuery.error instanceof ApiRequestError
                ? assessmentsQuery.error.status
                : undefined,
            )}
          </p>
        ) : null}

        <ul
          aria-label="Engine levels"
          className="mt-3 flex flex-col gap-2 text-sm sm:flex-row sm:flex-wrap"
        >
          {locations.map((item) => (
            <li
              key={item.name}
              className="flex flex-wrap items-center gap-2 rounded-md border border-slate-200 bg-slate-50/70 px-2.5 py-1.5 dark:border-slate-800 dark:bg-slate-800/40"
            >
              <span className="font-semibold text-slate-900 dark:text-slate-100">
                {item.name}
              </span>
              {item.assessment ? (
                <>
                  <ThreatLevelBadge
                    level={item.assessment.level.number}
                    label={item.assessment.level.label}
                    atLeast={!item.assessment.complete}
                    size="sm"
                  />
                  <span className="text-slate-600 dark:text-slate-400">
                    {formatBothTimes(item.assessment.as_of, item.time_zone)}
                  </span>
                </>
              ) : (
                <span className="text-slate-600 dark:text-slate-400">
                  No assessment stored yet
                </span>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <section
        aria-labelledby="chat-heading"
        className="space-y-4 rounded-card border border-line bg-surface-card p-4 text-sm shadow-card sm:p-5"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2
            id="chat-heading"
            className="inline-flex items-center gap-2 text-base font-bold text-ink"
          >
            <MessagesSquare
              className="h-5 w-5 shrink-0 text-brand"
              aria-hidden="true"
            />
            Conversation
          </h2>
          <button
            type="button"
            onClick={chat.reset}
            className="inline-flex min-h-6 items-center gap-1.5 rounded-control border border-line-strong bg-surface-card px-2.5 py-1.5 text-sm font-semibold text-ink hover:bg-surface-inset focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            New conversation
          </button>
        </div>

        {ai && ai.state !== "ready" ? (
          <AiStateBanner
            state={ai.state}
            reason={ai.reason}
            capMicroUsd={ai.today.cap_micro_usd}
          />
        ) : null}

        {chat.turns.length === 0 ? (
          <p className="text-ink-muted">
            No questions yet. Choose a starter prompt below or type your own
            question, then press <strong className="text-ink">Ask</strong>.
          </p>
        ) : (
          <ol aria-label="Transcript" aria-live="polite" className="space-y-4">
            {chat.turns.map((turn) => (
              <li
                key={turn.id}
                className="space-y-2.5 rounded-card border border-line bg-surface-page p-3.5"
              >
                <div className="ml-auto max-w-measure rounded-card border border-line-strong bg-surface-inset px-3.5 py-2.5 text-ink">
                  <p className="font-semibold text-ink">
                    You asked
                    {turn.location ? ` about ${turn.location}` : ""}
                  </p>
                  <p className="mt-1 whitespace-pre-line text-ink">
                    {turn.question}
                  </p>
                </div>

                <div className="max-w-measure space-y-2">
                  {turn.sentences.length > 0 ? (
                    <div
                      data-testid="chat-answer"
                      className="rounded-card border border-line bg-surface-card px-3.5 py-2.5 text-ink shadow-card"
                    >
                      <AiText text={turn.sentences.join(" ")} />
                    </div>
                  ) : null}

                  {turn.tools.length > 0 ? (
                    <ul aria-label="Lookups" className="flex flex-wrap gap-1.5">
                      {turn.tools.map((tool, idx) => (
                        <li key={`${tool}-${String(idx)}`}>
                          <Chip
                            tone="ai"
                            icon={
                              <Wrench
                                className="h-3.5 w-3.5"
                                aria-hidden="true"
                              />
                            }
                          >
                            {toolChipText(tool)}
                          </Chip>
                        </li>
                      ))}
                    </ul>
                  ) : null}

                  <TurnOutcome
                    turn={turn}
                    capMicroUsd={ai?.today.cap_micro_usd}
                  />
                </div>
              </li>
            ))}
          </ol>
        )}

        {chat.closed !== null ? (
          <p
            role="status"
            className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-950 dark:border-amber-700/80 dark:bg-amber-950/60 dark:text-amber-100"
          >
            This conversation is closed. Start a new conversation to ask again.
          </p>
        ) : null}

        <form onSubmit={handleSubmit} className="space-y-3 border-t border-line pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <label
              htmlFor="ask-location"
              className="font-medium text-ink"
            >
              About
            </label>
            <select
              id="ask-location"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="rounded-control border border-line-strong bg-surface-card px-2.5 py-1.5 text-sm text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              <option value="">Every location</option>
              {locations.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <span className="inline-flex items-center gap-1.5 text-caption font-semibold text-ink-subtle">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              Starter prompts (fills your question without sending)
            </span>
            <div
              role="group"
              aria-label="Starter prompts"
              className="flex flex-wrap gap-2"
            >
              {starterPrompts.map((chip) => (
                <button
                  key={chip.id}
                  type="button"
                  data-testid={chip.testId}
                  disabled={chipsDisabled}
                  onClick={() => handleSelectChip(chip.question)}
                  className="inline-flex min-h-6 items-center rounded-pill border border-line-strong bg-surface-inset px-3 py-1.5 text-left text-sm font-medium text-ink transition-colors hover:bg-surface-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {chip.question}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label
              htmlFor="ask-question"
              className="block font-medium text-ink"
            >
              Your question
            </label>
            <textarea
              ref={questionInputRef}
              id="ask-question"
              value={question}
              maxLength={QUESTION_LIMIT}
              rows={3}
              disabled={chat.closed !== null}
              onChange={(e) => setQuestion(e.target.value)}
              aria-describedby="ask-question-count"
              className="mt-1 w-full rounded-control border border-line-strong bg-surface-card px-2.5 py-1.5 text-sm text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-60"
            />
            <span
              id="ask-question-count"
              className="block text-right text-caption tabular-nums text-ink-subtle"
            >
              {formatCount(question.length)} / {formatCount(QUESTION_LIMIT)}
            </span>
          </div>
          <button
            type="submit"
            disabled={!canAsk}
            className="inline-flex min-h-6 items-center gap-1.5 rounded-control bg-brand px-3.5 py-1.5 text-sm font-semibold text-on-brand hover:bg-brand-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Send className="h-3.5 w-3.5" aria-hidden="true" />
            Ask
          </button>
        </form>
      </section>
    </div>
  );
}

// frontend/src/pages/Ask.tsx
import { useQuery } from "@tanstack/react-query";
import { MessagesSquare, RotateCcw, Send, Wrench } from "lucide-react";
import { type FormEvent, useState } from "react";
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
import { formatBothTimes, formatRouteError } from "./format.ts";

export type AssessmentsResponse =
  components["schemas"]["AssessmentsResponse"];

export const QUESTION_LIMIT = 2000;

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

  const ai = status.data;
  const ready = ai?.state === "ready";
  const locations = assessmentsQuery.data?.locations ?? [];
  const trimmed = question.trim();
  const canAsk =
    ready &&
    !chat.busy &&
    chat.closed === null &&
    trimmed.length > 0 &&
    question.length <= QUESTION_LIMIT;

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
      <section
        aria-labelledby="ask-heading"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
      >
        <h1
          id="ask-heading"
          className="text-lg font-semibold text-slate-900 dark:text-slate-100"
        >
          Ask
        </h1>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          Ask Claude about the stored assessments, alerts, storms, and outlook.
          The levels below come from official NHC and NWS products; the answers
          only explain them.
        </p>

        {assessmentsQuery.isError ? (
          <p role="alert" className="mt-3 text-xs text-red-800 dark:text-red-300">
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
          className="mt-3 flex flex-col gap-2 text-xs sm:flex-row sm:flex-wrap"
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
      </section>

      <section
        aria-labelledby="chat-heading"
        className="space-y-3 rounded-lg border border-violet-200 bg-white p-4 text-xs shadow-xs sm:p-5 dark:border-violet-900/70 dark:bg-slate-900"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2
            id="chat-heading"
            className="inline-flex items-center gap-2 text-base font-bold text-slate-900 dark:text-slate-100"
          >
            <MessagesSquare
              className="h-5 w-5 shrink-0 text-violet-700 dark:text-violet-300"
              aria-hidden="true"
            />
            Conversation
          </h2>
          <button
            type="button"
            onClick={chat.reset}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
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
          <p className="text-slate-600 dark:text-slate-400">
            No questions yet. Try “What does my level mean?” or “Which storms
            are active?”
          </p>
        ) : (
          <ol aria-label="Transcript" aria-live="polite" className="space-y-3">
            {chat.turns.map((turn) => (
              <li
                key={turn.id}
                className="space-y-2 rounded-md border border-slate-200 p-3 dark:border-slate-800"
              >
                <div>
                  <p className="font-semibold text-slate-900 dark:text-slate-100">
                    You asked
                    {turn.location ? ` about ${turn.location}` : ""}
                  </p>
                  <p className="whitespace-pre-line text-slate-800 dark:text-slate-200">
                    {turn.question}
                  </p>
                </div>
                {turn.tools.length > 0 ? (
                  <ul aria-label="Lookups" className="flex flex-wrap gap-1.5">
                    {turn.tools.map((tool, idx) => (
                      <li
                        key={`${tool}-${String(idx)}`}
                        className="inline-flex items-center gap-1 rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[11px] text-violet-900 dark:border-violet-800 dark:bg-violet-950/50 dark:text-violet-200"
                      >
                        <Wrench className="h-3 w-3" aria-hidden="true" />
                        {toolChipText(tool)}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {turn.sentences.length > 0 ? (
                  <div
                    data-testid="chat-answer"
                    className="rounded-md bg-violet-50/60 px-3 py-2 text-slate-800 dark:bg-violet-950/20 dark:text-slate-200"
                  >
                    <AiText text={turn.sentences.join(" ")} />
                  </div>
                ) : null}
                <TurnOutcome turn={turn} capMicroUsd={ai?.today.cap_micro_usd} />
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

        <form onSubmit={handleSubmit} className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <label
              htmlFor="ask-location"
              className="font-medium text-slate-700 dark:text-slate-300"
            >
              About
            </label>
            <select
              id="ask-location"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              <option value="">Every location</option>
              {locations.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="ask-question"
              className="block font-medium text-slate-700 dark:text-slate-300"
            >
              Your question
            </label>
            <textarea
              id="ask-question"
              value={question}
              maxLength={QUESTION_LIMIT}
              rows={3}
              disabled={chat.closed !== null}
              onChange={(e) => setQuestion(e.target.value)}
              aria-describedby="ask-question-count"
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <p
              id="ask-question-count"
              className="text-right text-[11px] text-slate-500 dark:text-slate-400"
            >
              {formatCount(question.length)} / {formatCount(QUESTION_LIMIT)}
            </p>
          </div>
          <button
            type="submit"
            disabled={!canAsk}
            className="inline-flex items-center gap-1.5 rounded-md bg-violet-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-violet-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-violet-500 dark:text-slate-950 dark:hover:bg-violet-400"
          >
            <Send className="h-3.5 w-3.5" aria-hidden="true" />
            Ask
          </button>
        </form>
      </section>
    </div>
  );
}

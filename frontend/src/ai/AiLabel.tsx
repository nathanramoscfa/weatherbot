// frontend/src/ai/AiLabel.tsx
import { Sparkles } from "lucide-react";
import { formatBothTimes } from "../pages/format.ts";
import { browserTimeZone, modelDisplayName } from "./format.ts";

export const AI_LABEL_NOTE =
  "AI-generated · may be wrong · the level above comes from official products";

export interface AiLabelProps {
  readonly kind: string;
  readonly model: string;
  readonly modelName?: string | null;
  readonly at?: string | null;
  readonly context?: string | null;
  readonly note?: string;
  readonly timeZone?: string | undefined;
}

export function AiLabel({
  kind,
  model,
  modelName,
  at,
  context,
  note = AI_LABEL_NOTE,
  timeZone = browserTimeZone(),
}: AiLabelProps) {
  return (
    <div
      data-testid="ai-label"
      className="space-y-0.5 text-[11px] text-violet-900 dark:text-violet-200"
    >
      <p className="flex items-start gap-1.5">
        <Sparkles className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span>
          <span className="font-semibold">{kind}</span>
          {" · "}
          {modelDisplayName(model, modelName)}
          {at ? (
            <>
              {" · "}
              <time dateTime={at}>written {formatBothTimes(at, timeZone)}</time>
            </>
          ) : null}
          {context ? ` ${context}` : ""}
        </span>
      </p>
      <p className="text-violet-800/90 dark:text-violet-300/90">{note}</p>
    </div>
  );
}

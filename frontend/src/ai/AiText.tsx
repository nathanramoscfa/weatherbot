// frontend/src/ai/AiText.tsx
import { ExternalLink } from "lucide-react";
import { formatUtc } from "../pages/format.ts";
import { isPublicHttpsUrl } from "./format.ts";
import type { AiSourceResponse } from "./queries.ts";

export interface AiTextProps {
  readonly text: string;
  readonly className?: string;
}

export function AiText({ text, className = "" }: AiTextProps) {
  return <p className={`whitespace-pre-line ${className}`}>{text}</p>;
}

export interface AiSourcesProps {
  readonly sources: readonly AiSourceResponse[];
}

export function AiSources({ sources }: AiSourcesProps) {
  if (sources.length === 0) {
    return null;
  }
  return (
    <ul className="space-y-1">
      {sources.map((source) => (
        <li key={source.key}>
          <span className="font-mono font-semibold">{source.key}</span>{" "}
          <span>{source.title}</span>
          {source.issued_at ? ` · issued ${formatUtc(source.issued_at)}` : ""}
          {source.why ? (
            <span className="whitespace-pre-line"> — {source.why}</span>
          ) : null}
          {isPublicHttpsUrl(source.url) ? (
            <>
              {" · "}
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 font-medium text-sky-700 underline underline-offset-2 hover:text-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:text-sky-400 dark:hover:text-sky-300"
              >
                official page
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </a>
            </>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

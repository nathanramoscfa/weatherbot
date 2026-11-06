// frontend/e2e/guard.ts
import { readFileSync } from "node:fs";
import { test as base, expect, type Page } from "@playwright/test";

declare global {
  interface Window {
    __wbCspViolations?: string[];
    __wbSmokeMark?: string;
  }
}

const DECIMAL_COORDINATE = /(?<![\d.])\d{1,3}\.\d{3,}(?![\d.])/;

function loadLandmarkCoordinateRenderings(): Set<string> {
  const raw = readFileSync("../scripts/public_landmarks.toml", "utf8");
  const renderings = new Set<string>();
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("lat =") && !trimmed.startsWith("lon =")) {
      continue;
    }
    const eqIndex = trimmed.indexOf("=");
    if (eqIndex === -1) {
      continue;
    }
    const value = trimmed.slice(eqIndex + 1).trim();
    const num = Number(value);
    if (!Number.isFinite(num)) {
      continue;
    }
    renderings.add(value);
    renderings.add(String(num));
    renderings.add(num.toFixed(4));
    renderings.add(value.replace(/^-/, ""));
  }
  return renderings;
}

const LANDMARK_RENDERINGS = loadLandmarkCoordinateRenderings();

export function leaksCoordinate(text: string): boolean {
  for (const rendering of LANDMARK_RENDERINGS) {
    if (text.includes(rendering)) {
      return true;
    }
  }
  return DECIMAL_COORDINATE.test(text);
}

const AI_FRAGMENT_MIN = 16;
const AI_TEXTS = new WeakMap<Page, string[]>();

// Remembers AI text a spec saw on the page; the guard fails the test when any
// sentence of it reached the console.
export function recordAiText(page: Page, text: string): void {
  const fragments = text
    .split(/(?<=[.!?])\s+|\n+/)
    .map((fragment) => fragment.trim())
    .filter((fragment) => fragment.length >= AI_FRAGMENT_MIN);
  AI_TEXTS.set(page, [...(AI_TEXTS.get(page) ?? []), ...fragments]);
}

export function leaksAiText(page: Page, message: string): boolean {
  return (AI_TEXTS.get(page) ?? []).some((fragment) =>
    message.includes(fragment),
  );
}

export const test = base.extend<{ guard: void }>({
  guard: [
    async ({ page, baseURL }, use) => {
      const serverOrigin = new URL(baseURL ?? "http://127.0.0.1:8799").origin;
      const unexpectedOrigins: string[] = [];
      const consoleMessages: string[] = [];
      const pageErrors: string[] = [];

      await page.addInitScript(() => {
        const violations: string[] = [];
        Object.defineProperty(window, "__wbCspViolations", {
          value: violations,
          writable: false,
          configurable: true,
        });
        window.addEventListener("securitypolicyviolation", (event) => {
          violations.push(
            `${event.violatedDirective}: ${event.blockedURI || "inline"}`,
          );
        });
      });

      await page.route("**/*", async (route) => {
        const rawUrl = route.request().url();
        const parsed = new URL(rawUrl);
        if (
          parsed.origin === "https://tile.openstreetmap.org" ||
          parsed.origin === "https://nowcoast.noaa.gov"
        ) {
          await route.fulfill({
            status: 200,
            contentType: "image/png",
            headers: { "Cache-Control": "no-store" },
            path: "./e2e/blank-tile.png",
          });
          return;
        }
        if (
          parsed.origin === serverOrigin ||
          parsed.protocol === "data:" ||
          parsed.protocol === "blob:"
        ) {
          await route.continue();
          return;
        }
        unexpectedOrigins.push(rawUrl);
        await route.abort("blockedbyclient");
      });

      page.on("console", (msg) => {
        consoleMessages.push(msg.text());
      });
      page.on("pageerror", (err) => {
        pageErrors.push(err.message);
      });

      await use();

      const cspViolations = await page.evaluate(
        () => window.__wbCspViolations ?? [],
      );
      const leakingMessages = consoleMessages.filter((msg) =>
        leaksCoordinate(msg),
      );
      const aiMessages = consoleMessages.filter((msg) =>
        leaksAiText(page, msg),
      );

      expect(
        unexpectedOrigins,
        "Requests to origins other than the server or tile.openstreetmap.org",
      ).toEqual([]);
      expect(
        cspViolations,
        "Content-Security-Policy securitypolicyviolation events",
      ).toEqual([]);
      expect(pageErrors, "Uncaught pageerror events").toEqual([]);
      expect(
        leakingMessages,
        "Console messages holding landmark coordinate renderings",
      ).toEqual([]);
      expect(aiMessages, "Console messages holding AI text").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

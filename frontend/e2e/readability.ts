// frontend/e2e/readability.ts
import type { Page } from "@playwright/test";

// The readability gate of Phase 8 Decision 6 (docs/DESIGN.md, "The
// readability gate"): four computed checks over every visible element that has
// its own text inside <header>, <main>, and <footer>, skipping SVG chart
// internals, visually hidden text, closed <details> content, and everything
// inside the Leaflet container.
//
//   size      primary prose (p, li, dd, dt, td, th, label, summary, blockquote,
//             figcaption, legend, a, button, role note/alert/status) computes
//             at least 14 px; any other text at least 13 px.
//   contrast  the WCAG 2.2 ratio between the text's colour and the first opaque
//             background up its ancestors, alpha-composited, is at least 4.5:1,
//             or 3:1 for large text (24 px, or 18.66 px at weight 700); a
//             background image or gradient behind text is a finding of its own
//             ("background"), because its contrast cannot be computed.
//   measure   a p, li, or dd holding 160 characters or more is at most 42 em
//             wide.
//   overflow  the page never scrolls sideways, and no audited element's box
//             extends past the viewport's right edge unless an ancestor
//             scrolls it on purpose (overflow-x auto or scroll).
//
// Everything the page runs lives inside readabilityKit(), so the kit's source
// can be evaluated in the page as it stands (no package, no injected script
// tag, nothing the CSP would refuse) and its pure functions unit-tested in
// Node (readability.unit.spec.ts).

export type ReadabilityCheck =
  | "size"
  | "contrast"
  | "background"
  | "measure"
  | "overflow";

export interface ReadabilityFinding {
  readonly check: ReadabilityCheck;
  readonly element: string;
  readonly value: string;
  readonly sample: string;
}

export interface Rgba {
  readonly r: number;
  readonly g: number;
  readonly b: number;
  readonly a: number;
}

export function readabilityKit() {
  const MIN_PROSE_PX = 14;
  const MIN_TEXT_PX = 13;
  const MIN_RATIO = 4.5;
  const MIN_RATIO_LARGE = 3;
  const LARGE_PX = 24;
  const LARGE_BOLD_PX = 18.66;
  const MAX_MEASURE_EM = 42;
  const MEASURE_MIN_CHARS = 160;
  const SAMPLE_CHARS = 60;

  const PROSE_TAGS = new Set([
    "p",
    "li",
    "dd",
    "dt",
    "td",
    "th",
    "label",
    "summary",
    "blockquote",
    "figcaption",
    "legend",
    "a",
    "button",
  ]);
  const PROSE_ROLES = new Set(["note", "alert", "status"]);
  const MEASURE_TAGS = new Set(["p", "li", "dd"]);
  const SKIPPED_TAGS = new Set([
    "script",
    "style",
    "noscript",
    "template",
    "title",
    "option",
    "optgroup",
  ]);

  function channelToLinear(value: number): number {
    const c = value / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }

  // WCAG 2.2 relative luminance of an sRGB colour (channels 0 to 255).
  function relativeLuminance(color: Rgba): number {
    return (
      0.2126 * channelToLinear(color.r) +
      0.7152 * channelToLinear(color.g) +
      0.0722 * channelToLinear(color.b)
    );
  }

  // WCAG 2.2 contrast ratio of two opaque colours, from 1 to 21.
  function contrastRatio(first: Rgba, second: Rgba): number {
    const a = relativeLuminance(first);
    const b = relativeLuminance(second);
    const lighter = Math.max(a, b);
    const darker = Math.min(a, b);
    return (lighter + 0.05) / (darker + 0.05);
  }

  // Source-over compositing of `top` onto `bottom`.
  function composite(top: Rgba, bottom: Rgba): Rgba {
    const alpha = top.a + bottom.a * (1 - top.a);
    if (alpha <= 0) {
      return { r: 0, g: 0, b: 0, a: 0 };
    }
    const mix = (t: number, b: number) =>
      (t * top.a + b * bottom.a * (1 - top.a)) / alpha;
    return {
      r: mix(top.r, bottom.r),
      g: mix(top.g, bottom.g),
      b: mix(top.b, bottom.b),
      a: alpha,
    };
  }

  function isLargeText(fontSizePx: number, fontWeight: number): boolean {
    return (
      fontSizePx >= LARGE_PX || (fontSizePx >= LARGE_BOLD_PX && fontWeight >= 700)
    );
  }

  function minimumRatio(fontSizePx: number, fontWeight: number): number {
    return isLargeText(fontSizePx, fontWeight) ? MIN_RATIO_LARGE : MIN_RATIO;
  }

  function formatColor(color: Rgba): string {
    const hex = [color.r, color.g, color.b]
      .map((c) => Math.round(c).toString(16).padStart(2, "0"))
      .join("");
    return `#${hex}`;
  }

  function audit(): ReadabilityFinding[] {
    const findings: ReadabilityFinding[] = [];
    const doc = document.documentElement;
    const viewportWidth = doc.clientWidth;

    // Every CSS colour the browser computes (rgb, oklch, oklab, color-mix)
    // is normalised to sRGB by painting it on a 1x1 canvas.
    const canvas = document.createElement("canvas");
    canvas.width = 1;
    canvas.height = 1;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    const colorCache = new Map<string, Rgba>();
    function parseColor(css: string): Rgba {
      const cached = colorCache.get(css);
      if (cached) {
        return cached;
      }
      let parsed: Rgba = { r: 0, g: 0, b: 0, a: 0 };
      if (context) {
        context.clearRect(0, 0, 1, 1);
        context.fillStyle = "rgba(0, 0, 0, 0)";
        context.fillStyle = css;
        context.fillRect(0, 0, 1, 1);
        const [r = 0, g = 0, b = 0, a = 0] = context.getImageData(0, 0, 1, 1).data;
        parsed = { r, g, b, a: a / 255 };
      }
      colorCache.set(css, parsed);
      return parsed;
    }

    const styleCache = new Map<Element, CSSStyleDeclaration>();
    function styleOf(el: Element): CSSStyleDeclaration {
      let style = styleCache.get(el);
      if (!style) {
        style = getComputedStyle(el);
        styleCache.set(el, style);
      }
      return style;
    }

    function ownText(el: Element): string {
      let text = "";
      for (const node of Array.from(el.childNodes)) {
        if (node.nodeType === Node.TEXT_NODE) {
          text += node.textContent ?? "";
        }
      }
      return text.replace(/\s+/g, " ").trim();
    }

    function isVisuallyHiddenBox(el: Element): boolean {
      const style = styleOf(el);
      if (style.clipPath === "inset(50%)") {
        return true;
      }
      if (style.clip === "rect(0px, 0px, 0px, 0px)") {
        return true;
      }
      if (style.position === "absolute" && style.overflow === "hidden") {
        const rect = el.getBoundingClientRect();
        return rect.width <= 1 && rect.height <= 1;
      }
      return false;
    }

    function insideClosedDetails(el: Element): boolean {
      let details = el.parentElement?.closest("details") ?? null;
      let current: Element = el;
      while (details) {
        if (!details.open) {
          const summary = Array.from(details.children).find(
            (child) => child.tagName.toLowerCase() === "summary",
          );
          if (!summary || !summary.contains(current)) {
            return true;
          }
        }
        current = details;
        details = details.parentElement?.closest("details") ?? null;
      }
      return false;
    }

    function isSkipped(el: Element): boolean {
      if (SKIPPED_TAGS.has(el.tagName.toLowerCase())) {
        return true;
      }
      if (el.closest("svg") || el.closest(".leaflet-container")) {
        return true;
      }
      if (insideClosedDetails(el)) {
        return true;
      }
      if (
        !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) ||
        el.getClientRects().length === 0
      ) {
        return true;
      }
      for (
        let node: Element | null = el;
        node && node !== document.body;
        node = node.parentElement
      ) {
        if (isVisuallyHiddenBox(node)) {
          return true;
        }
      }
      return false;
    }

    function describe(el: Element): string {
      const parts: string[] = [];
      let node: Element | null = el;
      while (node && node !== document.body && parts.length < 4) {
        const tag = node.tagName.toLowerCase();
        const testId = node.getAttribute("data-testid");
        const label = node.getAttribute("aria-label");
        if (node.id) {
          parts.unshift(`${tag}#${node.id}`);
          break;
        }
        if (testId) {
          parts.unshift(`${tag}[data-testid="${testId}"]`);
          break;
        }
        if (label && (tag === "article" || tag === "section" || tag === "nav")) {
          parts.unshift(`${tag}[aria-label="${label}"]`);
          break;
        }
        const parent: Element | null = node.parentElement;
        if (parent) {
          const siblings = Array.from(parent.children).filter(
            (child) => child.tagName === node?.tagName,
          );
          parts.unshift(
            siblings.length > 1
              ? `${tag}:nth-of-type(${String(siblings.indexOf(node) + 1)})`
              : tag,
          );
        } else {
          parts.unshift(tag);
        }
        node = parent;
      }
      return parts.join(" > ");
    }

    function push(
      check: ReadabilityCheck,
      el: Element | null,
      value: string,
      sample: string,
    ) {
      findings.push({
        check,
        element: el ? describe(el) : "html",
        value,
        sample: sample.slice(0, SAMPLE_CHARS),
      });
    }

    // The right edge of an element's own text, which can spill past its box
    // (an unbroken URL or code), or of the box, whichever is further right.
    function rightEdge(el: Element): number {
      let right = el.getBoundingClientRect().right;
      for (const node of Array.from(el.childNodes)) {
        if (node.nodeType === Node.TEXT_NODE && (node.textContent ?? "").trim()) {
          const range = document.createRange();
          range.selectNodeContents(node);
          right = Math.max(right, range.getBoundingClientRect().right);
        }
      }
      return right;
    }

    function scrolledOnPurpose(el: Element): boolean {
      for (
        let node: Element | null = el.parentElement;
        node && node !== document.body;
        node = node.parentElement
      ) {
        const overflowX = styleOf(node).overflowX;
        if (overflowX === "auto" || overflowX === "scroll") {
          return true;
        }
      }
      return false;
    }

    if (doc.scrollWidth > doc.clientWidth) {
      // Name what widens the page: the innermost boxes past the right edge.
      const past = Array.from(document.body.querySelectorAll("*")).filter(
        (el) => rightEdge(el) > viewportWidth + 0.5 && !scrolledOnPurpose(el),
      );
      const innermost = past.filter(
        (el) => !past.some((other) => other !== el && el.contains(other)),
      );
      const culprit = innermost[0] ?? null;
      push(
        "overflow",
        culprit,
        `page scrollWidth ${String(doc.scrollWidth)}px > clientWidth ${String(doc.clientWidth)}px${
          culprit
            ? `; widened by ${String(innermost.length)} box(es), first ending at ${rightEdge(culprit).toFixed(1)}px`
            : ""
        }`,
        culprit ? (culprit.textContent ?? "").replace(/\s+/g, " ").trim() : "",
      );
    }

    const candidates = Array.from(
      document.body.querySelectorAll("*"),
    ).filter((el) => el.closest("header, main, footer") !== null);

    for (const el of candidates) {
      const text = ownText(el);
      if (text.length === 0 || isSkipped(el)) {
        continue;
      }
      const style = styleOf(el);
      const tag = el.tagName.toLowerCase();
      const role = el.getAttribute("role") ?? "";
      const fontSize = Number.parseFloat(style.fontSize);
      const fontWeight = Number.parseFloat(style.fontWeight) || 400;

      // (1) Size.
      const prose = PROSE_TAGS.has(tag) || PROSE_ROLES.has(role);
      const minimumPx = prose ? MIN_PROSE_PX : MIN_TEXT_PX;
      if (fontSize < minimumPx - 0.01) {
        push(
          "size",
          el,
          `${String(fontSize)}px; ${prose ? "primary prose" : "text"} needs ${String(minimumPx)}px`,
          text,
        );
      }

      // (2) Contrast against the first opaque background up the ancestors.
      const layers: Rgba[] = [];
      let imageBehind: Element | null = null;
      for (
        let node: Element | null = el;
        node;
        node = node.parentElement
      ) {
        const nodeStyle = styleOf(node);
        if (nodeStyle.backgroundImage !== "none") {
          imageBehind = node;
          break;
        }
        const background = parseColor(nodeStyle.backgroundColor);
        if (background.a > 0) {
          layers.push(background);
          if (background.a >= 1) {
            break;
          }
        }
      }
      if (imageBehind) {
        push(
          "background",
          el,
          `background image behind text: ${styleOf(imageBehind).backgroundImage.slice(0, 80)}`,
          text,
        );
      } else {
        let backdrop: Rgba = { r: 255, g: 255, b: 255, a: 1 };
        for (const layer of layers.reverse()) {
          backdrop = composite(layer, backdrop);
        }
        const foreground = composite(parseColor(style.color), backdrop);
        const ratio = contrastRatio(foreground, backdrop);
        const needed = minimumRatio(fontSize, fontWeight);
        if (ratio < needed - 0.005) {
          push(
            "contrast",
            el,
            `${ratio.toFixed(2)}:1 (${formatColor(foreground)} on ${formatColor(backdrop)}); needs ${String(needed)}:1`,
            text,
          );
        }
      }

      // (3) Measure.
      if (MEASURE_TAGS.has(tag)) {
        const fullText = (el.textContent ?? "").replace(/\s+/g, " ").trim();
        if (fullText.length >= MEASURE_MIN_CHARS) {
          const rect = el.getBoundingClientRect();
          const inner =
            rect.width -
            Number.parseFloat(style.paddingLeft) -
            Number.parseFloat(style.paddingRight) -
            Number.parseFloat(style.borderLeftWidth) -
            Number.parseFloat(style.borderRightWidth);
          const widthEm = inner / fontSize;
          if (widthEm > MAX_MEASURE_EM + 0.05) {
            push(
              "measure",
              el,
              `${widthEm.toFixed(1)}em wide for ${String(fullText.length)} characters; at most ${String(MAX_MEASURE_EM)}em`,
              fullText,
            );
          }
        }
      }

      // (4) Overflow past the viewport's right edge.
      const right = rightEdge(el);
      if (right > viewportWidth + 0.5) {
        if (!scrolledOnPurpose(el)) {
          push(
            "overflow",
            el,
            `right edge ${right.toFixed(1)}px > viewport ${String(viewportWidth)}px`,
            text,
          );
        }
      }
    }
    return findings;
  }

  return {
    MIN_PROSE_PX,
    MIN_TEXT_PX,
    MAX_MEASURE_EM,
    MEASURE_MIN_CHARS,
    relativeLuminance,
    contrastRatio,
    composite,
    isLargeText,
    minimumRatio,
    audit,
  };
}

// Runs the four checks in the page and returns every finding. The kit's own
// source is evaluated as an expression through the DevTools protocol, as
// Playwright evaluates any function, so it needs nothing from the page.
export async function auditReadability(
  page: Page,
): Promise<ReadabilityFinding[]> {
  const expression = `(${readabilityKit.toString()})().audit()`;
  return page.evaluate<ReadabilityFinding[]>(expression);
}

export function formatFindings(
  findings: readonly (ReadabilityFinding & { readonly render?: string })[],
): string {
  return findings
    .map(
      (finding) =>
        `${finding.render ? `[${finding.render}] ` : ""}${finding.check}: ${finding.element} — ${finding.value}${finding.sample ? ` — "${finding.sample}"` : ""}`,
    )
    .join("\n");
}

<!-- docs/DESIGN.md -->
# Design system

Weatherbot's pages share one design language: a small set of tokens in
`frontend/src/index.css`, the primitives in `frontend/src/ui/`, and the rules
below. Phase 8 Step 2 built it; Steps 3 to 7 rebuild the pages with it, and the
readability gate (`frontend/e2e/readability.spec.ts`) checks every route in CI.
The decisions it records are Phase 8 Decisions 4 to 8 in
`docs/roadmap/phase08-roadmap.md`.

## Tokens

Tailwind 4 reads its scale from CSS variables, so every token lives in one
`@theme` block in `frontend/src/index.css`, and the dark theme redefines the
same names under the `dark` class (set by `frontend/public/theme-init.js` before
first paint and by the theme menu). Colours are sRGB hex values taken from
Tailwind's own palette (the hue is named beside each), so the ratios below are
exact. A component uses a token through its utility: `bg-surface-card`,
`text-ink-subtle`, `border-threat-5-border`, `shadow-card`, `rounded-card`.

### Type scale

| Utility        | Size               | Line height | Use                                          |
| -------------- | ------------------ | ----------- | -------------------------------------------- |
| `text-caption` | 0.8125 rem (13 px) | 1.4         | meta on a `<span>`, `<time>`, or `<small>`   |
| `text-sm`      | 0.9375 rem (15 px) | 1.5         | prose, controls, table cells                 |
| `text-base`    | 1.0625 rem (17 px) | 1.6         | lead prose, card titles                      |
| `text-lg`      | 1.25 rem (20 px)   | 1.4         | section headings (`SectionHeading` h2)       |
| `text-xl`      | 1.5 rem (24 px)    | 1.333       | large figures                                |
| `text-2xl`     | 1.875 rem (30 px)  | 1.2         | page titles (`PageHeader`), stat values      |

The face is the system stack (`ui-sans-serif, system-ui, …`; Segoe UI Variable
on Windows 11). No font is downloaded: a font package fails the licence
allowlist, and a font host would need a CSP entry and an outbound host.

### Surfaces, ink, and brand

| Token            | Light                 | Dark                  | Use                              |
| ---------------- | --------------------- | --------------------- | -------------------------------- |
| `surface-page`   | `#f8fafc` slate-50    | `#020618` slate-950   | the page behind every card       |
| `surface-card`   | `#ffffff`             | `#0f172b` slate-900   | a card (`Card`)                  |
| `surface-raised` | `#ffffff`             | `#1d293d` slate-800   | menus, popovers, toasts          |
| `surface-inset`  | `#f1f5f9` slate-100   | `#020618` slate-950   | a well inside a card, stat tiles |
| `line`           | `#e2e8f0` slate-200   | `#1d293d` slate-800   | card borders and dividers        |
| `line-strong`    | `#cad5e2` slate-300   | `#314158` slate-700   | control borders                  |
| `ink`            | `#0f172b` slate-900   | `#f1f5f9` slate-100   | body text and headings           |
| `ink-muted`      | `#314158` slate-700   | `#cad5e2` slate-300   | secondary prose                  |
| `ink-subtle`     | `#45556c` slate-600   | `#90a1b9` slate-400   | captions and meta                |
| `brand`          | `#0069a8` sky-700     | `#00bcff` sky-400     | links, primary buttons, focus    |
| `brand-hover`    | `#024a70` sky-900     | `#74d4ff` sky-300     | hover on the above               |
| `on-brand`       | `#ffffff`             | `#020618` slate-950   | text on `brand`                  |

Phase 7's primary buttons were white on sky-600, which measures 4.02:1 and
fails AA at 15 px; `brand` replaces it everywhere.

### Threat palette

Each level keeps the hue the operator knows (1 emerald, 2 sky, 3 amber, 4
orange, 5 red) in five roles: `surface` tints a card or chip, `border` outlines
it, `fg` is text on that surface, `accent` is the solid mark, and `on-accent` is
text on the accent. `frontend/src/ui/threat.ts` spells out each level's classes
(`tint`, `solid`, `fg`) so Tailwind's scanner finds every one.

| Level | Role        | Light                | Dark                  |
| ----- | ----------- | -------------------- | --------------------- |
| 1     | `surface`   | `#ecfdf5` emerald-50 | `#002c22` emerald-950 |
| 1     | `border`    | `#5ee9b5` emerald-300 | `#007a55` emerald-700 |
| 1     | `fg`        | `#004f3b` emerald-900 | `#a4f4cf` emerald-200 |
| 1     | `accent`    | `#007a55` emerald-700 | `#00bc7d` emerald-500 |
| 1     | `on-accent` | `#ffffff`            | `#020618` slate-950   |
| 2     | `surface`   | `#f0f9ff` sky-50     | `#052f4a` sky-950     |
| 2     | `border`    | `#74d4ff` sky-300    | `#0069a8` sky-700     |
| 2     | `fg`        | `#024a70` sky-900    | `#b8e6fe` sky-200     |
| 2     | `accent`    | `#0069a8` sky-700    | `#00bcff` sky-400     |
| 2     | `on-accent` | `#ffffff`            | `#020618` slate-950   |
| 3     | `surface`   | `#fffbeb` amber-50   | `#461901` amber-950   |
| 3     | `border`    | `#ffd230` amber-300  | `#bb4d00` amber-700   |
| 3     | `fg`        | `#7b3306` amber-900  | `#fee685` amber-200   |
| 3     | `accent`    | `#ffb900` amber-400  | `#ffb900` amber-400   |
| 3     | `on-accent` | `#020618` slate-950  | `#020618` slate-950   |
| 4     | `surface`   | `#fff7ed` orange-50  | `#441306` orange-950  |
| 4     | `border`    | `#ffb86a` orange-300 | `#ca3500` orange-700  |
| 4     | `fg`        | `#7e2a0c` orange-900 | `#ffd6a7` orange-200  |
| 4     | `accent`    | `#ff6900` orange-500 | `#ff6900` orange-500  |
| 4     | `on-accent` | `#020618` slate-950  | `#020618` slate-950   |
| 5     | `surface`   | `#fef2f2` red-50     | `#460809` red-950     |
| 5     | `border`    | `#ffa2a2` red-300    | `#c10007` red-700     |
| 5     | `fg`        | `#82181a` red-900    | `#ffc9c9` red-200     |
| 5     | `accent`    | `#e7000b` red-600    | `#fb2c36` red-500     |
| 5     | `on-accent` | `#ffffff`            | `#020618` slate-950   |

`ThreatLevelBadge` draws levels 1 and 2 tinted and levels 3 to 5 solid. The
charts keep `LEVEL_SVG_CLASSES` (the 400 to 600 steps), which hold 3:1 against
the card as graphics; an amber or orange accent standing alone as a graphic on a
light card does not, so it always carries its level number or an outline.

### Measured contrast

Every text and surface pair the palette defines, by the WCAG 2.2 formula (the
same functions `frontend/e2e/readability.ts` uses, pinned by
`readability.unit.spec.ts`). AA is 4.5:1 for text under 24 px (18.66 px bold)
and 3:1 above; every pair passes in both themes, the lowest at 4.77:1.

| Text                 | Surface            | Light   | Dark    |
| -------------------- | ------------------ | ------- | ------- |
| `ink`                | `surface-page`     | 17.04:1 | 18.40:1 |
| `ink`                | `surface-card`     | 17.83:1 | 16.28:1 |
| `ink`                | `surface-raised`   | 17.83:1 | 13.34:1 |
| `ink`                | `surface-inset`    | 16.28:1 | 18.40:1 |
| `ink-muted`          | `surface-page`     | 9.90:1  | 13.56:1 |
| `ink-muted`          | `surface-card`     | 10.36:1 | 12.00:1 |
| `ink-muted`          | `surface-raised`   | 10.36:1 | 9.83:1  |
| `ink-muted`          | `surface-inset`    | 9.45:1  | 13.56:1 |
| `ink-subtle`         | `surface-page`     | 7.25:1  | 7.66:1  |
| `ink-subtle`         | `surface-card`     | 7.58:1  | 6.78:1  |
| `ink-subtle`         | `surface-raised`   | 7.58:1  | 5.56:1  |
| `ink-subtle`         | `surface-inset`    | 6.92:1  | 7.66:1  |
| `brand`              | `surface-page`     | 5.60:1  | 9.25:1  |
| `brand`              | `surface-card`     | 5.86:1  | 8.18:1  |
| `brand`              | `surface-raised`   | 5.86:1  | 6.71:1  |
| `brand`              | `surface-inset`    | 5.35:1  | 9.25:1  |
| `on-brand`           | `brand`            | 5.86:1  | 9.25:1  |
| `threat-1-fg`        | `threat-1-surface` | 9.14:1  | 11.87:1 |
| `threat-1-on-accent` | `threat-1-accent`  | 5.36:1  | 8.15:1  |
| `threat-1-fg`        | `surface-card`     | 9.63:1  | 13.94:1 |
| `threat-2-fg`        | `threat-2-surface` | 8.89:1  | 10.44:1 |
| `threat-2-on-accent` | `threat-2-accent`  | 5.86:1  | 9.25:1  |
| `threat-2-fg`        | `surface-card`     | 9.48:1  | 13.41:1 |
| `threat-3-fg`        | `threat-3-surface` | 8.73:1  | 12.05:1 |
| `threat-3-on-accent` | `threat-3-accent`  | 11.70:1 | 11.70:1 |
| `threat-3-fg`        | `surface-card`     | 9.06:1  | 14.33:1 |
| `threat-4-fg`        | `threat-4-surface` | 8.90:1  | 11.50:1 |
| `threat-4-on-accent` | `threat-4-accent`  | 6.98:1  | 6.98:1  |
| `threat-4-fg`        | `surface-card`     | 9.44:1  | 13.10:1 |
| `threat-5-fg`        | `threat-5-surface` | 9.16:1  | 11.12:1 |
| `threat-5-on-accent` | `threat-5-accent`  | 4.77:1  | 5.29:1  |
| `threat-5-fg`        | `surface-card`     | 10.03:1 | 12.27:1 |

### Elevation, radius, and measure

- `shadow-card` is a resting card; `shadow-raised` is a layer above the page
  (menus, popovers, toasts). The dark theme deepens both.
- `rounded-control` (0.375 rem) for buttons and inputs, `rounded-card`
  (0.75 rem) for cards, callouts, and disclosures, `rounded-pill` for chips
  and badges.
- `max-w-measure` (42 em) is the longest line of prose. Every `<p>` takes it in
  the base layer; give it to a long `<li>` or `<dd>` that holds text directly.
  The body sets `overflow-wrap: break-word`, so an unbroken URL, code, or topic
  wraps instead of widening the page.

## Type rules

- **The scale, nothing else.** No `text-xs` (12 px) and no arbitrary size
  (`text-[11px]`) anywhere under `frontend/src`. `eslint.config.js` refuses
  both in any string or template literal through `no-restricted-syntax`, so
  `npm run lint` (`--max-warnings 0`, the pre-commit hook and CI) keeps them
  out.
- **Prose or caption.** Prose and controls are `text-sm` or `text-base`. Meta
  — timestamps, units, badge text, legend and axis captions, footnotes, codes in
  chips — is `text-caption` on a `<span>`, `<time>`, or `<small>`, never on a
  `<p>`, `<li>`, `<td>`, `<label>`, or `<button>`. A caption that needs its own
  line is a block `<span>`, not a paragraph.
- **Headings by the scale.** `PageHeader` sets the route's `<h1>` in `text-2xl`;
  `SectionHeading` sets h2 in `text-lg`, h3 in `text-base`, h4 in `text-sm`.
  Every route keeps an `<h1>` with its name, visually hidden (`hideTitle`) where
  the design wants, because the shell's test finds each by its exact name.
- **Figures that change** — a distance, a bearing, a percentage, an age, a
  countdown, a count — set `tabular-nums` so they do not jitter.
- **Chart text.** SVG labels take `text-caption` in the chart's own user units,
  and each chart is no wider than its `viewBox` (`max-w-[560px]` for the level
  history and wind-probability charts, `max-w-[420px]` for the arrival
  timeline), so a label is 13 px at full size and only ever smaller on a narrow
  screen. A chart's readable form is its visually hidden table, which is why the
  readability gate skips chart internals. The last axis label ends at its tick
  (`tickAnchor`), so it never runs past the right edge.

## Primitives

`frontend/src/ui/`, one file each with a test beside it. None sets a `style`
attribute or reads the clock.

- **`Card`** — a surface that groups one subject: `as` (`section`, `article`,
  `div`, `aside`, `figure`), `level` for a threat tint, `elevation` (`flat`,
  `card`, `raised`), and `padding` (`none`, `sm`, `md`). Use it for every boxed
  region of a page.
- **`PageHeader`** — a route's `<h1>`, a one-line summary, and an actions slot;
  `titleId` labels a section by it, and `hideTitle` keeps the heading only for
  assistive technology.
- **`SectionHeading`** — a heading inside a page or card (`as` h2 to h4) with an
  optional description and actions.
- **`StatTile`** — one number: a caption label, the value in `tabular-nums` at
  `text-2xl`, a unit, an optional caption, and a trend in words beside its
  arrow. It is a labelled `group`.
- **`Callout`** — a boxed message beside what it concerns: `note`, `info`,
  `warning`, or `error`. Its role defaults to `note`, `status`, `alert`, and
  `alert`; pass `role` to keep the role an existing use already has, or `none`.
  An alarm the reader must not miss (the stale monitor) is a `warning` with
  `role="alert"`.
- **`Chip`** — a short caption-sized label (a code, a count, a state) in a tone
  (`neutral`, `brand`, `ai`, `warning`) or a threat level.
- **`Button` and `LinkButton`** — `primary`, `secondary`, `ghost`, and `danger`
  in `sm` or `md`, each with a visible focus ring and a target of at least 24 by
  24 CSS pixels. `LinkButton` takes `to` for a route inside the app or `href`
  for a plain link (a download). A button defaults to `type="button"`.
- **`Disclosure`** — detail one click away: a native `<details>` and `<summary>`
  with a chevron and an optional caption, closed by default. Native, because
  closed content stays in the DOM (the browser tests read it), needs no script,
  sets no inline style, is keyboard- and screen-reader-native, and prints; never
  a Radix collapsible, which unmounts what it hides and sets inline styles.

## Navigation

`AppShell.tsx`'s `NAV_ITEMS` hold one `{ to, label, icon, end }` object per
line, in a fixed order (two earlier phases' verifiers read the literals). Each
link shows its lucide icon beside its label (stacked above it on phones, in a
four-column grid that fits 360 px). Live status badges sit beside their links,
never inside them:

| Link     | Badge                                     | Query key     |
| -------- | ----------------------------------------- | ------------- |
| Dashboard | the highest current level, in its accent | `assessments` |
| Storms   | the active storm count                    | `storms`      |
| Alerts   | the count of alerts covering a location   | `alerts`      |
| Ask      | the AI state when not ready               | `ai`          |
| Settings | a warning mark when the monitor is stale  | `health`      |

Each badge reads an existing route through its shared query key
(`frontend/src/app/navStatus.ts`), so the shell and the page share one cache
entry and the server's events refresh both; nothing polls. A badge is
`aria-hidden` and is described to assistive technology by the link's
`aria-describedby`, which points at a hidden sentence ("Highest current level:
5, Hurricane Warning"), so every link's text and accessible name stay its label.

## Vocabulary

Step 3 completes these rules (Phase 8 Decisions 7 and 8):

- **Plain English leads.** A location's headline is the engine's level name
  ("At least" before it when the assessment is incomplete), the deciding rule's
  sentence, and the level's actions — never a rule id, product code, source id,
  zone, breakpoint span, or raw timestamp.
- **Provenance is one click away and never removed.** Rule ids, evidence,
  official products, unavailable inputs, coverage, and the evacuation-order
  switch live in a `Disclosure` whose summary reads "Why this level / Official
  provenance & controls". What a reader must not miss stays outside it: the
  "At least" floor, a toggle-changed note, and an evacuation order that is on.
- **One vocabulary: the engine's.** Level names, rule names, products, and
  codes come from the server (`GET /api/ladder` from Step 3), never from a table
  written in the frontend.
- **Colour is only for threat.** The threat palette marks levels; everything
  else is neutral or brand. Colour is never the only signal: a level always
  carries its number and name.

## The readability gate

`frontend/e2e/readability.ts` exports `auditReadability(page)`, Decision 6's
four computed checks, run in the page with no package. It inspects every visible
element that has its own text inside `<header>`, `<main>`, and `<footer>`,
skipping SVG chart internals, visually hidden text, closed `<details>` content,
and everything inside the Leaflet container:

1. **Size.** Primary prose (`p`, `li`, `dd`, `dt`, `td`, `th`, `label`,
   `summary`, `blockquote`, `figcaption`, `legend`, `a`, `button`, and anything
   with `role="note"`, `"alert"`, or `"status"`) computes at least 14 px; any
   other text at least 13 px.
2. **Contrast.** The WCAG 2.2 ratio between the text's colour and the first
   opaque background up its ancestors, alpha-composited, is at least 4.5:1, or
   3:1 for large text (24 px, or 18.66 px at weight 700). A background image or
   gradient behind text is a finding of its own, because its contrast cannot be
   computed. Colours are normalised to sRGB by painting them on a 1×1 canvas, so
   OKLCH, OKLab, and `color-mix` values compare like any other.
3. **Measure.** A `p`, `li`, or `dd` holding 160 characters or more is at most
   42 em wide.
4. **Overflow.** The page never scrolls sideways, and no audited element's box —
   or its own text, which can spill past the box — extends past the viewport's
   right edge unless an ancestor scrolls it on purpose (`overflow-x: auto` or
   `scroll`). A page-level finding names the innermost box that widens the page.
   The shell no longer clips horizontal overflow, which would hide it.

Each finding names the element (a short selector path), its computed value, and
a text sample. `readability.spec.ts` runs the audit under the browser-test guard
over eight renders — `/`, `/map`, `/replay` with its storm loaded, `/storms`,
`/alerts`, `/timeline`, `/ask`, and `/settings` — at 1440×900, 1280×800, and
360×740 on the `quiet` (8802) and `landfall` (8806) scenario servers in light,
and again at 1440×900 in dark, and fails on any finding, printing every one.
Step 7 makes `/settings` one render per tab, twelve in all; Step 8's dogfood
harness runs the same audit over every scenario. The scenario servers hold only
the public landmarks and the synthetic storm, so the printed samples carry
nothing private.

## Layout

- Breakpoints are Tailwind's: `sm` 640 px, `md` 768 px, `lg` 1024 px, and `xl`
  1280 px. Pages are designed at 360 px first; the shell's content column is
  `max-w-6xl` (72 rem).
- A table wider than its card scrolls inside an `overflow-x-auto` wrapper; a
  page never scrolls sideways.

## Motion

- `prefers-reduced-motion: reduce` collapses every animation and transition
  (the base layer of `index.css`).
- No page runs an infinite animation or a timer while idle: the idle budget
  (0.5 percent of a core for the server and the tab, `scripts/measure_idle.py`)
  is measured on `/`.

## Accessibility

- Every interactive element shows a visible focus ring
  (`focus-visible:outline-2 focus-visible:outline-offset-2
  focus-visible:outline-brand`).
- Targets are at least 24 by 24 CSS pixels (WCAG 2.2, 2.5.8).
- Colour is never the only signal: a level carries its number and name, a state
  its word, an alarm its text.
- Live regions announce what changes without a reload (the event-stream status,
  the dashboard's level announcements, the stale-monitor alert); badges and
  icons are `aria-hidden`, with the words in the accessible name or
  description.

## CSP rules

The page runs under a Content-Security-Policy whose `style-src` has no
`unsafe-inline`, with a per-answer nonce:

- No `style=` attribute anywhere under `frontend/src`, tests included: position
  and size are Tailwind classes, and a chart's geometry is SVG attributes.
- No markup built from text: no `innerHTML` or `dangerouslySetInnerHTML`, AI
  text renders as plain text, and Leaflet popups are DOM nodes.
- Radix's injected styles (the theme menu, the dialogs, the toasts) carry the
  existing per-answer nonce (`frontend/src/app/nonce.ts`).
- No new package, font host, or outbound host; `CSP_SUFFIX` and
  `frontend/index.html`'s nonce meta and scripts stay as they are.

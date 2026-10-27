// frontend/scripts/check-licenses.mjs
import { readFileSync } from "node:fs";

const ALLOWED_LICENSES = new Set([
  "MIT",
  "ISC",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "Apache-2.0",
  "0BSD",
]);

function isAllowedExpression(expression) {
  if (typeof expression !== "string" || expression.trim() === "") {
    return false;
  }
  const normalized = expression.replace(/[()]/g, " ").trim();
  if (ALLOWED_LICENSES.has(normalized)) {
    return true;
  }
  if (normalized.includes(" OR ")) {
    return normalized
      .split(/\s+OR\s+/)
      .some((part) => ALLOWED_LICENSES.has(part.trim()));
  }
  if (normalized.includes(" AND ")) {
    return normalized
      .split(/\s+AND\s+/)
      .every((part) => ALLOWED_LICENSES.has(part.trim()));
  }
  return false;
}

const raw = readFileSync("../src/weatherbot/web/static/licenses.json", "utf8");
const parsed = JSON.parse(raw);
if (!Array.isArray(parsed)) {
  process.stderr.write("licenses:check: expected a JSON array in licenses.json\n");
  process.exit(1);
}

const disallowed = [];
for (const entry of parsed) {
  const pkgName = typeof entry?.name === "string" ? entry.name : "<unknown>";
  const pkgVersion = typeof entry?.version === "string" ? `@${entry.version}` : "";
  const rawLicense =
    typeof entry?.identifier === "string"
      ? entry.identifier
      : typeof entry?.license === "string"
        ? entry.license
        : "<missing>";
  if (!isAllowedExpression(rawLicense)) {
    disallowed.push(`${pkgName}${pkgVersion} (${rawLicense})`);
  }
}

if (disallowed.length > 0) {
  process.stderr.write(
    `licenses:check: disallowed package licences: ${disallowed.join(", ")}\n`,
  );
  process.exit(1);
}

process.stdout.write(
  `licenses:check: verified ${String(parsed.length)} bundled package(s) against allowlist.\n`,
);

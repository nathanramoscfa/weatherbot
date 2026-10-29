// frontend/e2e/node-env.d.ts
declare const process: {
  env: Record<string, string | undefined>;
  argv: string[];
};

declare module "node:fs" {
  export function readFileSync(path: string, encoding: "utf8"): string;
  export function writeFileSync(
    path: string,
    data: string,
    encoding?: "utf8",
  ): void;
  export function mkdirSync(
    path: string,
    options?: { recursive?: boolean },
  ): void;
  export function rmSync(path: string, options?: { force?: boolean }): void;
}

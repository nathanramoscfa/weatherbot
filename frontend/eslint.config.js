// frontend/eslint.config.js
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import security from "eslint-plugin-security";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "node_modules/**",
      "coverage/**",
      "test-results/**",
      "playwright-report/**",
      "src/api/schema.d.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  reactHooks.configs.flat.recommended,
  security.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: {
        ...globals.browser,
      },
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports" },
      ],
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // The type scale (docs/DESIGN.md, Phase 8 Decision 4): no 12 px
      // `text-xs` and no arbitrary font size such as `text-[11px]`. Prose
      // takes text-sm or text-base, and meta text-caption on a span, time, or
      // small.
      "no-restricted-syntax": [
        "error",
        {
          selector: String.raw`Literal[value=/text-xs|text-\[(?:length:)?[0-9.]/]`,
          message:
            "Use the type scale (text-caption, text-sm, text-base, …), never text-xs or an arbitrary font size (docs/DESIGN.md).",
        },
        {
          selector: String.raw`TemplateElement[value.raw=/text-xs|text-\[(?:length:)?[0-9.]/]`,
          message:
            "Use the type scale (text-caption, text-sm, text-base, …), never text-xs or an arbitrary font size (docs/DESIGN.md).",
        },
      ],
    },
  },
  {
    files: ["**/*.{js,mjs}"],
    ...tseslint.configs.disableTypeChecked,
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
  },
);

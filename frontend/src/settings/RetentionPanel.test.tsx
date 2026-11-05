// frontend/src/settings/RetentionPanel.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import retentionFixture from "../test/fixtures/retention.json";
import settingsFixture from "../test/fixtures/settings.json";
import { RetentionPanel } from "./RetentionPanel.tsx";

const TYPED_RETENTION = asSchema<components["schemas"]["RetentionResponse"]>(
  retentionFixture satisfies JsonFixture<
    components["schemas"]["RetentionResponse"]
  >,
);
const TYPED_SETTINGS = asSchema<components["schemas"]["SettingsResponse"]>(
  settingsFixture satisfies JsonFixture<
    components["schemas"]["SettingsResponse"]
  >,
);

describe("RetentionPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("displays database and WAL sizes, saves [retention] history_days, previews a plan, and runs Prune now behind a Radix AlertDialog", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.retention(), TYPED_RETENTION);
    queryClient.setQueryData(queryKeys.settings(), TYPED_SETTINGS);

    const putSpy = vi.spyOn(apiClient, "PUT").mockResolvedValue({
      data: {
        settings_file_sha256: "c".repeat(64),
        applied_next_cycle: ["[retention] history_days"],
        applied_next_start: [],
        restart_keys: [],
        settings: TYPED_SETTINGS.settings,
        notice: TYPED_SETTINGS.notice,
      },
      response: new Response(null, { status: 200 }),
    });

    const postSpy = vi.spyOn(apiClient, "POST").mockResolvedValue({
      data: {
        status: "accepted",
        cutoff: TYPED_RETENTION.plan.cutoff,
        started_at: "2026-10-13T01:35:00Z",
        notice: TYPED_RETENTION.notice,
      },
      response: new Response(null, { status: 202 }),
    });

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <RetentionPanel />
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Database & Retention" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/256\.0 KiB/)).toBeInTheDocument();
    expect(container.querySelector("[style]")).toBeNull();

    const daysInput = screen.getByLabelText(/Automatic retention window/i);
    await user.clear(daysInput);
    await user.type(daysInput, "90");
    await user.click(
      screen.getByRole("button", { name: "Save retention window" }),
    );

    expect(putSpy).toHaveBeenCalledWith("/api/settings", {
      body: {
        expected_sha256: TYPED_SETTINGS.settings_file_sha256,
        changes: [
          {
            table: "retention",
            key: "history_days",
            value: 90,
          },
        ],
      },
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Saved \[retention\] history_days = 90 days/i,
    );

    // Open Prune now confirmation dialog
    await user.click(screen.getByRole("button", { name: "Prune now" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: /Prune records older than 365 days\?/i,
    });
    expect(dialog).toHaveTextContent(/Protected by keep-list/i);
    await user.click(
      within(dialog).getByRole("button", { name: "Confirm prune" }),
    );

    expect(postSpy).toHaveBeenCalledWith("/api/retention/run", {
      body: { cutoff: TYPED_RETENTION.plan.cutoff },
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Retention prune started for cutoff/i,
    );
  });
});

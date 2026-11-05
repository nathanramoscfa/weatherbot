// frontend/src/settings/QuietHoursForm.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import settingsFixture from "../test/fixtures/settings.json";
import { QuietHoursForm } from "./QuietHoursForm.tsx";

const TYPED_SETTINGS = asSchema<components["schemas"]["SettingsResponse"]>(
  settingsFixture satisfies JsonFixture<
    components["schemas"]["SettingsResponse"]
  >,
);

describe("QuietHoursForm", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("explains that levels 1 and 2 alone are held and escalations always arrive, saves via PUT /api/settings, and states next_cycle", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.settings(), TYPED_SETTINGS);

    const putSpy = vi.spyOn(apiClient, "PUT").mockResolvedValue({
      data: {
        settings_file_sha256: "b".repeat(64),
        applied_next_cycle: [
          "[notifications] quiet_hours_start",
          "[notifications] quiet_hours_end",
        ],
        applied_next_start: [],
        restart_keys: [],
        settings: TYPED_SETTINGS.settings,
        notice: TYPED_SETTINGS.notice,
      },
      response: new Response(null, { status: 200 }),
    });

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <QuietHoursForm />
      </QueryClientProvider>,
    );

    expect(
      screen.getByText(/Level 1 \(All Clear\) and Level 2 \(Monitor\)/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/any upward escalation always arrive immediately/i),
    ).toBeInTheDocument();
    expect(container.querySelector("[style]")).toBeNull();

    const startInput = screen.getByLabelText(/Quiet hours start/i);
    const endInput = screen.getByLabelText(/Quiet hours end/i);
    await user.clear(startInput);
    await user.type(startInput, "22:00");
    await user.clear(endInput);
    await user.type(endInput, "07:00");

    await user.click(screen.getByRole("button", { name: "Save quiet hours" }));

    expect(putSpy).toHaveBeenCalledWith("/api/settings", {
      body: {
        expected_sha256: TYPED_SETTINGS.settings_file_sha256,
        changes: [
          {
            table: "notifications",
            key: "quiet_hours_start",
            value: "22:00",
          },
          {
            table: "notifications",
            key: "quiet_hours_end",
            value: "07:00",
          },
        ],
      },
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Changes apply on the next monitor cycle/i,
    );
  });

  it("shows the environment variable and disables inputs when origin is environment, and reloads on 409 stale file", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    const envSettings = {
      ...TYPED_SETTINGS,
      settings: TYPED_SETTINGS.settings.map((item) =>
        item.table === "notifications" && item.key === "quiet_hours_start"
          ? {
              ...item,
              value: "23:00",
              origin: "environment" as const,
            }
          : item,
      ),
    };
    queryClient.setQueryData(queryKeys.settings(), envSettings);

    vi.spyOn(apiClient, "PUT").mockResolvedValue({
      data: undefined,
      error: {
        detail: "weatherbot.toml changed on disk; reload settings and try again",
      } as never,
      response: new Response(null, { status: 409 }),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <QuietHoursForm />
      </QueryClientProvider>,
    );

    const startInput = screen.getByLabelText(/Quiet hours start/i);
    expect(startInput).toBeDisabled();
    expect(
      screen.getByText("WEATHERBOT_NOTIFICATIONS_QUIET_HOURS_START"),
    ).toBeInTheDocument();

    const endInput = screen.getByLabelText(/Quiet hours end/i);
    await user.clear(endInput);
    await user.type(endInput, "07:00");
    await user.click(screen.getByRole("button", { name: "Save quiet hours" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Reloaded the latest settings — review and save again/i,
    );
  });
});

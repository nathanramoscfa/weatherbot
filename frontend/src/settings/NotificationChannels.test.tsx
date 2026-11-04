// frontend/src/settings/NotificationChannels.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import notificationChannelsFixture from "../test/fixtures/notification-channels.json";
import notificationsFixture from "../test/fixtures/notifications.json";
import { NotificationChannels } from "./NotificationChannels.tsx";

const TYPED_CHANNELS = asSchema<
  components["schemas"]["NotificationChannelsResponse"]
>(
  notificationChannelsFixture satisfies JsonFixture<
    components["schemas"]["NotificationChannelsResponse"]
  >,
);
const TYPED_NOTIFICATIONS = asSchema<
  components["schemas"]["NotificationsResponse"]
>(
  notificationsFixture satisfies JsonFixture<
    components["schemas"]["NotificationsResponse"]
  >,
);

describe("NotificationChannels", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("renders all four channels with state badges, details, and last delivery outcomes", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.notificationChannels(), {
      ...TYPED_CHANNELS,
      channels: [
        ...TYPED_CHANNELS.channels.slice(0, 3),
        {
          name: "ntfy",
          state: "unconfigured",
          detail:
            "Set WEATHERBOT_NTFY_TOPIC in the environment and restart serve.",
          last_result: null,
          last_attempted_at: null,
        },
      ],
    });

    render(
      <QueryClientProvider client={queryClient}>
        <NotificationChannels />
      </QueryClientProvider>,
    );

    const logCard = screen.getByTestId("channel-card-log");
    expect(within(logCard).getByText("on")).toBeInTheDocument();
    expect(
      within(logCard).getByText(/Last delivery: delivered/i),
    ).toBeInTheDocument();

    const toastCard = screen.getByTestId("channel-card-toast");
    expect(within(toastCard).getByText("on")).toBeInTheDocument();
    expect(
      within(toastCard).getByText(/Windows desktop toast/i),
    ).toBeInTheDocument();

    const browserCard = screen.getByTestId("channel-card-browser");
    expect(within(browserCard).getByText("on")).toBeInTheDocument();

    const ntfyCard = screen.getByTestId("channel-card-ntfy");
    expect(within(ntfyCard).getByText("unconfigured")).toBeInTheDocument();
    expect(
      within(ntfyCard).getByText(
        /Set WEATHERBOT_NTFY_TOPIC in the environment/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(ntfyCard).getByText("Last delivery: none recorded yet"),
    ).toBeInTheDocument();
  });

  it("refreshes notifications and notificationChannels when Send test notification succeeds", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.notificationChannels(), TYPED_CHANNELS);
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    vi.spyOn(apiClient, "POST").mockResolvedValueOnce({
      data: TYPED_NOTIFICATIONS.notifications[0]!,
      response: new Response(null, { status: 200 }),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <NotificationChannels />
      </QueryClientProvider>,
    );

    await user.click(
      screen.getByRole("button", { name: "Send test notification" }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Test notification sent/i,
    );
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.notifications(),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.notificationChannels(),
    });
  });
});

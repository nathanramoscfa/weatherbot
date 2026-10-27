// frontend/src/notifications/notify.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StreamEvent } from "../events/useEventStream";
import {
  BROWSER_NOTIFICATIONS_STORAGE_KEY,
  deliverBrowserNotification,
  getBrowserNotificationPermission,
  readBrowserNotificationsEnabled,
  requestBrowserNotificationPermission,
  writeBrowserNotificationsEnabled,
} from "./notify";

interface RecordedNotification {
  title: string;
  options: NotificationOptions | undefined;
}

const recorded: RecordedNotification[] = [];
let mockPermission: NotificationPermission = "default";
let requestPermissionSpy = vi.fn<() => Promise<NotificationPermission>>(() =>
  Promise.resolve("granted"),
);

class FakeNotification {
  static get permission(): NotificationPermission {
    return mockPermission;
  }

  static requestPermission(): Promise<NotificationPermission> {
    return requestPermissionSpy();
  }

  readonly title: string;
  readonly options: NotificationOptions | undefined;

  constructor(title: string, options?: NotificationOptions) {
    this.title = title;
    this.options = options;
    recorded.push({ title, options });
  }
}

function setVisibility(state: DocumentVisibilityState): void {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => state,
  });
}

const SAMPLE_NOTIFICATION_EVENT: StreamEvent = {
  id: 7,
  kind: "notification",
  at: "2026-10-13T01:30:00Z",
  invalidate: ["notifications", "timeline"],
  started_at: null,
  cycle_id: 1,
  runner: "serve",
  trigger: "manual",
  status: "complete",
  snapshot_id: null,
  location: "Miami-Dade County Hall",
  assessment_id: 1,
  level: 4,
  complete: true,
  notification_id: 1,
  notification_kind: "location",
  escalation: true,
  title: "Miami-Dade County Hall — Level 4 (Prepare to Evacuate)",
  body: ["Level 4: Evacuation order is in effect", "Review your evacuation plan."],
  display: true,
};

describe("notify", () => {
  beforeEach(() => {
    recorded.length = 0;
    mockPermission = "default";
    requestPermissionSpy = vi.fn(() => {
      mockPermission = "granted";
      return Promise.resolve("granted");
    });
    vi.stubGlobal("Notification", FakeNotification);
    window.localStorage.clear();
    setVisibility("visible");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
    setVisibility("visible");
  });

  it("reads and writes the browser notification switch in localStorage", () => {
    expect(readBrowserNotificationsEnabled()).toBe(false);
    writeBrowserNotificationsEnabled(true);
    expect(
      window.localStorage.getItem(BROWSER_NOTIFICATIONS_STORAGE_KEY),
    ).toBe("on");
    expect(readBrowserNotificationsEnabled()).toBe(true);
    writeBrowserNotificationsEnabled(false);
    expect(readBrowserNotificationsEnabled()).toBe(false);
  });

  it("requests browser permission only when called and reports permission states", async () => {
    expect(getBrowserNotificationPermission()).toBe("default");
    const result = await requestBrowserNotificationPermission();
    expect(result).toBe("granted");
    expect(requestPermissionSpy).toHaveBeenCalledTimes(1);

    // Calling again when already granted does not re-prompt.
    const second = await requestBrowserNotificationPermission();
    expect(second).toBe("granted");
    expect(requestPermissionSpy).toHaveBeenCalledTimes(1);
  });

  it("fires a Web Notification only when display is true, switch is on, permission is granted, and page is hidden", () => {
    writeBrowserNotificationsEnabled(true);
    mockPermission = "granted";

    // Page is visible -> no Web Notification (in-page toast handles it).
    setVisibility("visible");
    expect(deliverBrowserNotification(SAMPLE_NOTIFICATION_EVENT)).toBe(false);
    expect(recorded).toHaveLength(0);

    // Page is hidden -> fires Web Notification.
    setVisibility("hidden");
    expect(deliverBrowserNotification(SAMPLE_NOTIFICATION_EVENT)).toBe(true);
    expect(recorded).toHaveLength(1);
    expect(recorded[0]?.title).toBe(
      "Miami-Dade County Hall — Level 4 (Prepare to Evacuate)",
    );
    expect(recorded[0]?.options?.body).toBe(
      "Level 4: Evacuation order is in effect\nReview your evacuation plan.",
    );

    // Switch is off -> no Web Notification.
    writeBrowserNotificationsEnabled(false);
    expect(deliverBrowserNotification(SAMPLE_NOTIFICATION_EVENT)).toBe(false);
    expect(recorded).toHaveLength(1);

    // Permission is denied -> no Web Notification.
    writeBrowserNotificationsEnabled(true);
    mockPermission = "denied";
    expect(deliverBrowserNotification(SAMPLE_NOTIFICATION_EVENT)).toBe(false);
    expect(recorded).toHaveLength(1);

    // display is false -> no Web Notification.
    mockPermission = "granted";
    expect(
      deliverBrowserNotification({
        ...SAMPLE_NOTIFICATION_EVENT,
        display: false,
      }),
    ).toBe(false);
    expect(recorded).toHaveLength(1);
  });
});

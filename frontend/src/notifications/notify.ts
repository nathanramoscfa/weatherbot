// frontend/src/notifications/notify.ts
import type { StreamEvent } from "../events/useEventStream";

export const BROWSER_NOTIFICATIONS_STORAGE_KEY = "weatherbot.notifications";

export type BrowserNotificationPermission =
  | NotificationPermission
  | "unsupported";

export function readBrowserNotificationsEnabled(): boolean {
  try {
    const raw = window.localStorage.getItem(BROWSER_NOTIFICATIONS_STORAGE_KEY);
    return raw === "on" || raw === "true";
  } catch {
    return false;
  }
}

export function writeBrowserNotificationsEnabled(enabled: boolean): void {
  try {
    window.localStorage.setItem(
      BROWSER_NOTIFICATIONS_STORAGE_KEY,
      enabled ? "on" : "off",
    );
  } catch {
    // Ignore storage quota or private-mode errors.
  }
}

export function getBrowserNotificationPermission(): BrowserNotificationPermission {
  if (typeof Notification === "undefined") {
    return "unsupported";
  }
  return Notification.permission;
}

export async function requestBrowserNotificationPermission(): Promise<BrowserNotificationPermission> {
  if (typeof Notification === "undefined") {
    return "unsupported";
  }
  if (Notification.permission === "granted") {
    return "granted";
  }
  try {
    return await Notification.requestPermission();
  } catch {
    return Notification.permission;
  }
}

export function deliverBrowserNotification(event: StreamEvent): boolean {
  if (event.kind !== "notification" || !event.display) {
    return false;
  }
  if (!readBrowserNotificationsEnabled()) {
    return false;
  }
  if (
    typeof Notification === "undefined" ||
    Notification.permission !== "granted"
  ) {
    return false;
  }
  if (
    typeof document === "undefined" ||
    document.visibilityState !== "hidden"
  ) {
    return false;
  }

  const title = event.title ?? "Weatherbot notification";
  const body = (event.body ?? []).join("\n");
  try {
    new Notification(title, { body });
    return true;
  } catch {
    return false;
  }
}

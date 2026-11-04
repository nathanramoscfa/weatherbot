<!-- docs/NOTIFICATIONS.md -->
# Notifications and the phone channel

Weatherbot decides notifications from official NHC and NWS products through a
pure policy (`weatherbot.services.policy`) and delivers each notification
through four channels: the local SQLite log, Windows desktop toasts, the
dashboard's browser notifications, and phone push notifications through `ntfy`.
This page covers what each channel does, how to configure `ntfy`, what leaves
the machine, per-location notification preferences, priorities, quiet hours,
and the operational runbook.

## Channels

Every notification is stored in `notifications` with one `notification_deliveries`
row per configured channel:

- **`log`** (`LogChannel`) — the local SQLite notification log, shown by
  `weatherbot notify log` and on the dashboard's Timeline and Settings pages.
  It is always on, never interrupts the operator, and is never muted by
  per-location preferences or quiet hours.
- **`toast`** (`ToastChannel`) — Windows desktop notifications via WinRT
  (`windows-toasts` / `pywinrt`). Enabled by default (`[notifications] toast =
  true`); requires one-time application identity registration with `weatherbot
  notify setup` on Windows.
- **`browser`** (`BrowserChannel`) — Server-Sent Event (`notification`) pushes
  to open dashboard tabs (`weatherbot serve`), which raise a Web Notification
  when the browser has granted permission. Enabled by default (`[notifications]
  browser = true`).
- **`ntfy`** (`NtfyChannel`) — HTTPS JSON POST delivery to an `ntfy` server
  (`https://ntfy.sh` by default, or a self-hosted server). Off by default
  (`[notifications] ntfy = false`) so no traffic leaves the machine until the
  operator enables it and sets a topic in the environment.

When `[notifications] ntfy` is `false`, `Context.channels` omits the channel
entirely so `weatherbot notify test` tests only the active channels.

## Setting up ntfy

`ntfy` uses a topic name to route messages to subscribed phones. On a public
server without access control, **the topic name is your password**: anyone who
knows the topic can read or publish to it.

1. Generate a long, random topic in your own terminal:

   ```sh
   python -c "import secrets; print('weatherbot-' + secrets.token_urlsafe(18))"
   ```

2. Subscribe to that topic in the `ntfy` mobile app (iOS or Android). On
   Android, keep instant delivery enabled (or ensure Firebase delivery is
   active) so notifications arrive immediately.

3. Open the Windows **Environment Variables** dialog (`rundll32.exe
   sysdm.cpl,EditEnvironmentVariables`) and set `WEATHERBOT_NTFY_TOPIC` in your
   **User variables** (never on a command line where shell history stores it).
   If your server requires bearer authentication, also set
   `WEATHERBOT_NTFY_TOKEN` there.

4. Enable the channel in `weatherbot.toml`:

   ```toml
   [notifications]
   ntfy = true
   ntfy_server = "https://ntfy.sh"
   ```

   `ntfy_server` must use `https://` unless the host is loopback (`127.0.0.1`,
   `::1`, or `localhost`), and it must not carry a URL path, query string,
   fragment, or credentials.

5. Restart `\Weatherbot\serve` so the scheduled task inherits the updated User
   environment, then verify with `weatherbot doctor --offline` and `weatherbot
   notify test`.

Neither `WEATHERBOT_NTFY_TOPIC` nor `WEATHERBOT_NTFY_TOKEN` is a `Settings`
field or an `ENVIRONMENT_OVERRIDES` entry. Neither appears in `weatherbot
config show`, `GET /api/settings`, `GET /api/notifications/channels`, stored
delivery details, log records, or tracebacks (`SecretFilter` and
`redact_secrets` scrub both values and `tk_…` token shapes at every log level).

## What leaves the machine

When `[notifications] ntfy` is `true` and a notification is delivered to `ntfy`,
`NtfyChannel` sends one `POST` request to the root of `ntfy_server` (for
example `https://ntfy.sh/`) with `follow_redirects=False`, TLS verification on,
and the project's `User-Agent`.

The topic is sent **in the JSON request body** (`"topic"`), never in the URL
path, so the topic never enters `httpx` request URLs, exception strings, or
proxy and server access logs. When `WEATHERBOT_NTFY_TOKEN` is set, it travels
only in the `Authorization: Bearer <token>` header.

The JSON body carries five fields:

- `topic` — the value of `WEATHERBOT_NTFY_TOPIC`.
- `title` — the notification's title, which names the location and the threat
  level (or the system alarm kind).
- `message` — the engine's change sentences (or system alarm lines) followed by
  the one-line informational-only disclaimer notice, cut to at most 4,000 UTF-8
  bytes at a character boundary so `ntfy` never turns a long message into a
  file attachment (its limit is 4,096 bytes) and never cuts off the disclaimer.
- `priority` — an integer from 3 to 5.
- `tags` — emoji shortcodes from a fixed table (`rotating_light`, `warning`,
  `white_check_mark`, `test_tube`).

No notification title or body ever carries a latitude, longitude, coordinate
pair, polygon, or distance in kilometres or miles (`engine/changes.py` and
`services/policy.py` write only product names, codes, advisory numbers, and
levels, and a test enforces this).

**What `ntfy.sh` does with delivered messages (read 2026-11-03):**

- Messages are cached on the server for 12 hours so phones that reconnect can
  fetch missed notifications.
- `ntfy.sh` logs topics and client IP addresses for abuse prevention and rate
  limiting.
- On Android, messages without `Firebase: no` are forwarded through Firebase
  Cloud Messaging so phones wake promptly when backgrounded.
- `ntfy.sh`'s free tier allows 250 messages per day and a burst of 60 requests
  (refilling one request every 5 seconds).
- Operators who want no third-party message cache or IP logging can point
  `ntfy_server` at a self-hosted `ntfy` server.

## Per-location preferences

Each watched location has its own `LocationPreferences` (`toast`, `browser`,
`phone`, all `true` by default, and `phone_min_level`, `2` by default), edited
on the Settings page (`PUT /api/locations/preferences`) and stored in the
`locations` table (revision `0009`).

Preferences filter **delivery channels**, never the policy's decisions:

- When a location turns off `toast`, `browser`, or `phone`, `NotificationService`
  still records the notification and its policy decisions in SQLite, and writes
  a `notification_deliveries` row with `result = "muted"` and `detail = "turned
  off for this location"` without calling the channel.
- When `phone` is on and a location notification's level is below the
  location's `phone_min_level`, `ntfy` records `result = "muted"` with `detail
  = "below this location's phone level"` — **unless** the location's previous
  location notification was delivered to `ntfy`. Because a de-escalation carries
  the level it drops *to* (such as level 1, All Clear), that exception guarantees
  that a phone woken by a level 3–5 alarm always receives the all-clear that
  ends it.
- `latest_delivery` skips `muted` rows, so muting a noisy location never causes
  `weatherbot doctor` to fail and never hides an earlier channel failure on the
  Settings page.
- Location-free notifications (`test`, `degraded`, `recovered`, and
  `stale_monitor`) ignore per-location preferences and reach every active
  channel. When a `degraded` source alarm was delivered over `ntfy` (even with
  desktop toasts off), the matching `recovered` notice is delivered over `ntfy`
  as well.

## Priorities, quiet hours, and limits

`NtfyChannel` assigns `ntfy` priorities so every phone notification vibrates or
sounds by default (`ntfy` vibrates and sounds at priority 3 and above, and pops
over at 4 and 5):

- **Priority 5** (`rotating_light`) — an escalation to level 5 (Extreme Threat).
- **Priority 4** (`warning`) — any other escalation, any level 4 notification,
  or a `degraded` / `stale_monitor` alarm.
- **Priority 3** (`warning`, `white_check_mark`, or `test_tube`) — non-escalating
  notifications at levels 1–3, `recovered` notices, and `notify test`.

Quiet hours (`[notifications] quiet_hours_start`, `quiet_hours_end`, and
`quiet_hours_time_zone`) are global in the policy: non-escalating notifications
at or below level 2 are held back during quiet hours, while escalations and
levels 3–5 always deliver immediately through every interrupting channel,
including `ntfy`.

Each `ntfy` delivery uses a 5-second timeout and retries at most once (after 3
seconds, or `Retry-After` up to 5 seconds on HTTP 429) on a timeout, connection
error, HTTP 429, or HTTP 5xx, so a slow or failing server holds the monitor
cycle lock for at most 15 seconds, and `ntfy` runs last in the channel tuple so
local log, toast, and browser deliveries never wait on it.

## Runbook

### A failed `ntfy` delivery (`doctor` fails `ntfy`)

1. Run `weatherbot doctor --offline` or check **Notification Channels** on the
   Settings page to see the latest `ntfy` delivery detail (`HTTP 401`, `HTTP
   403`, `HTTP 429`, `HTTP 5xx`, `ReadTimeout`, or `WEATHERBOT_NTFY_TOPIC is not
   set`).
2. If the detail is `WEATHERBOT_NTFY_TOPIC is not set`: set
   `WEATHERBOT_NTFY_TOPIC` in the Windows Environment Variables dialog, restart
   `\Weatherbot\serve`, and run `weatherbot notify test`.
3. If the detail is `HTTP 401` or `HTTP 403`: the server rejected the bearer
   token or topic permissions. Check `WEATHERBOT_NTFY_TOKEN` and your server's
   ACL for the topic.
4. If the detail is `HTTP 429`: the server rate-limited the request or the
   daily quota (250 messages/day on `ntfy.sh`) was reached. Wait for the window
   to reset, then run `weatherbot notify test`.
5. Once the cause is resolved, run `weatherbot notify test`: a new `delivered`
   row clears the `doctor` alarm.

### Rotating `WEATHERBOT_NTFY_TOKEN`

1. Issue a new access token on your `ntfy` server and revoke the old token.
2. Update `WEATHERBOT_NTFY_TOKEN` in the Windows Environment Variables dialog.
3. Restart the scheduled task so the background service reads the new token:

   ```powershell
   schtasks /End /TN "\Weatherbot\serve"
   schtasks /Run /TN "\Weatherbot\serve"
   ```

4. Open a new terminal and run `weatherbot notify test` to confirm `ntfy:
   delivered`.

### Replacing a leaked `WEATHERBOT_NTFY_TOPIC`

If a topic on a public server is ever exposed:

1. Generate a fresh random topic (`python -c "import secrets;
   print('weatherbot-' + secrets.token_urlsafe(18))"`).
2. Subscribe to the new topic in the `ntfy` mobile app and unsubscribe from the
   old one.
3. Update `WEATHERBOT_NTFY_TOPIC` in the Windows Environment Variables dialog.
4. Restart `\Weatherbot\serve` and run `weatherbot notify test` to confirm the
   phone receives the test on the new topic.

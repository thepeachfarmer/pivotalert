# PivotAlert Development Journal

## 2026-06-08 - Power Company Sender Switch

### What happened
Missed a real load control event today. Three Beat the Peak / Santee Cooper alerts hit the inbox between 17:30 and 19:00 but never fired SMS because the sender allowlist only knew about the old CEPCI address. By the time it was noticed, control had already started.

### Diagnosis
Looked at recent emails on the dashboard. The new sender is `EnergySmartSC <energysmartsc@beatthepeak.com>`. Santee Cooper / Central Electric switched their member notifications from `rapidnotifications.com` to the Beat the Peak platform. The emails describe the same kind of event — "Central has initiated a load control event for all participating resources within the Santee Cooper Balancing Authority" — but the new subjects are suffixed with " - Santee Cooper" and the bodies are heavily inline-styled HTML.

### Fix
1. Added `energysmartsc@beatthepeak.com` to `ALERT_SENDERS` in `app/main.py`. Kept the old CEPCI address in the list in case any tail-end messages still come from it.
2. Built `scripts/replay_recent.py` — pulls the last N hours of emails from the SQLite DB, runs them through the current sender allowlist + classifier, and reports what would have fired SMS. No rebuild needed — streamed over stdin via `curl raw.github | docker exec -i pivotalert python3`. Used to confirm the patch worked before waiting for the next live event.
3. Built `scripts/fire_recent.py` — same shape, but actually sends SMS for the missed alerts (gated by `CONFIRM_SEND=YES`). Respects cooldown so a back-to-back "in 15 minutes" + "now" only produces one text. Used it to retroactively alert the chain after the fix went live.

### Replay verdict
Two of three classified correctly: `Beginning Control in 15 Minutes - Santee Cooper` and `Beginning Control Now - Santee Cooper` both matched the existing `"beginning control"` subject pattern → critical → SMS. The third, `Control This Evening - Santee Cooper` (sent ~90 min before the event), didn't match any classifier branch and was silent. That early-evening heads-up wording is new to Beat the Peak; CEPCI never sent anything like it. Left as a known gap to patch next time we see one come in, by adding `"control this evening" / "control today" / "control tonight"` to the Control Possible branch.

### Lessons
- **Sender allowlist is the single most fragile config in this app.** When the upstream provider changes, every message is silently dropped — no error, no log, no SMS, the email just sits in the archive marked `alert_triggered = 0`. Worth considering whether to surface an alert when an email from a brand-new sender shows up that contains classifier-keyword content. Or move the allowlist into the database so the dashboard can edit it without a redeploy.
- **Streaming ops scripts over stdin beats baking them into the image.** Both diagnostic scripts work via `curl raw.github | docker exec -i pivotalert python3`. No rebuild, no redeploy, instant iteration during an active event. Pattern worth reusing for any future one-off operational tooling.

---

## 2026-04-16 - Classifier Rewrite Based on Real Event Data

### New Sample Emails
Got 15 real emails from an actual load control event on Apr 15. This was a full cycle: no control (Apr 13-14), control possible, taking control, full control with rampouts, then releasing control. Much richer than the original 5 samples.

### New Message Types Discovered
- **"Releasing Control Now."** - New subject type, didn't exist in original samples
- **"Control Is Possible. Next message in 15 minutes."** - Warning in subject line
- **Ramp-out messages** - "Beginning rampout of water heaters/air conditioners" - transitional, not actionable for pivot operators
- **Multi-provider format** - Santee Cooper / Duke sections in body with separate statuses
- **"Maintaining control"** - Status updates during active control
- **"Taking control of line regulators"** - Grid-level, not interruptibles

### Classifier Rewrite
Simplified from a generic 3-level system to 4 specific actionable categories matching what the farm actually needs:

1. **No Control** - Good news, no action needed. Now sends SMS (was previously silent).
2. **Control Possible** - Heads up, be ready.
3. **Taking Control** - Drop everything, turn pivots off.
4. **Releasing Control** - All clear, pivots can go back on.

Everything else (rampouts, maintaining control, line regulators) gets stored but doesn't blow up anyone's phone.

### SMS Cooldown
Added a 15-minute cooldown per alert level. The power company sends updates every 15-60 minutes during an event, and getting 13 texts in one afternoon is too many. Now if we've already sent a "control possible" SMS, the next one within 15 min gets skipped. Configurable via `SMS_COOLDOWN_MINUTES` env var.

### Custom Test SMS
Added ability to send a custom test message from the dashboard, alongside the default fun test message. Useful for verifying Twilio is working without sending a canned message.

### Database Migration Bug
First deploy after the classifier rewrite hit a 500 error — `sqlite3.OperationalError: no such column: original_sender`. The `original_sender` column was added to the schema in the previous commit, but `CREATE TABLE IF NOT EXISTS` doesn't add new columns to an existing table. Fixed by adding an `ALTER TABLE` migration at startup that adds the column if missing and silently skips if it already exists. Lesson: always account for existing databases when adding columns.

---

## 2026-04-15 - Project Kickoff

### Problem
The power company (Central Electric, via Pee Dee Electric cooperative) sends email alerts when load control events are happening. These emails go to `mpdloadcontrolfrontier@mpd.coop` and get forwarded to `smcleod@macspride.com`. When a control event is active, irrigation systems need to be shut down to avoid peak charges. The emails are easy to miss, and multiple people need to know about them.

### Solution
Built PivotAlert -- a small server that monitors a dedicated Gmail inbox for these emails and sends SMS alerts to a list of people via Twilio.

### Email Patterns Discovered
Analyzed 5 sample `.eml` files from the power company. All come from `cepci@rapidnotifications.com`. The key message types:

| Subject | Body Content | Action |
|---------|-------------|--------|
| "Beginning control now" | "Central is taking control of interruptibles" | CRITICAL - SMS alert |
| "LM Logger Message" | "implement control now" + interruptibles, water heaters, etc. | CRITICAL - SMS alert |
| "LM Logger Message" | "Control is possible" | WARNING - SMS alert |
| "LM Logger Message" | "Taking control of line regulators" | WARNING - SMS alert |
| "No Control" | "will not be required" | INFO - no SMS |

### Deployment
- Deployed as a Docker container on `dockerhost3` via Portainer
- Image built by GitHub Actions and pushed to `ghcr.io/thepeachfarmer/pivotalert:latest`
- Web UI accessible on port 8080

### Twilio Issues
- Initial test SMS attempts failed with error 30034 (A2P 10DLC - Unregistered Number). US carriers now require 10DLC registration for business SMS from local numbers.
- Tried buying a toll-free number as a workaround -- failed with error 30032 (toll-free number not verified).
- Deleted the toll-free number to avoid the monthly charge.
- Solution: Register as Sole Proprietor in Twilio Trust Hub, create a campaign, and link the Grain Dryer number (`+18438656887`). Brand was already registered. Campaign registration in progress.

### Email Forwarding
Set up Gmail filter on `smcleod@macspride.com` to forward emails from `cepci@rapidnotifications.com` to the dedicated PivotAlert inbox (`alertpivot0@gmail.com`). Updated the app to read `X-Original-Sender` headers so forwarded emails still get classified correctly.

### Architecture Decisions
- **SQLite over Postgres**: Zero-config, single file, persisted via Docker volume. More than enough for this workload.
- **Store all emails**: Initially only processed emails from the known sender. Changed to store every email that hits the inbox so we can review and add new classification rules later without losing history.
- **Web UI for credentials**: Rather than environment variables, credentials are entered through the web UI and stored in the database. Easier for the user to configure without SSH access.
- **All-in-one container**: Email poller runs as a background task inside the FastAPI process. No need for a separate worker or message queue at this scale.

# Changelog

## 2026-06-12

### Operational
- Redeployed the live container to pick up `b7d0edc` (2026-06-11). The image had been built and pushed to GHCR the previous evening, but the running container — created 2026-06-08 15:43:10 EDT, two minutes after the sender allowlist fix — had never pulled the newer `:latest`. Portainer does not auto-pull on `restart: unless-stopped`; the registry refresh only happens on a manual "Update the stack" with **Pull image** enabled. Surfaced when a 1:30 PM "Control This Evening - Santee Cooper" email went silent today, exactly as it would have under the pre-fix classifier. No code changes — the Control Scheduled branch shipped on 2026-06-11.

### Known Gap
- The Build-and-Push workflow does not trigger a Portainer redeploy. Pushes to `main` build a new `:latest` in GHCR, but the live container keeps running whichever image it was created with until someone manually redeploys with Pull image enabled. Next step: add a Portainer stack-webhook `curl` at the end of `.github/workflows/docker-publish.yml` so every successful push refreshes the live container automatically.

## 2026-06-11

### Added
- New **Control Scheduled** classifier branch — fires on Beat the Peak's hours-ahead "Control This Evening / Tonight / Today / Tomorrow" subjects and on bodies containing `"load control will be initiated"` / `"control will be initiated"`. SMS: `⚠️ HEADS UP: Santee Cooper has announced a load control event {timeframe}. It IS coming — prepare to shut down pivots.` Uses its own `level="scheduled"` so the cooldown bucket is separate from `critical` — i.e. firing the heads-up does NOT suppress the later "Beginning Control" critical SMS.
- `.badge-scheduled` CSS rule (orange) for the new alert level so dashboard badges render styled.
- Two new regression samples in `inbox/`: `Control This Evening - Santee Cooper.eml` and `No Control This Evening or Tomorrow Morning - Santee Cooper.eml` (both from the 2026-06-11 event).

### Changed
- **No Control** SMS no longer says "No control **today**! Good news." It now mirrors the source subject's timeframe (e.g. "no load control expected this evening or tomorrow morning") and adds the caveat "(They can still change their mind.)". Triggered by the 2026-06-11 false-positive where the 9:53 AM email said "this evening or tomorrow morning" — but the classifier promised "today" and control was called at 3 PM. Wording now matches what the source actually said.
- Branch order: **No Control is now evaluated before Control Scheduled**, because a subject like "No Control This Evening or Tomorrow Morning" contains both `"no control"` and `"this evening"`. No Control must win.

### Fixed
- Closes the "known gap" from the 2026-06-08 entry — the Beat the Peak hours-ahead heads-up message now triggers an SMS warning instead of being silently archived.

## 2026-06-08

### Added
- `energysmartsc@beatthepeak.com` added to the alert sender allowlist. Santee Cooper / Central Electric switched their member notifications from `cepci@rapidnotifications.com` to the Beat the Peak platform. The old address is kept in the list in case any tail-end messages still come from it.
- `scripts/replay_recent.py` — dry-run script that re-runs the current sender allowlist + classifier against emails from the last N hours and reports what WOULD have fired SMS (sends nothing). Useful for verifying a code change without waiting for the next live event. Streams over stdin via `docker exec`, no rebuild required.
- `scripts/fire_recent.py` — retroactive SMS fire for emails the live system missed. Safe by default (dry-run); set `CONFIRM_SEND=YES` to actually send. Respects existing cooldown so back-to-back duplicates of the same level produce one SMS, not two.
- `inbox/` directory with the new Beat the Peak format `.eml` samples (`Beginning Control Now - Santee Cooper`, `Beginning Control in 15 Minutes - Santee Cooper`) for regression reference.

### Known Gap
- "Control This Evening - Santee Cooper" (Beat the Peak's hours-ahead heads-up — wording new to this provider, never sent by CEPCI) does not match any classifier branch. To pick it up next time, add `"control this evening"`, `"control today"`, `"control tonight"` to the Control Possible subject patterns in `app/classifier.py`.

## 2026-04-16 (v2)

### Added
- 15 new sample emails from a real load control event day (Apr 13-15) in `new_sample_emails/`
- SMS cooldown system: won't send duplicate SMS of the same alert level within 15 minutes (configurable via `SMS_COOLDOWN_MINUTES` env var)
- Custom test SMS: text input on dashboard to send any message to all members
- Fun default test SMS message with emojis
- Database migration for `original_sender` column on existing deployments

### Changed
- Rewrote email classifier with 4 actionable categories and custom SMS messages:
  - **No Control**: "No control today! Good news — no load control expected."
  - **Control Possible**: "Control is possible today. Stay vigilant and be ready to shut down pivots."
  - **Taking Control**: "LOAD CONTROL ACTIVE! Turn pivots OFF now!"
  - **Releasing Control**: "Control is being released. You can turn pivots back on."
- Intermediate messages (rampout, maintaining control, line regulators) are now stored but do not trigger SMS
- "No Control" messages now send an SMS (previously silent)
- "Releasing Control" is now a recognized category (new subject pattern from real emails)
- Test SMS UI redesigned with default and custom message options

## 2026-04-16

### Added
- Original sender extraction from forwarded email headers (`X-Original-Sender`, `X-Original-From`, `Reply-To`)
- Forwarded emails from `smcleod@macspride.com` are now properly classified using the original sender

### Changed
- Alert classification now checks both `From` and original sender headers

## 2026-04-15

### Added
- Full email archive: every email that hits the inbox is saved to the `emails` table with complete body, headers, sender, and message ID
- "All Emails" section on the dashboard showing every received email
- Email detail page with full body text, HTML, and raw headers
- Deduplication via `message_id` unique constraint

### Changed
- IMAP fetch now retrieves ALL unread emails, not just from the known sender
- Alert classification only runs on emails from `cepci@rapidnotifications.com` or `smcleod@macspride.com`; all others are stored but not processed for alerts

## 2026-04-15 (Initial Release)

### Added
- FastAPI web application with dark-themed dashboard
- Gmail IMAP polling (configurable interval, default 60s)
- Email classification engine with three alert levels: critical, warning, info
- Twilio SMS notifications to all registered members
- Web UI for managing members (add/remove phone numbers)
- Web UI for configuring Gmail IMAP and Twilio credentials
- Test SMS button on dashboard
- Alert history table showing all processed alerts
- Docker deployment with GitHub Actions CI/CD to ghcr.io
- docker-compose.yml for Portainer deployment
- SQLite database with persistent Docker volume
- Sample .eml files from power company for reference

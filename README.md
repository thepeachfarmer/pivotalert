# PivotAlert

Email-to-SMS alert system for power company load control notifications. Monitors a Gmail inbox for emails from the power cooperative's notification system and sends SMS alerts to registered members via Twilio when a load control event is happening.

## Why

The power company (via Central Electric / Pee Dee Electric cooperative) sends email notifications when load control events are taking place. When control is active, irrigation systems and other interruptible loads should be shut down to save on the power bill. This app watches for those emails and texts the right people so they can act quickly.

## How It Works

1. **Email Polling** - Checks a Gmail inbox via IMAP every 60 seconds for new emails
2. **Classification** - Parses the email subject/body and maps to 5 actionable categories. Listed in evaluation order:
   - **Taking Control** *(critical)* — "Beginning control now", "implement control now", "taking control of interruptibles" → SMS: 🚨 LOAD CONTROL ACTIVE! Turn pivots OFF now!
   - **Releasing Control** *(info)* — "Releasing Control Now", "releasing control of interruptibles" → SMS: 🟢 Control is being released. You can turn pivots back on.
   - **No Control** *(info)* — Subject begins with "No Control" / body says "will not be required" → SMS mirrors the source's stated timeframe, e.g. `✅ Santee Cooper: no load control expected this evening or tomorrow morning. (They can still change their mind.)` Falls back to "no load control expected" if the subject carries no timeframe. *Caveat is load-bearing — the 2026-06-11 event proved the source can flip mid-day.*
   - **Control Scheduled** *(scheduled)* — Subject contains "control this evening / tonight / today / tomorrow" OR body contains "control will be initiated" → SMS: ⚠️ HEADS UP: Santee Cooper has announced a load control event {timeframe}. It IS coming — prepare to shut down pivots. *Firm commitment, hours of lead time. Distinct from Control Possible (which is hedged).*
   - **Control Possible** *(warning)* — "Control is possible" → SMS: ⚠️ Control is possible today. Stay vigilant and be ready to shut down pivots.
   - Intermediate messages (rampouts, maintaining control, line regulators) are stored but do not trigger SMS.

   Branch order matters: **No Control is evaluated before Control Scheduled**, because subjects like "No Control This Evening or Tomorrow Morning" contain both `"no control"` and `"this evening"`.
3. **SMS Cooldown** - Won't send duplicate SMS of the same alert level within 15 minutes (configurable via `SMS_COOLDOWN_MINUTES`). Each level has its own cooldown bucket — firing a `scheduled` heads-up does NOT suppress the later `critical` "Beginning Control" SMS.
4. **SMS Alerts** - Sends text messages to all registered members via Twilio
5. **Email Archive** - Every email that hits the inbox is saved to the database for future review, regardless of whether it triggered an alert

## Email Sources

- **Direct**: `energysmartsc@beatthepeak.com` (Santee Cooper / Central Electric via the Beat the Peak platform — current notification system as of 2026-06-08)
- **Legacy direct**: `cepci@rapidnotifications.com` (the prior notification system — kept in the allowlist for any tail-end messages)
- **Forwarded**: Emails forwarded from `smcleod@macspride.com` via Gmail filter. The app reads `X-Original-Sender` headers to identify the real sender on forwarded messages.

The sender allowlist lives in `ALERT_SENDERS` at the top of `app/main.py`. To add a new sender, edit that list, commit, push, and redeploy — the rest of the pipeline is provider-agnostic.

## Deployment

### Prerequisites

- A Gmail account with IMAP enabled and an App Password generated
- A Twilio account with a registered phone number (10DLC or toll-free, must be verified)
- Docker host with Portainer (or plain Docker)

### Deploy via Portainer

Use the stack with this `docker-compose.yml`:

```yaml
services:
  pivotalert:
    image: ghcr.io/thepeachfarmer/pivotalert:latest
    container_name: pivotalert
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - pivotalert_data:/data
    environment:
      - POLL_INTERVAL=60
      - SMS_COOLDOWN_MINUTES=15

volumes:
  pivotalert_data:
```

### Refreshing the image after a code change

CI (`.github/workflows/docker-publish.yml`) builds `ghcr.io/thepeachfarmer/pivotalert:latest` on every push to `main`. **Portainer does not automatically pull the new image.** The container keeps running whichever image it was created with — `restart: unless-stopped` restarts the same image, it does not reach back to the registry.

To pick up a new commit:

1. In Portainer → Stacks → `pivotalert`, click **Update the stack**.
2. Enable the **Pull image** toggle.
3. Click "Update".

To confirm what's live, compare the container's "Created" timestamp to `git log` — any commit at or before that moment is live, anything after is not.

> ⚠️ Easy to forget. The 2026-06-12 journal entry documents a missed-alert day caused by a classifier fix that had been merged and built but never pulled into the running container.

### Configuration

All configuration is done through the web UI at `http://<host>:8080`:

- **Gmail IMAP** - Host, email address, and app password
- **Twilio SMS** - Account SID, auth token, and sending phone number
- **Members** - Add/remove phone numbers that receive alerts

### Gmail Forwarding Setup

To forward power company emails to the PivotAlert inbox:

1. In the source Gmail account, go to Settings > Forwarding and POP/IMAP
2. Add the PivotAlert Gmail address as a forwarding destination and confirm
3. Go to Filters and Blocked Addresses > Create a new filter
4. Set From: `cepci@rapidnotifications.com`
5. Create filter > Forward it to the PivotAlert Gmail address

## Tech Stack

- Python 3.12 + FastAPI
- SQLite (persisted via Docker volume, auto-migrates on startup)
- imaplib (stdlib) for IMAP
- Twilio SDK for SMS
- Jinja2 templates for the web UI
- GitHub Actions for CI/CD (builds Docker image to ghcr.io)

## Project Structure

```
pivotalert/
├── app/
│   ├── main.py              # FastAPI app, routes, email poll loop
│   ├── email_checker.py     # IMAP connection and email fetching
│   ├── classifier.py        # Email classification logic
│   ├── notifier.py          # Twilio SMS sending
│   ├── database.py          # SQLite schema and queries
│   ├── templates/
│   │   ├── index.html       # Dashboard
│   │   └── email_detail.html # Full email viewer
│   └── static/
│       └── style.css
├── Dockerfile
├── docker-compose.yml
├── .github/workflows/
│   └── docker-publish.yml
├── sample_emails/           # Original .eml files for reference
├── new_sample_emails/       # Real event emails from Apr 13-15 (CEPCI format)
├── inbox/                   # New Beat the Peak / Santee Cooper format samples (Jun 2026)
├── scripts/
│   ├── replay_recent.py     # Dry-run replay of last N hours against current classifier
│   └── fire_recent.py       # Retroactive SMS fire for missed alerts (CONFIRM_SEND=YES to send)
├── CHANGELOG.md
├── JOURNAL.md
└── README.md
```

## Operational Scripts

Both scripts in `scripts/` stream over stdin via `docker exec`, so no rebuild or redeploy is needed to use a newly-committed version.

### Replay recent emails (dry run, no SMS)

Re-runs the current sender allowlist + classifier against emails from the last N hours and reports what would have fired SMS. Use this to verify a change without waiting for the next live event.

```sh
curl -s https://raw.githubusercontent.com/thepeachfarmer/pivotalert/main/scripts/replay_recent.py \
  | docker exec -i pivotalert python3
```

Change the window with `-e REPLAY_HOURS=24`.

### Fire missed alerts (sends real SMS)

Retroactively fires SMS for emails the live system missed (e.g. after fixing a sender allowlist). Safe by default — dry-runs unless `CONFIRM_SEND=YES`. Respects cooldown so duplicates of the same level are suppressed.

```sh
# Dry run first
curl -s https://raw.githubusercontent.com/thepeachfarmer/pivotalert/main/scripts/fire_recent.py \
  | docker exec -i pivotalert python3

# Actually send
curl -s https://raw.githubusercontent.com/thepeachfarmer/pivotalert/main/scripts/fire_recent.py \
  | docker exec -i -e CONFIRM_SEND=YES pivotalert python3
```

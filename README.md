# PivotAlert

Email-to-SMS alert system for power company load control notifications. Monitors a Gmail inbox for emails from the power cooperative's notification system and sends SMS alerts to registered members via Twilio when a load control event is happening.

## Why

The power company (via Central Electric / Pee Dee Electric cooperative) sends email notifications when load control events are taking place. When control is active, irrigation systems and other interruptible loads should be shut down to save on the power bill. This app watches for those emails and texts the right people so they can act quickly.

## How It Works

1. **Email Polling** - Checks a Gmail inbox via IMAP every 60 seconds for new emails
2. **Classification** - Parses the email subject/body and maps to 4 actionable categories:
   - **Taking Control** - "Beginning control now", "implement control now", "taking control of interruptibles" → SMS: 🚨 LOAD CONTROL ACTIVE! Turn pivots OFF now!
   - **Releasing Control** - "Releasing Control Now", "releasing control of interruptibles" → SMS: 🟢 Control is being released. You can turn pivots back on.
   - **No Control** - "No control" / "will not be required" → SMS: ✅ No control today! Good news.
   - **Control Possible** - "Control is possible" → SMS: ⚠️ Control is possible today. Stay vigilant.
   - Intermediate messages (rampouts, maintaining control, line regulators) are stored but do not trigger SMS
3. **SMS Cooldown** - Won't send duplicate SMS of the same alert level within 15 minutes (configurable via `SMS_COOLDOWN_MINUTES`)
4. **SMS Alerts** - Sends text messages to all registered members via Twilio
5. **Email Archive** - Every email that hits the inbox is saved to the database for future review, regardless of whether it triggered an alert

## Email Sources

- **Direct**: `cepci@rapidnotifications.com` (the power company notification system)
- **Forwarded**: Emails forwarded from `smcleod@macspride.com` via Gmail filter. The app reads `X-Original-Sender` headers to identify the real sender on forwarded messages.

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
├── new_sample_emails/       # Real event emails from Apr 13-15
├── CHANGELOG.md
├── JOURNAL.md
└── README.md
```

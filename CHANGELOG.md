# Changelog

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

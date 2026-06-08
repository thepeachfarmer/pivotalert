"""Retroactively fire SMS for recent emails the live system missed.

Safe by default: runs as a dry run unless CONFIRM_SEND=YES is set.

Pulls emails from the last N hours, runs them through the current sender
allowlist + classifier, and (if confirmed) actually sends each SMS via the
configured Twilio account + logs the alert to history. Respects cooldown
so duplicates of the same level are suppressed.

Usage:
    # dry run (safe — prints what it would do, sends nothing)
    docker exec -i pivotalert python3 < scripts/fire_recent.py

    # actually send
    docker exec -i -e CONFIRM_SEND=YES pivotalert python3 < scripts/fire_recent.py
"""
import asyncio
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")
from app.classifier import classify_email  # noqa: E402
from app.database import add_alert, get_last_alert_time, mark_email_processed  # noqa: E402
from app.main import ALERT_SENDERS, SMS_COOLDOWN_MINUTES  # noqa: E402
from app.notifier import send_sms_to_all  # noqa: E402

HOURS = int(os.environ.get("REPLAY_HOURS", "8"))
DB_PATH = os.environ.get("PIVOTALERT_DB", "/data/pivotalert.db")
CONFIRM = os.environ.get("CONFIRM_SEND", "").upper() == "YES"


async def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, message_id, sender, original_sender, subject,
               body_text, body_html, alert_triggered, created_at
        FROM emails
        WHERE created_at >= datetime('now', ?)
        ORDER BY created_at ASC
        """,
        (f"-{HOURS} hours",),
    ).fetchall()
    conn.close()

    mode = "LIVE — sending SMS" if CONFIRM else "DRY RUN — set CONFIRM_SEND=YES to actually send"
    print(f"\n=== Fire recent: {len(rows)} emails in last {HOURS} hours ===")
    print(f"Mode: {mode}\n")

    fired = 0
    suppressed = 0
    skipped = 0

    for r in rows:
        s = (r["sender"] or "").lower()
        o = (r["original_sender"] or "").lower()
        matched = any(x in s or x in o for x in ALERT_SENDERS)
        body = r["body_html"] or r["body_text"] or ""
        res = classify_email(r["subject"] or "", body)

        if not matched or not res.is_alert:
            skipped += 1
            print(f"  [skip] {r['created_at']}  {r['subject']!r}")
            continue

        last_time_str = await get_last_alert_time(res.level)
        in_cooldown = False
        if last_time_str:
            try:
                last_time = datetime.fromisoformat(last_time_str).replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - last_time < timedelta(minutes=SMS_COOLDOWN_MINUTES):
                    in_cooldown = True
            except ValueError:
                pass

        if in_cooldown:
            suppressed += 1
            print(f"  [cooldown] {r['created_at']}  level={res.level}  {r['subject']!r}")
            continue

        print(f"  [FIRE] {r['created_at']}  level={res.level}  {r['subject']!r}")
        print(f"         message = {res.sms_message!r}")

        if CONFIRM:
            sent_to = await send_sms_to_all(res.sms_message)
            await add_alert(
                subject=f"[retroactive] {r['subject']}",
                body_snippet=(body[:200] if body else ""),
                alert_level=res.level,
                sms_sent=len(sent_to),
                recipients=", ".join(sent_to),
            )
            await mark_email_processed(r["message_id"], alert_triggered=True)
            print(f"         -> sent to {len(sent_to)} members: {sent_to}")
        fired += 1

    print(
        f"\n=== Summary: fired={fired}  cooldown-suppressed={suppressed}  "
        f"skipped={skipped}  (sent={'yes' if CONFIRM else 'NO — dry run'}) ==="
    )


asyncio.run(main())

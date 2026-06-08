"""Replay recent emails through the current sender allowlist + classifier.

Dry-run only — does NOT send SMS. Reports what WOULD happen if each email
in the last N hours were processed against the currently-deployed code.

Run inside the container:
    docker exec -i pivotalert python3 < scripts/replay_recent.py

Or remotely from a workstation:
    ssh spencer@10.0.10.198 'docker exec -i pivotalert python3' < scripts/replay_recent.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "/app")
from app.classifier import classify_email  # noqa: E402
from app.main import ALERT_SENDERS  # noqa: E402

HOURS = int(os.environ.get("REPLAY_HOURS", "8"))
DB_PATH = os.environ.get("PIVOTALERT_DB", "/data/pivotalert.db")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT id, sender, original_sender, subject, body_text, body_html,
           alert_triggered, created_at
    FROM emails
    WHERE created_at >= datetime('now', ?)
    ORDER BY created_at DESC
    """,
    (f"-{HOURS} hours",),
).fetchall()

print(f"\n=== Replay: {len(rows)} emails in last {HOURS} hours ===")
print(f"Sender allowlist: {ALERT_SENDERS}\n")

would_fire = 0
for r in rows:
    s = (r["sender"] or "").lower()
    o = (r["original_sender"] or "").lower()
    matched = any(x in s or x in o for x in ALERT_SENDERS)
    body = r["body_html"] or r["body_text"] or ""
    res = classify_email(r["subject"] or "", body)
    would_sms = matched and res.is_alert
    if would_sms:
        would_fire += 1

    if would_sms:
        tag = "[OK -> SMS]"
    elif not matched:
        tag = "[skip-sender]"
    else:
        tag = f"[no-match:{res.level}]"

    print(f"{r['created_at']}  {tag}")
    print(f"   from = {r['sender']!r}")
    print(f"   orig = {r['original_sender']!r}")
    print(f"   subj = {r['subject']!r}")
    print(f"   live alert_triggered = {bool(r['alert_triggered'])}")
    print()

print(f"=== Summary: {would_fire}/{len(rows)} would now fire SMS ===")

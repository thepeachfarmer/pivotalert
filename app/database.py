import aiosqlite
import os

DB_PATH = os.environ.get("PIVOTALERT_DB", "/data/pivotalert.db")


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT,
                body_snippet TEXT,
                alert_level TEXT,
                sms_sent INTEGER DEFAULT 0,
                recipients TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                sender TEXT,
                original_sender TEXT,
                to_addr TEXT,
                subject TEXT,
                body_text TEXT,
                body_html TEXT,
                date TEXT,
                headers TEXT,
                processed INTEGER DEFAULT 0,
                alert_triggered INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Migrate: add original_sender column if DB was created before it existed
        try:
            await db.execute("ALTER TABLE emails ADD COLUMN original_sender TEXT DEFAULT ''")
        except Exception:
            pass  # column already exists
        await db.commit()
    finally:
        await db.close()


async def get_setting(key: str) -> str | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row["value"] if row else None
    finally:
        await db.close()


async def set_setting(key: str, value: str):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()
    finally:
        await db.close()


async def get_all_settings() -> dict[str, str]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}
    finally:
        await db.close()


async def get_members() -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id, name, phone, created_at FROM members ORDER BY name")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def add_member(name: str, phone: str):
    db = await get_db()
    try:
        await db.execute("INSERT INTO members (name, phone) VALUES (?, ?)", (name, phone))
        await db.commit()
    finally:
        await db.close()


async def delete_member(member_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM members WHERE id = ?", (member_id,))
        await db.commit()
    finally:
        await db.close()


async def add_alert(subject: str, body_snippet: str, alert_level: str, sms_sent: int, recipients: str):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO alert_history (subject, body_snippet, alert_level, sms_sent, recipients) "
            "VALUES (?, ?, ?, ?, ?)",
            (subject, body_snippet, alert_level, sms_sent, recipients),
        )
        await db.commit()
    finally:
        await db.close()


async def get_last_alert_time(alert_level: str) -> str | None:
    """Return the created_at timestamp of the most recent alert with this level that sent SMS."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT created_at FROM alert_history "
            "WHERE alert_level = ? AND sms_sent > 0 "
            "ORDER BY created_at DESC LIMIT 1",
            (alert_level,),
        )
        row = await cursor.fetchone()
        return row["created_at"] if row else None
    finally:
        await db.close()


async def get_alerts(limit: int = 50) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM alert_history ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def save_email(
    message_id: str,
    sender: str,
    original_sender: str,
    to_addr: str,
    subject: str,
    body_text: str,
    body_html: str,
    date: str,
    headers: str,
) -> bool:
    """Save an email to the database. Returns True if new, False if duplicate."""
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO emails "
            "(message_id, sender, original_sender, to_addr, subject, body_text, body_html, date, headers) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, sender, original_sender, to_addr, subject, body_text, body_html, date, headers),
        )
        await db.commit()
        cursor = await db.execute("SELECT changes()")
        row = await cursor.fetchone()
        return row[0] > 0
    finally:
        await db.close()


async def mark_email_processed(message_id: str, alert_triggered: bool):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE emails SET processed = 1, alert_triggered = ? WHERE message_id = ?",
            (1 if alert_triggered else 0, message_id),
        )
        await db.commit()
    finally:
        await db.close()


async def get_emails(limit: int = 100) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, message_id, sender, original_sender, to_addr, subject, date, processed, "
            "alert_triggered, created_at FROM emails ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_email_by_id(email_id: int) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()

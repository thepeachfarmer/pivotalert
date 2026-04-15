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
        """)
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

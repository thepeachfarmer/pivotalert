import asyncio
import email
import email.policy
import imaplib
import logging
from email.message import EmailMessage

from app.database import get_setting

logger = logging.getLogger("pivotalert.email")

EXPECTED_SENDER = "cepci@rapidnotifications.com"


async def fetch_new_emails() -> list[dict]:
    """Connect to Gmail via IMAP and fetch unread emails from the expected sender."""
    imap_host = await get_setting("imap_host") or "imap.gmail.com"
    imap_user = await get_setting("imap_user")
    imap_pass = await get_setting("imap_pass")

    if not imap_user or not imap_pass:
        logger.warning("IMAP credentials not configured, skipping email check")
        return []

    def _fetch():
        results = []
        try:
            mail = imaplib.IMAP4_SSL(imap_host)
            mail.login(imap_user, imap_pass)
            mail.select("INBOX")

            # Search for unread emails from the expected sender
            status, message_ids = mail.search(None, "UNSEEN", f'FROM "{EXPECTED_SENDER}"')
            if status != "OK" or not message_ids[0]:
                mail.logout()
                return results

            for msg_id in message_ids[0].split():
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue

                raw = msg_data[0][1]
                msg: EmailMessage = email.message_from_bytes(raw, policy=email.policy.default)

                subject = msg.get("Subject", "")
                body = _extract_body(msg)

                results.append({"subject": subject, "body": body})

                # Mark as seen (already done by fetching, but explicit)
                mail.store(msg_id, "+FLAGS", "\\Seen")

            mail.logout()
        except imaplib.IMAP4.error as e:
            logger.error("IMAP error: %s", e)
        except Exception as e:
            logger.error("Email fetch error: %s", e)

        return results

    return await asyncio.to_thread(_fetch)


def _extract_body(msg: EmailMessage) -> str:
    """Extract the text body from an email message."""
    if msg.is_multipart():
        # Prefer HTML, fall back to plain text
        html_part = None
        text_part = None
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html" and html_part is None:
                html_part = part.get_content()
            elif ct == "text/plain" and text_part is None:
                text_part = part.get_content()

        return html_part or text_part or ""

    return msg.get_content() if msg.get_content_type().startswith("text/") else ""

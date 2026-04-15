import asyncio
import email
import email.policy
import imaplib
import logging
from email.message import EmailMessage

from app.database import get_setting

logger = logging.getLogger("pivotalert.email")


async def fetch_new_emails() -> list[dict]:
    """Connect to Gmail via IMAP and fetch ALL unread emails."""
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

            status, message_ids = mail.search(None, "UNSEEN")
            if status != "OK" or not message_ids[0]:
                mail.logout()
                return results

            for msg_id in message_ids[0].split():
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue

                raw = msg_data[0][1]
                msg: EmailMessage = email.message_from_bytes(raw, policy=email.policy.default)

                sender = msg.get("From", "")
                to_addr = msg.get("To", "")
                subject = msg.get("Subject", "")
                message_id = msg.get("Message-ID", "")
                date = msg.get("Date", "")
                body_text, body_html = _extract_bodies(msg)

                # Resolve original sender from forwarding headers
                original_sender = (
                    msg.get("X-Original-Sender")
                    or msg.get("X-Original-From")
                    or msg.get("Reply-To")
                    or ""
                )

                # Collect all headers as a string for storage
                headers = str(msg)

                results.append({
                    "message_id": message_id,
                    "sender": sender,
                    "original_sender": original_sender,
                    "to_addr": to_addr,
                    "subject": subject,
                    "date": date,
                    "body_text": body_text,
                    "body_html": body_html,
                    "body": body_html or body_text,
                    "headers": headers,
                })

                mail.store(msg_id, "+FLAGS", "\\Seen")

            mail.logout()
        except imaplib.IMAP4.error as e:
            logger.error("IMAP error: %s", e)
        except Exception as e:
            logger.error("Email fetch error: %s", e)

        return results

    return await asyncio.to_thread(_fetch)


def _extract_bodies(msg: EmailMessage) -> tuple[str, str]:
    """Extract both plain text and HTML bodies from an email message."""
    if msg.is_multipart():
        html_part = None
        text_part = None
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html" and html_part is None:
                html_part = part.get_content()
            elif ct == "text/plain" and text_part is None:
                text_part = part.get_content()
        return (text_part or "", html_part or "")

    content = msg.get_content() if msg.get_content_type().startswith("text/") else ""
    if msg.get_content_type() == "text/html":
        return ("", content)
    return (content, "")

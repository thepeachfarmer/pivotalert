import asyncio
import logging

from twilio.rest import Client

from app.database import get_setting, get_members

logger = logging.getLogger("pivotalert.notifier")


async def send_sms_to_all(message: str) -> list[str]:
    """Send an SMS to all registered members. Returns list of recipient names."""
    account_sid = await get_setting("twilio_sid")
    auth_token = await get_setting("twilio_token")
    from_number = await get_setting("twilio_from")

    if not all([account_sid, auth_token, from_number]):
        logger.warning("Twilio credentials not configured, skipping SMS")
        return []

    members = await get_members()
    if not members:
        logger.warning("No members registered, skipping SMS")
        return []

    # Truncate SMS to 1600 chars (Twilio limit)
    if len(message) > 1600:
        message = message[:1597] + "..."

    def _send():
        client = Client(account_sid, auth_token)
        sent_to = []
        for member in members:
            try:
                client.messages.create(
                    body=message,
                    from_=from_number,
                    to=member["phone"],
                )
                sent_to.append(member["name"])
                logger.info("SMS sent to %s (%s)", member["name"], member["phone"])
            except Exception as e:
                logger.error("Failed to send SMS to %s: %s", member["name"], e)
        return sent_to

    return await asyncio.to_thread(_send)

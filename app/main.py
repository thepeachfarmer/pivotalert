import asyncio
import logging
import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.classifier import classify_email
from app.database import (
    add_alert,
    add_member,
    delete_member,
    get_alerts,
    get_all_settings,
    get_email_by_id,
    get_emails,
    get_members,
    init_db,
    mark_email_processed,
    save_email,
    set_setting,
)
from app.email_checker import fetch_new_emails
from app.notifier import send_sms_to_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("pivotalert")

app = FastAPI(title="PivotAlert")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))

# Senders whose emails get run through the alert classifier
ALERT_SENDERS = [
    "cepci@rapidnotifications.com",
    "smcleod@macspride.com",
]


# ---------------------------------------------------------------------------
# Background email poller
# ---------------------------------------------------------------------------
async def email_poll_loop():
    """Continuously poll for new emails and process them."""
    while True:
        try:
            emails = await fetch_new_emails()
            for em in emails:
                # Save every email to the database
                is_new = await save_email(
                    message_id=em["message_id"],
                    sender=em["sender"],
                    to_addr=em["to_addr"],
                    subject=em["subject"],
                    body_text=em["body_text"],
                    body_html=em["body_html"],
                    date=em["date"],
                    headers=em["headers"],
                )

                if not is_new:
                    continue

                logger.info("New email saved: from=%r subject=%r", em["sender"], em["subject"])

                # Check if this sender should trigger alert classification
                sender_lower = em["sender"].lower()
                is_alert_sender = any(s in sender_lower for s in ALERT_SENDERS)

                if not is_alert_sender:
                    await mark_email_processed(em["message_id"], alert_triggered=False)
                    continue

                result = classify_email(em["subject"], em["body"])
                logger.info(
                    "Classified: subject=%r level=%s alert=%s",
                    em["subject"],
                    result.level,
                    result.is_alert,
                )

                recipients_str = ""
                sms_sent = 0

                if result.is_alert:
                    sent_to = await send_sms_to_all(result.sms_message)
                    recipients_str = ", ".join(sent_to)
                    sms_sent = len(sent_to)

                snippet = em["body"][:200] if em["body"] else ""
                await add_alert(
                    subject=em["subject"],
                    body_snippet=snippet,
                    alert_level=result.level,
                    sms_sent=sms_sent,
                    recipients=recipients_str,
                )
                await mark_email_processed(em["message_id"], alert_triggered=result.is_alert)

        except Exception:
            logger.exception("Error in email poll loop")

        await asyncio.sleep(POLL_INTERVAL)


@app.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(email_poll_loop())


# ---------------------------------------------------------------------------
# Web UI routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    members = await get_members()
    alerts = await get_alerts(limit=30)
    all_emails = await get_emails(limit=50)
    settings = await get_all_settings()
    has_imap = bool(settings.get("imap_user") and settings.get("imap_pass"))
    has_twilio = bool(
        settings.get("twilio_sid")
        and settings.get("twilio_token")
        and settings.get("twilio_from")
    )
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "members": members,
            "alerts": alerts,
            "all_emails": all_emails,
            "settings": settings,
            "has_imap": has_imap,
            "has_twilio": has_twilio,
        },
    )


@app.get("/emails/{email_id}", response_class=HTMLResponse)
async def email_detail(request: Request, email_id: int):
    em = await get_email_by_id(email_id)
    if not em:
        return HTMLResponse("Email not found", status_code=404)
    return templates.TemplateResponse(
        "email_detail.html",
        {"request": request, "email": em},
    )


@app.post("/members/add")
async def member_add(name: str = Form(...), phone: str = Form(...)):
    phone = phone.strip()
    if not phone.startswith("+"):
        phone = "+1" + phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
    await add_member(name.strip(), phone)
    return RedirectResponse("/", status_code=303)


@app.post("/members/delete/{member_id}")
async def member_delete(member_id: int):
    await delete_member(member_id)
    return RedirectResponse("/", status_code=303)


@app.post("/settings/save")
async def settings_save(
    imap_host: str = Form("imap.gmail.com"),
    imap_user: str = Form(""),
    imap_pass: str = Form(""),
    twilio_sid: str = Form(""),
    twilio_token: str = Form(""),
    twilio_from: str = Form(""),
):
    if imap_host.strip():
        await set_setting("imap_host", imap_host.strip())
    if imap_user.strip():
        await set_setting("imap_user", imap_user.strip())
    if imap_pass.strip():
        await set_setting("imap_pass", imap_pass.strip())
    if twilio_sid.strip():
        await set_setting("twilio_sid", twilio_sid.strip())
    if twilio_token.strip():
        await set_setting("twilio_token", twilio_token.strip())
    if twilio_from.strip():
        await set_setting("twilio_from", twilio_from.strip())
    return RedirectResponse("/", status_code=303)


@app.post("/test/sms")
async def test_sms():
    sent = await send_sms_to_all("PivotAlert test message - if you received this, alerts are working!")
    return {"sent_to": sent}

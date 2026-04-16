import re
from dataclasses import dataclass
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str):
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def strip_html(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    return extractor.get_text()


@dataclass
class ClassificationResult:
    is_alert: bool
    level: str          # "critical", "warning", "info", "none"
    sms_message: str    # the message to send via SMS


# Patterns that strip the legal notice boilerplate
_NOTICE_PATTERN = re.compile(r"NOTICE to Recipient:.*", re.DOTALL | re.IGNORECASE)

# Custom SMS messages for each alert category
_SMS_NO_CONTROL = "\u2705 No control today! Good news \u2014 no load control expected."
_SMS_CONTROL_POSSIBLE = "\u26a0\ufe0f Control is possible today. Stay vigilant and be ready to shut down pivots."
_SMS_TAKING_CONTROL = "\U0001f6a8 LOAD CONTROL ACTIVE! Turn pivots OFF now!"
_SMS_RELEASING_CONTROL = "\U0001f7e2 Control is being released. You can turn pivots back on."


def classify_email(subject: str, body: str) -> ClassificationResult:
    text = strip_html(body)
    text = _NOTICE_PATTERN.sub("", text).strip()
    subject_lower = subject.lower().strip()
    lower = text.lower()

    # --- TAKING CONTROL (critical) ---
    if (
        "beginning control" in subject_lower
        or "implement control now" in lower
        or ("taking control of" in lower and "interruptibles" in lower)
    ):
        return ClassificationResult(
            is_alert=True,
            level="critical",
            sms_message=_SMS_TAKING_CONTROL,
        )

    # --- RELEASING CONTROL ---
    if (
        "releasing control" in subject_lower
        or ("releasing control" in lower and "interruptibles" in lower)
    ):
        return ClassificationResult(
            is_alert=True,
            level="info",
            sms_message=_SMS_RELEASING_CONTROL,
        )

    # --- NO CONTROL ---
    if "no control" in subject_lower or "will not be required" in lower:
        return ClassificationResult(
            is_alert=True,
            level="info",
            sms_message=_SMS_NO_CONTROL,
        )

    # --- CONTROL POSSIBLE (warning) ---
    if "control is possible" in lower or "control is possible" in subject_lower:
        return ClassificationResult(
            is_alert=True,
            level="warning",
            sms_message=_SMS_CONTROL_POSSIBLE,
        )

    # --- Everything else: store but don't SMS ---
    return ClassificationResult(
        is_alert=False,
        level="none",
        sms_message="",
    )

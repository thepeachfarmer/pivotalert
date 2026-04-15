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
    level: str          # "critical", "warning", "info"
    sms_message: str    # the message to send via SMS


# Patterns that strip the legal notice boilerplate
_NOTICE_PATTERN = re.compile(r"NOTICE to Recipient:.*", re.DOTALL | re.IGNORECASE)


def classify_email(subject: str, body: str) -> ClassificationResult:
    text = strip_html(body)
    text = _NOTICE_PATTERN.sub("", text).strip()
    subject_lower = subject.lower().strip()

    # --- NO CONTROL ---
    if "no control" in subject_lower or "will not be required" in text.lower():
        return ClassificationResult(
            is_alert=False,
            level="info",
            sms_message="",
        )

    # --- CRITICAL: active control happening now ---
    lower = text.lower()
    if (
        "beginning control" in subject_lower
        or "implement control now" in lower
        or ("taking control of" in lower and "interruptibles" in lower)
    ):
        return ClassificationResult(
            is_alert=True,
            level="critical",
            sms_message=f"LOAD CONTROL ALERT: {text}",
        )

    # --- WARNING: control is possible ---
    if "control is possible" in lower:
        return ClassificationResult(
            is_alert=True,
            level="warning",
            sms_message=f"Control is possible. {text}",
        )

    # --- Escalating: taking control of regulators, etc. ---
    if "taking control of" in lower:
        return ClassificationResult(
            is_alert=True,
            level="warning",
            sms_message=f"Control update: {text}",
        )

    # Default: unknown message type, send it to be safe
    return ClassificationResult(
        is_alert=True,
        level="warning",
        sms_message=f"PivotAlert: {text}",
    )

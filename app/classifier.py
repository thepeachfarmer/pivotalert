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

# Strips the trailing " - Santee Cooper" / " - Duke" provider tag from subjects
_SUBJECT_PROVIDER_TAIL = re.compile(r"\s*-\s*(santee cooper|duke|cepci|central electric).*$", re.IGNORECASE)

# Pulls the timeframe out of "No Control This Evening or Tomorrow Morning" \u2192 "this evening or tomorrow morning"
_NO_CONTROL_TIMEFRAME = re.compile(r"no control\s+(.+)", re.IGNORECASE)

# Custom SMS messages for each alert category
_SMS_CONTROL_POSSIBLE = "\u26a0\ufe0f Control is possible today. Stay vigilant and be ready to shut down pivots."
_SMS_TAKING_CONTROL = "\U0001f6a8 LOAD CONTROL ACTIVE! Turn pivots OFF now!"
_SMS_RELEASING_CONTROL = "\U0001f7e2 Control is being released. You can turn pivots back on."


def _no_control_sms(subject: str) -> str:
    """Build a No Control SMS that mirrors the source's timeframe, not a blanket 'today!'.

    Santee Cooper / Beat the Peak sends subjects like 'No Control This Evening or
    Tomorrow Morning' \u2014 saying 'no control today!' misrepresents that and lulls
    operators (they've changed their mind mid-day before \u2014 2026-06-11).
    """
    cleaned = _SUBJECT_PROVIDER_TAIL.sub("", subject).strip()
    m = _NO_CONTROL_TIMEFRAME.search(cleaned)
    timeframe = m.group(1).strip() if m else ""
    if timeframe:
        return f"\u2705 Santee Cooper: no load control expected {timeframe.lower()}. (They can still change their mind.)"
    return "\u2705 Santee Cooper: no load control expected. (They can still change their mind.)"


def classify_email(subject: str, body: str) -> ClassificationResult:
    text = strip_html(body)
    text = _NOTICE_PATTERN.sub("", text).strip()
    subject_lower = subject.lower().strip()
    lower = text.lower()

    # --- TAKING CONTROL (critical) ---
    # Anchored on `inbox/Beginning Control Now - Santee Cooper.eml` and the legacy CEPCI "Beginning control now."
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
    # Must be evaluated BEFORE Control Scheduled because subjects like
    # "No Control This Evening or Tomorrow Morning" contain both phrases \u2014
    # we want the No Control branch to win for those.
    #
    # Was matching "no control" anywhere in subject and firing "No control TODAY!"
    # \u2014 which lied on 2026-06-11 when the subject was "No Control This Evening
    # or Tomorrow Morning" (didn't say 'today') and they then called control
    # at 3pm. SMS now mirrors the subject's timeframe and adds a caveat.
    if "no control" in subject_lower or "will not be required" in lower:
        return ClassificationResult(
            is_alert=True,
            level="info",
            sms_message=_no_control_sms(subject),
        )

    # --- CONTROL SCHEDULED (warning, hours-out commitment) ---
    # Anchored on `inbox/Control This Evening - Santee Cooper.eml` (2026-06-11):
    # body is "Load control WILL BE initiated this evening". Distinct from
    # "Control is Possible" (which is hedged). Own cooldown level so it does
    # NOT suppress the later "critical" SMS when the event actually begins.
    if (
        "control this evening" in subject_lower
        or "control tonight" in subject_lower
        or "control today" in subject_lower
        or "control tomorrow" in subject_lower
        or "load control will be initiated" in lower
        or "control will be initiated" in lower
    ):
        timeframe = "soon"
        for key in ("this evening", "tonight", "today", "tomorrow"):
            if key in subject_lower:
                timeframe = key
                break
        return ClassificationResult(
            is_alert=True,
            level="scheduled",
            sms_message=f"\u26a0\ufe0f HEADS UP: Santee Cooper has announced a load control event {timeframe}. It IS coming \u2014 prepare to shut down pivots.",
        )

    # --- CONTROL POSSIBLE (warning, hedged) ---
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

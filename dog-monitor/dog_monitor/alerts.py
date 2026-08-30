"""Gmail SMTP email alerts for newly matched animals."""

import logging
import smtplib
from collections import defaultdict
from email.message import EmailMessage
from typing import List

from .config import Config
from .models import Animal, MatchLevel

logger = logging.getLogger(__name__)

_LEVEL_ORDER = [MatchLevel.EXACT, MatchLevel.STRONG, MatchLevel.POSSIBLE]

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _level_value(level) -> str:
    return level.value if isinstance(level, MatchLevel) else str(level)


def _format_animal(animal: Animal) -> str:
    lines = [f"- {animal.name or 'Unnamed'}  (ID: {animal.animal_id or 'unknown'})"]
    lines.append(f"    Source: {animal.source}")
    lines.append(f"    Region: {animal.region}")
    lines.append(f"    Match level: {_level_value(animal.match_level)}")
    lines.append(f"    Matched term: {animal.matched_term or 'n/a'}")
    lines.append(f"    Breed text: {animal.breed_text or 'n/a'}")
    if animal.weight is not None:
        lines.append(f"    Weight: {animal.weight:g} lb")
    if animal.age:
        lines.append(f"    Age: {animal.age}")
    if animal.sex:
        lines.append(f"    Sex: {animal.sex}")
    lines.append(f"    Listing URL: {animal.url}")
    if animal.image_url:
        lines.append(f"    Image: {animal.image_url}")
    return "\n".join(lines)


def build_subject(animals: List[Animal]) -> str:
    counts = defaultdict(int)
    for animal in animals:
        counts[animal.match_level] += 1
    parts = [f"{counts[level]} {level.value}" for level in _LEVEL_ORDER if counts[level]]
    if not parts:
        return "Dog Alert"
    return "Dog Alert — " + ", ".join(parts)


def build_body(animals: List[Animal]) -> str:
    sections = []
    for level in _LEVEL_ORDER:
        matching = [a for a in animals if a.match_level == level]
        if not matching:
            continue
        sections.append(f"{level.value} MATCHES ({len(matching)})")
        sections.append("=" * 40)
        for animal in matching:
            sections.append(_format_animal(animal))
            sections.append("")
    sections.append("Check availability with the shelter before traveling.")
    return "\n".join(sections)


def send_alert_email(config: Config, animals: List[Animal]) -> bool:
    """Send a single alert email grouping animals by match level.

    Returns True only on confirmed successful delivery. Returns False (and
    logs the reason) on any failure, including missing configuration, so the
    caller can leave alert_sent=0 for a retry on the next run.
    """
    if not animals:
        return True

    if not config.email_configured:
        logger.error(
            "Email is not configured (EMAIL_FROM/EMAIL_TO/EMAIL_PASSWORD); "
            "cannot send alert for %d animal(s).",
            len(animals),
        )
        return False

    message = EmailMessage()
    message["Subject"] = build_subject(animals)
    message["From"] = config.email_from
    message["To"] = config.email_to
    message.set_content(build_body(animals))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.login(config.email_from, config.email_password)
            smtp.send_message(message)
        logger.info("Alert email sent to %s covering %d animal(s).", config.email_to, len(animals))
        return True
    except Exception:
        logger.exception("Failed to send alert email via Gmail SMTP.")
        return False

"""Isolated, unit-tested breed matching and identifier-extraction logic.

This module has no dependencies on Playwright, SQLite, or email -- it is
pure text-processing so it can be exhaustively unit tested independent of
any scraper or network access.
"""

import hashlib
import re
from typing import List, Optional

from .models import MatchLevel, MatchResult

# Ordered longest-first within each tier so the more specific phrase is
# reported as the matched_term (e.g. "Cairn Terrier Mix" over "Cairn Terrier").
EXACT_TERMS: List[str] = [
    "Cairn Terrier Mix",
    "Cairn Mix",
    "Cairn Terrier",
    "Norwich Terrier Mix",
    "Norwich Mix",
    "Norwich Terrier",
]

STRONG_TERMS: List[str] = [
    "Norfolk Terrier Mix",
    "Norfolk Terrier",
]

POSSIBLE_TERMS: List[str] = [
    "Small Terrier",
    "Terrier Mix",
    "Terrier",
]

MIN_POSSIBLE_WEIGHT_LB = 5.0
MAX_POSSIBLE_WEIGHT_LB = 30.0

_WEIGHT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:lbs?\.?|pounds?)\b", re.IGNORECASE)
_ANIMAL_ID_RE = re.compile(r"\bA\d{6,8}\b")


def extract_weight(text: Optional[str]) -> Optional[float]:
    """Extract a weight in pounds from free text, e.g. '14 lb', '14 lbs',
    '14 pounds', '14.5 lbs'. Returns None if no weight is found."""
    if not text:
        return None
    match = _WEIGHT_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def extract_animal_id(text: Optional[str]) -> Optional[str]:
    """Extract a shelter animal ID of the form 'A' + 6-8 digits.

    Uses word boundaries so it will not match digits embedded in longer
    unrelated numbers (phone numbers, dates, etc.).
    """
    if not text:
        return None
    match = _ANIMAL_ID_RE.search(text)
    return match.group(0) if match else None


def build_petconnect_key(agency_code: str, animal_id: str) -> str:
    """Build a stable, agency-namespaced key, e.g. 'BRWD:A2450160'."""
    return f"{agency_code.upper()}:{animal_id.upper()}"


def build_fingerprint_key(source: str, *stable_fields: Optional[str]) -> str:
    """Build a deterministic SHA-256 fingerprint key from stable listing
    fields (name, breed text, detail URL, etc). Callers must avoid passing
    volatile text such as timestamps or "available now" style messages so
    the same animal fingerprints identically across runs.
    """
    normalized = "|".join((field or "").strip().lower() for field in stable_fields)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{source}:{digest[:16]}"


def _find_term(text_lower: str, terms: List[str]) -> Optional[str]:
    for term in sorted(terms, key=len, reverse=True):
        if term.lower() in text_lower:
            return term
    return None


def classify_breed(breed_text: str, weight: Optional[float] = None) -> MatchResult:
    """Classify a breed/description string into EXACT, STRONG, POSSIBLE, or
    NONE, per the project's breed-matching rules.

    - EXACT: Cairn Terrier / Cairn Terrier Mix / Cairn Mix / Norwich Terrier
      / Norwich Terrier Mix / Norwich Mix (case-insensitive).
    - STRONG: Norfolk Terrier / Norfolk Terrier Mix.
    - POSSIBLE: Small Terrier / Terrier Mix / Terrier, but only if weight is
      unknown OR between 5 and 30 lb inclusive. A generic terrier listing
      outside that weight range is downgraded to NONE so large dogs are not
      treated as possible Cairn/Norwich candidates.
    """
    text = breed_text or ""
    text_lower = text.lower()

    if weight is None:
        weight = extract_weight(text)

    exact = _find_term(text_lower, EXACT_TERMS)
    if exact:
        return MatchResult(level=MatchLevel.EXACT, matched_term=exact, weight=weight)

    strong = _find_term(text_lower, STRONG_TERMS)
    if strong:
        return MatchResult(level=MatchLevel.STRONG, matched_term=strong, weight=weight)

    possible = _find_term(text_lower, POSSIBLE_TERMS)
    if possible:
        if weight is not None and not (MIN_POSSIBLE_WEIGHT_LB <= weight <= MAX_POSSIBLE_WEIGHT_LB):
            return MatchResult(level=MatchLevel.NONE, matched_term=None, weight=weight)
        return MatchResult(level=MatchLevel.POSSIBLE, matched_term=possible, weight=weight)

    return MatchResult(level=MatchLevel.NONE, matched_term=None, weight=weight)

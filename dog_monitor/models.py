"""Shared data types used across the dog monitor application."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MatchLevel(str, Enum):
    """Breed-match confidence levels, from most to least specific."""

    EXACT = "EXACT"
    STRONG = "STRONG"
    POSSIBLE = "POSSIBLE"
    NONE = "NONE"


@dataclass(frozen=True)
class MatchResult:
    """Result of classifying a breed/description string."""

    level: MatchLevel
    matched_term: Optional[str] = None
    weight: Optional[float] = None


@dataclass
class Animal:
    """A single adoptable animal listing extracted from a source."""

    animal_key: str
    source: str
    region: str
    url: str
    animal_id: Optional[str] = None
    name: Optional[str] = None
    breed_text: Optional[str] = None
    description: Optional[str] = None
    age: Optional[str] = None
    sex: Optional[str] = None
    weight: Optional[float] = None
    image_url: Optional[str] = None
    match_level: MatchLevel = MatchLevel.NONE
    matched_term: Optional[str] = None

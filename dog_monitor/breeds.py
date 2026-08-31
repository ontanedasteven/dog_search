"""Target breed configuration -- the file a contributor edits to change
what this monitor looks for, without touching the classification
algorithm itself (`dog_monitor/matching.py`). This mirrors
`dog_monitor/sources.py`'s role for shelters: one small, plain-data file
per axis of configuration (which shelters to watch / which breeds to
watch for), separate from the code that acts on it.

How matching uses these lists (see `matching.classify_breed` for the
actual algorithm): each term is matched case-insensitively as a
substring of a listing's free-text breed field, checked in this priority
order -- EXACT_TERMS, then STRONG_TERMS, then POSSIBLE_TERMS. Within a
tier, list a more specific phrase before a shorter phrase it contains
(e.g. "Cairn Terrier Mix" before "Cairn Terrier") purely for
readability -- `classify_breed` re-sorts by length internally regardless,
so the more specific phrase is always what gets recorded as the match.

To retarget this monitor at different breeds, edit the three term lists
below and re-run `pytest tests/test_matching.py -v` -- every existing
rule (including the weight-boundary behavior) has a dedicated test, so a
change here that breaks an assumption will fail loudly rather than
silently.
"""

from typing import List

# Unambiguous matches: a listing containing any of these phrases is
# treated as an EXACT match regardless of weight.
EXACT_TERMS: List[str] = [
    "Cairn Terrier Mix",
    "Cairn Mix",
    "Cairn Terrier",
    "Norwich Terrier Mix",
    "Norwich Mix",
    "Norwich Terrier",
]

# Closely related target breeds -- one tier below EXACT, still kept
# regardless of weight.
STRONG_TERMS: List[str] = [
    "Norfolk Terrier Mix",
    "Norfolk Terrier",
]

# Generic labels that *could* be a target breed (a shelter's own "Terrier
# Mix" catch-all is common and imprecise) -- kept only if weight is
# unknown, or known and within [MIN_POSSIBLE_WEIGHT_LB, MAX_POSSIBLE_WEIGHT_LB].
POSSIBLE_TERMS: List[str] = [
    "Small Terrier",
    "Terrier Mix",
    "Terrier",
]

# Weight window (inclusive, pounds) a POSSIBLE_TERMS match must fall
# into, when a weight is available, to be kept as POSSIBLE rather than
# downgraded to NONE. Listings with no published weight are kept as
# POSSIBLE regardless -- some sources (see README's "Current Breed
# Matching") never publish weight at all, and dropping unknown-weight
# listings would silently miss real matches from those sources.
MIN_POSSIBLE_WEIGHT_LB = 5.0
MAX_POSSIBLE_WEIGHT_LB = 30.0

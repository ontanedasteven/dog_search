"""Sanity checks for the target breed configuration (dog_monitor/breeds.py).

These exist so a contributor retargeting this monitor at different
breeds gets a clear failure for an obviously broken edit (an empty list,
a duplicated term, an inverted weight range) rather than a confusing
downstream test_matching.py failure."""

from dog_monitor.breeds import (
    EXACT_TERMS,
    MAX_POSSIBLE_WEIGHT_LB,
    MIN_POSSIBLE_WEIGHT_LB,
    POSSIBLE_TERMS,
    STRONG_TERMS,
)


def test_term_lists_are_non_empty():
    assert EXACT_TERMS
    assert STRONG_TERMS
    assert POSSIBLE_TERMS


def test_no_duplicate_terms_within_a_tier():
    for name, terms in [("EXACT_TERMS", EXACT_TERMS), ("STRONG_TERMS", STRONG_TERMS), ("POSSIBLE_TERMS", POSSIBLE_TERMS)]:
        lowered = [t.lower() for t in terms]
        assert len(lowered) == len(set(lowered)), f"duplicate term in {name}"


def test_no_term_appears_in_more_than_one_tier():
    # A phrase in two tiers would make classify_breed's result depend on
    # tier-check order in a way that's easy to get wrong when editing.
    exact = {t.lower() for t in EXACT_TERMS}
    strong = {t.lower() for t in STRONG_TERMS}
    possible = {t.lower() for t in POSSIBLE_TERMS}
    assert not (exact & strong)
    assert not (exact & possible)
    assert not (strong & possible)


def test_weight_range_is_valid():
    assert MIN_POSSIBLE_WEIGHT_LB > 0
    assert MAX_POSSIBLE_WEIGHT_LB > MIN_POSSIBLE_WEIGHT_LB

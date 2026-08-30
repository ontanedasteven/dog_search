from dog_monitor.matching import classify_breed, extract_animal_id, extract_weight
from dog_monitor.models import MatchLevel


def test_cairn_terrier_is_exact():
    result = classify_breed("Cairn Terrier")
    assert result.level == MatchLevel.EXACT
    assert result.matched_term == "Cairn Terrier"


def test_cairn_terrier_mix_is_exact():
    result = classify_breed("Cairn Terrier Mix")
    assert result.level == MatchLevel.EXACT
    assert result.matched_term == "Cairn Terrier Mix"


def test_cairn_mix_is_exact():
    result = classify_breed("Cairn Mix")
    assert result.level == MatchLevel.EXACT


def test_norwich_terrier_mix_is_exact():
    result = classify_breed("Norwich Terrier Mix")
    assert result.level == MatchLevel.EXACT
    assert result.matched_term == "Norwich Terrier Mix"


def test_norwich_terrier_is_exact():
    result = classify_breed("Norwich Terrier")
    assert result.level == MatchLevel.EXACT


def test_case_insensitive_matching():
    result = classify_breed("cairn terrier")
    assert result.level == MatchLevel.EXACT


def test_norfolk_terrier_is_strong():
    result = classify_breed("Norfolk Terrier")
    assert result.level == MatchLevel.STRONG
    assert result.matched_term == "Norfolk Terrier"


def test_norfolk_terrier_mix_is_strong():
    result = classify_breed("Norfolk Terrier Mix")
    assert result.level == MatchLevel.STRONG
    assert result.matched_term == "Norfolk Terrier Mix"


def test_terrier_mix_with_acceptable_weight_is_possible():
    result = classify_breed("Terrier Mix, 14 lbs")
    assert result.level == MatchLevel.POSSIBLE
    assert result.weight == 14.0


def test_terrier_mix_too_heavy_is_no_match():
    result = classify_breed("Terrier Mix, 65 lbs")
    assert result.level == MatchLevel.NONE


def test_terrier_with_no_weight_is_possible():
    result = classify_breed("Terrier")
    assert result.level == MatchLevel.POSSIBLE
    assert result.weight is None


def test_small_terrier_is_possible():
    result = classify_breed("Small Terrier")
    assert result.level == MatchLevel.POSSIBLE


def test_large_dog_with_terrier_word_and_weight_is_not_possible():
    # "contains terrier" should not be enough on its own when weight rules
    # it out of small-terrier range.
    result = classify_breed("Airedale Terrier, 65 lbs")
    assert result.level == MatchLevel.NONE


def test_boundary_weights_are_accepted():
    assert classify_breed("Terrier Mix", weight=5.0).level == MatchLevel.POSSIBLE
    assert classify_breed("Terrier Mix", weight=30.0).level == MatchLevel.POSSIBLE


def test_boundary_weights_just_outside_are_rejected():
    assert classify_breed("Terrier Mix", weight=4.9).level == MatchLevel.NONE
    assert classify_breed("Terrier Mix", weight=30.1).level == MatchLevel.NONE


def test_non_terrier_breed_is_no_match():
    result = classify_breed("Labrador Retriever")
    assert result.level == MatchLevel.NONE


def test_weight_extraction_lb():
    assert extract_weight("14 lb") == 14.0


def test_weight_extraction_lbs():
    assert extract_weight("14 lbs") == 14.0


def test_weight_extraction_pounds():
    assert extract_weight("14 pounds") == 14.0


def test_weight_extraction_decimal_lbs():
    assert extract_weight("14.5 lbs") == 14.5


def test_weight_extraction_no_weight_present():
    assert extract_weight("Terrier Mix, playful and friendly") is None


def test_weight_extraction_empty_text():
    assert extract_weight("") is None
    assert extract_weight(None) is None


def test_animal_id_extraction_basic():
    assert extract_animal_id("Adopt me! ID: A2450160") == "A2450160"


def test_animal_id_extraction_ignores_unrelated_numbers():
    assert extract_animal_id("Call 305-555-1234 for more info") is None


def test_animal_id_extraction_does_not_grab_partial_id_from_longer_token():
    assert extract_animal_id("Ref AB2450160Z is not a valid ID format") is None


def test_animal_id_extraction_min_and_max_digit_lengths():
    assert extract_animal_id("A123456") == "A123456"
    assert extract_animal_id("A12345678") == "A12345678"

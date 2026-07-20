import pytest
from sakshya_recovery.triage.keyword_match import match_keywords


def test_exact_english_match():
    # Use default config (loads red_flags.yaml) — 'payment' is in english keywords
    results = match_keywords("payment received")
    assert len(results) > 0
    assert any(r["keyword"] == "payment" for r in results)


def test_exact_hindi_match():
    results = match_keywords("मुझे पैसा चाहिए")
    assert len(results) > 0
    assert any(r["keyword"] == "पैसा" for r in results)


def test_exact_gujarati_match():
    results = match_keywords("લાંચ લીધી")
    assert len(results) > 0
    assert any(r["keyword"] == "લાંચ" for r in results)


def test_fuzzy_transliteration():
    # "paisi" should fuzzy-match "paisa" (edit distance 1)
    results = match_keywords("paisi is needed")
    fuzzy = [r for r in results if r["match_type"] == "fuzzy"]
    assert len(fuzzy) > 0
    assert any(r["keyword"] == "paisa" for r in fuzzy)


def test_no_false_positives():
    results = match_keywords("hello world how are you")
    assert len(results) == 0


def test_case_insensitivity():
    results = match_keywords("PAYMENT RECEIVED")
    assert len(results) > 0
    assert any(r["keyword"] == "payment" for r in results)


def test_mixed_script_text():
    results = match_keywords("payment done, पैसा received")
    matched_keywords = [r["keyword"] for r in results]
    assert "payment" in matched_keywords
    assert "पैसा" in matched_keywords


def test_deterministic_match():
    r1 = match_keywords("payment received and पैसा")
    r2 = match_keywords("payment received and पैसा")
    assert r1 == r2

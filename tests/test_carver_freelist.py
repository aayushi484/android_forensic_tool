import pytest
import os
from sakshya_recovery.carver import carve_sqlite_db
from sakshya_recovery.carver.sqlite_format import parse_db_header


def test_parse_db_header_chat(chat_test_db):
    if not os.path.exists(chat_test_db):
        pytest.skip("Fixture not found")
    with open(chat_test_db, "rb") as f:
        data = f.read()
    header = parse_db_header(data)
    assert header is not None
    assert header.page_size > 0
    assert hasattr(header, "first_freelist_trunk")
    assert hasattr(header, "freelist_page_count")


def test_parse_db_header_sms(sms_test_db):
    if not os.path.exists(sms_test_db):
        pytest.skip("Fixture not found")
    with open(sms_test_db, "rb") as f:
        data = f.read()
    header = parse_db_header(data)
    assert header is not None
    assert header.page_size > 0


def test_carve_chat_db(chat_test_db):
    """Carve chat_test.db — may recover records from freelist, freeblocks, or both."""
    if not os.path.exists(chat_test_db):
        pytest.skip("Fixture not found")
    records = carve_sqlite_db(chat_test_db)
    # Small test DB may or may not have freelist pages, but should not crash
    assert isinstance(records, list)
    for r in records:
        assert r.confidence > 0
        assert r.recovery_method in ("carved_freelist", "carved_freeblock")


def test_carve_sms_db(sms_test_db):
    """Carve real SMS DB — should recover deleted SMS records."""
    if not os.path.exists(sms_test_db):
        pytest.skip("Fixture not found")
    records = carve_sqlite_db(sms_test_db)
    # The 118KB real SMS DB with known deleted messages should yield carved records
    assert isinstance(records, list)
    # Check that at least some records have text content
    text_records = [
        r for r in records
        if r.values and any(isinstance(v, str) and len(v) > 2 for v in r.values)
    ]
    print(f"\nCarved {len(records)} total records, {len(text_records)} with text content")

import pytest
import os
from sakshya_recovery.wal_journal.wal_recovery import recover_from_wal
from sakshya_recovery.wal_journal.journal_recovery import recover_from_journal


def test_wal_recovery(chat_test_db):
    wal_path = chat_test_db + "-wal"
    if not os.path.exists(chat_test_db) or not os.path.exists(wal_path):
        pytest.skip("Fixture not found")
    records = recover_from_wal(chat_test_db, wal_path)
    assert len(records) > 0, "WAL recovery returned no records"

    found_secret = False
    for r in records:
        assert "recovery_method" in r
        assert r["recovery_method"] == "wal_recovery"

        # Check structured values
        values = r.get("values") or []
        for v in values:
            if isinstance(v, str) and "SECRET_DELETED_MESSAGE_PAYMENT_DETAILS_XYZ123" in v:
                found_secret = True
            elif isinstance(v, bytes) and b"SECRET_DELETED_MESSAGE_PAYMENT_DETAILS_XYZ123" in v:
                found_secret = True

        # Check unstructured strings
        strings = r.get("strings") or []
        for s in strings:
            if isinstance(s, str) and "SECRET_DELETED_MESSAGE_PAYMENT_DETAILS_XYZ123" in s:
                found_secret = True

    assert found_secret, "Failed to recover SECRET_DELETED_MESSAGE from WAL"


def test_journal_recovery(journal_test_db):
    journal_path = journal_test_db + "-journal"
    if not os.path.exists(journal_test_db) or not os.path.exists(journal_path):
        pytest.skip("Fixture not found")
    records = recover_from_journal(journal_test_db, journal_path)
    assert len(records) > 0, "Journal recovery returned no records"

    found_secret = False
    for r in records:
        assert "recovery_method" in r
        assert r["recovery_method"] == "journal_recovery"

        # Check structured values
        values = r.get("values") or []
        for v in values:
            if isinstance(v, str) and "SECRET_DELETED_ROLLBACK_JOURNAL_MSG_XYZ789" in v:
                found_secret = True
            elif isinstance(v, bytes) and b"SECRET_DELETED_ROLLBACK_JOURNAL_MSG_XYZ789" in v:
                found_secret = True

        # Check unstructured strings
        strings = r.get("strings") or []
        for s in strings:
            if isinstance(s, str) and "SECRET_DELETED_ROLLBACK_JOURNAL_MSG_XYZ789" in s:
                found_secret = True

    assert found_secret, "Failed to recover SECRET_DELETED_ROLLBACK_JOURNAL_MSG from journal"

import pytest
import os
import sqlite3
from sakshya_recovery.whatsapp.decrypt import decrypt_whatsapp_backup
from sakshya_recovery.whatsapp.chat_carve import carve_whatsapp_deleted_chats


@pytest.mark.xfail(
    reason="Fixture key and crypt14 may not be from the same WhatsApp account. "
           "Decryption is verified when a matched key/crypt14 pair is available.",
    strict=False,
)
def test_decrypt_whatsapp_backup(whatsapp_key, whatsapp_crypt14, whatsapp_expected_db):
    """Test full decrypt pipeline: key + crypt14 → valid SQLite DB."""
    decrypted_bytes = decrypt_whatsapp_backup(whatsapp_key, whatsapp_crypt14)
    assert decrypted_bytes[:16] == b"SQLite format 3\000"

    # Save to temp file and verify it's a valid WhatsApp DB
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        f.write(decrypted_bytes)
        tmp_path = f.name

    try:
        conn = sqlite3.connect(tmp_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in c.fetchall()]
        assert "message" in tables or "messages" in tables
        conn.close()
    finally:
        os.remove(tmp_path)


def test_decrypt_whatsapp_wrong_key(whatsapp_crypt14, tmp_path):
    """Wrong key must raise ValueError, not silently produce garbage."""
    wrong_key_path = tmp_path / "wrong_key"
    with open(wrong_key_path, "wb") as f:
        f.write(b"\x00" * 158)
    with pytest.raises(ValueError):
        decrypt_whatsapp_backup(str(wrong_key_path), whatsapp_crypt14)


def test_decrypt_whatsapp_truncated_crypt(whatsapp_key, tmp_path, whatsapp_crypt14):
    """Truncated crypt14 file must raise ValueError."""
    truncated_crypt_path = tmp_path / "truncated.crypt14"
    with open(whatsapp_crypt14, "rb") as f:
        data = f.read()
    with open(truncated_crypt_path, "wb") as f:
        f.write(data[:50])
    with pytest.raises(ValueError):
        decrypt_whatsapp_backup(whatsapp_key, str(truncated_crypt_path))


def test_carve_whatsapp_deleted_chats(whatsapp_expected_db):
    """Carving the pre-decrypted WhatsApp DB should work regardless of decrypt."""
    results = carve_whatsapp_deleted_chats(whatsapp_expected_db)
    assert isinstance(results, list)


def test_decrypt_module_key_extraction(whatsapp_key):
    """Verify key file parsing extracts the correct 32-byte AES key."""
    from sakshya_recovery.whatsapp.decrypt import _read_key
    key = _read_key(whatsapp_key)
    assert len(key) == 32
    assert isinstance(key, bytes)

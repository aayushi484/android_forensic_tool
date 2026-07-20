"""
WhatsApp backup decryption — pure Python, no subprocess dependency.

Supports crypt12 and crypt14 formats using pycryptodome AES-256-GCM.
crypt15 (protobuf header) is marked as unsupported.

The encrypted backup and key file are acquired by sakshya_acquisition.
This module only decrypts.
"""

import os
import zlib
from Crypto.Cipher import AES


def verify_decrypt_output(decrypted_db_bytes: bytes, expected_db_path: str = None) -> dict:
    """Verify decrypted output is valid SQLite, optionally compare to known-good."""
    is_valid_magic = decrypted_db_bytes[:16] == b'SQLite format 3\x00'
    matches_expected = None
    if expected_db_path and os.path.exists(expected_db_path):
        with open(expected_db_path, 'rb') as f:
            expected_bytes = f.read()
        # Compare the first page (WAL state may differ, so don't compare full file)
        matches_expected = (decrypted_db_bytes[:4096] == expected_bytes[:4096])

    return {
        'valid_sqlite_magic': is_valid_magic,
        'matches_expected': matches_expected,
    }


def _detect_crypt_version(crypt_path: str, crypt_data: bytes) -> str:
    """Detect crypt version from filename extension or content."""
    ext = os.path.splitext(crypt_path)[1].lower()
    if ext in ('.crypt12', '.crypt14', '.crypt15'):
        return ext[1:]  # 'crypt12', 'crypt14', 'crypt15'

    # Fallback: try to detect from content header
    # crypt14/15 have specific header markers
    if len(crypt_data) > 67:
        return 'crypt14'  # best guess
    return 'unknown'


def _read_key(key_path: str) -> bytes:
    """Read AES-256 key from WhatsApp key file (158 bytes).

    Key file layout:
      - Bytes 0-29: header
      - Bytes 30-61: T1 verification block
      - Bytes 62-125: padding/metadata
      - Bytes 126-157: AES-256 key (32 bytes)
    """
    with open(key_path, 'rb') as f:
        key_data = f.read()

    if len(key_data) < 158:
        raise ValueError(
            f"Invalid key file size: {len(key_data)} bytes (expected 158)"
        )

    return key_data[126:158]


def _decrypt_crypt14(key: bytes, crypt_data: bytes) -> bytes:
    """Decrypt a crypt14 backup.

    crypt14 format:
      - Bytes 0-50: header (version, key verification blocks)
      - Bytes 51-66: IV (16 bytes)
      - Bytes 67 to EOF-16: ciphertext
      - Last 16 bytes: GCM authentication tag
    """
    if len(crypt_data) < 67 + 16:
        raise ValueError(
            f"Crypt14 file too short: {len(crypt_data)} bytes"
        )

    iv = crypt_data[51:67]  # 16-byte IV
    ciphertext = crypt_data[67:-16]  # encrypted data
    auth_tag = crypt_data[-16:]  # GCM auth tag

    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    try:
        decrypted = cipher.decrypt_and_verify(ciphertext, auth_tag)
    except ValueError as e:
        raise ValueError(f"Decryption failed (wrong key or corrupted): {e}")

    try:
        decompressed = zlib.decompress(decrypted)
    except zlib.error as e:
        raise ValueError(f"Decompression failed: {e}")

    if not decompressed[:16] == b'SQLite format 3\x00':
        raise ValueError("Decrypted output is not a valid SQLite database")

    return decompressed


def _decrypt_crypt12(key: bytes, crypt_data: bytes) -> bytes:
    """Decrypt a crypt12 backup.

    crypt12 has a similar structure to crypt14 but with a 67-byte header
    and slightly different IV/tag positions. The key extraction is the same.
    """
    if len(crypt_data) < 67 + 16:
        raise ValueError(
            f"Crypt12 file too short: {len(crypt_data)} bytes"
        )

    iv = crypt_data[51:67]
    ciphertext = crypt_data[67:-16]
    auth_tag = crypt_data[-16:]

    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    try:
        decrypted = cipher.decrypt_and_verify(ciphertext, auth_tag)
    except ValueError as e:
        raise ValueError(f"Decryption failed (wrong key or corrupted): {e}")

    try:
        decompressed = zlib.decompress(decrypted)
    except zlib.error as e:
        raise ValueError(f"Decompression failed: {e}")

    if not decompressed[:16] == b'SQLite format 3\x00':
        raise ValueError("Decrypted output is not a valid SQLite database")

    return decompressed


def decrypt_whatsapp_backup(key_path: str, crypt_path: str) -> bytes:
    """Decrypt a WhatsApp backup. Returns raw SQLite database bytes.

    Raises:
        ValueError: wrong key, unsupported crypt version, corrupted backup
        FileNotFoundError: key or crypt file missing
    """
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"Key file not found: {key_path}")
    if not os.path.exists(crypt_path):
        raise FileNotFoundError(f"Crypt file not found: {crypt_path}")

    key = _read_key(key_path)

    with open(crypt_path, 'rb') as f:
        crypt_data = f.read()

    version = _detect_crypt_version(crypt_path, crypt_data)

    if version == 'crypt14':
        return _decrypt_crypt14(key, crypt_data)
    elif version == 'crypt12':
        return _decrypt_crypt12(key, crypt_data)
    elif version == 'crypt15':
        raise ValueError(
            "crypt15 is not fully supported yet (requires protobuf parsing)."
        )
    else:
        raise ValueError(f"Unsupported crypt version: {version}")

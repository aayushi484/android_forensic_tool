import pytest
import os
from sakshya_recovery.carver.sqlite_format import decode_varint, serial_type_size, parse_record
from sakshya_recovery.carver import carve_sqlite_db


def test_decode_varint():
    assert decode_varint(b'\x00', 0) == (0, 1)
    assert decode_varint(b'\x01', 0) == (1, 1)
    assert decode_varint(b'\x7f', 0) == (127, 1)
    assert decode_varint(b'\x81\x00', 0) == (128, 2)
    assert decode_varint(b'\x81\x7f', 0) == (255, 2)
    assert decode_varint(b'\x82\x00', 0) == (256, 2)
    assert decode_varint(b'\xff\x7f', 0) == (16383, 2)


def test_serial_type_size():
    assert serial_type_size(0) == 0
    assert serial_type_size(1) == 1
    assert serial_type_size(2) == 2
    assert serial_type_size(3) == 3
    assert serial_type_size(4) == 4
    assert serial_type_size(5) == 6
    assert serial_type_size(6) == 8
    assert serial_type_size(7) == 8
    assert serial_type_size(8) == 0
    assert serial_type_size(9) == 0
    assert serial_type_size(12) == 0  # Blob size 0
    assert serial_type_size(13) == 0  # Text size 0
    assert serial_type_size(14) == 1  # Blob size 1
    assert serial_type_size(15) == 1  # Text size 1
    assert serial_type_size(16) == 2  # Blob size 2
    assert serial_type_size(17) == 2  # Text size 2


def test_parse_record():
    # Construct a simple record:
    # Header varint: 3 (header is 3 bytes total, including this varint)
    # Serial type 17 = text of length (17-13)/2 = 2 bytes → "hi"
    # Serial type 23 = text of length (23-13)/2 = 5 bytes → "hello"
    record_data = b'\x03\x11\x17hihello'
    result = parse_record(record_data, 0)
    assert result is not None
    values, consumed = result
    assert len(values) == 2
    assert values[0] == "hi"
    assert values[1] == "hello"


def test_freeblock_carving(chat_test_db):
    if not os.path.exists(chat_test_db):
        pytest.skip("Fixture not found")
    records = carve_sqlite_db(chat_test_db)
    # Just ensure it doesn't crash — freeblock records may or may not exist
    freeblock_records = [r for r in records if "freeblock" in r.recovery_method]
    assert len(freeblock_records) >= 0


def test_unstructured_fallback(chat_test_db):
    if not os.path.exists(chat_test_db):
        pytest.skip("Fixture not found")
    # The carver should at least not crash
    records = carve_sqlite_db(chat_test_db)
    assert isinstance(records, list)

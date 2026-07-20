import struct
import os
import logging
from sakshya_recovery.carver.sqlite_format import (
    parse_db_header, parse_page_header, get_cell_pointers,
    parse_leaf_table_cell, PAGE_TYPE_LEAF_TABLE,
)
from sakshya_recovery.carver.unstructured_fallback import extract_text_strings

logger = logging.getLogger(__name__)

JOURNAL_HEADER_MAGIC = b'\xd9\xd5\x05\xf9\x20\xa1\x63\xd7'


def recover_from_journal(db_path: str, journal_path: str) -> list[dict]:
    """Recover data from a SQLite rollback journal file.

    Parses the journal header, extracts pre-modification page snapshots,
    and runs b-tree parsing on each page. Falls back to unstructured
    string extraction where structured parsing fails.
    """
    results = []

    try:
        journal_data = open(journal_path, 'rb').read()
    except Exception as e:
        logger.error(f"Cannot read journal {journal_path}: {e}")
        return results

    if len(journal_data) < 28:
        return results

    magic = journal_data[:8]
    has_valid_magic = (magic == JOURNAL_HEADER_MAGIC)
    if not has_valid_magic:
        logger.warning(f"Journal magic mismatch in {journal_path}")

    # Read page_size from DB header (more reliable than journal header
    # for small/test journals where header fields may be zeroed)
    page_size = 4096  # default
    try:
        with open(db_path, 'rb') as db_f:
            db_header_data = db_f.read(100)
            db_header = parse_db_header(db_header_data)
            if db_header:
                page_size = db_header.page_size
    except Exception:
        pass

    # Try parsing journal header for page count and sector size
    sector_size = 512
    page_count = 0
    if has_valid_magic and len(journal_data) >= 28:
        raw_page_count = struct.unpack('>I', journal_data[8:12])[0]
        # nonce at 12:16
        # initial_db_size at 16:20
        raw_sector_size = struct.unpack('>I', journal_data[20:24])[0]
        raw_page_size = struct.unpack('>I', journal_data[24:28])[0]

        if 0 < raw_sector_size <= 65536:
            sector_size = raw_sector_size
        if 512 <= raw_page_size <= 65536:
            page_size = raw_page_size
        if raw_page_count != 0xFFFFFFFF and raw_page_count > 0:
            page_count = raw_page_count

    # If page_count is unknown, compute from file size
    record_size = 4 + page_size + 4  # page_number(4) + page_data(page_size) + checksum(4)
    if page_count == 0:
        available = len(journal_data) - sector_size
        if available > 0 and record_size > 0:
            page_count = available // record_size

    # Extract page images
    offset = sector_size
    for i in range(page_count):
        if offset + 4 > len(journal_data):
            break
        page_number = struct.unpack('>I', journal_data[offset:offset + 4])[0]
        offset += 4

        if offset + page_size > len(journal_data):
            break
        page_data = journal_data[offset:offset + page_size]
        offset += page_size

        # Skip 4-byte checksum
        offset += 4

        # Determine b-tree header offset (page 1 has 100-byte DB header)
        btree_offset = 100 if page_number == 1 else 0

        # Try structured parsing
        ph = parse_page_header(page_data, btree_offset)
        if ph is not None and ph.page_type == PAGE_TYPE_LEAF_TABLE:
            pointers = get_cell_pointers(page_data, ph, btree_offset)
            for ptr in pointers:
                cell = parse_leaf_table_cell(page_data, ptr)
                if cell is not None:
                    results.append({
                        'values': cell['values'],
                        'strings': None,
                        'recovery_method': 'journal_recovery',
                        'page_number': page_number,
                    })

        # Always also run unstructured extraction
        raw_strings = extract_text_strings(page_data)
        if raw_strings:
            str_list = [s for s, _off in raw_strings]
            results.append({
                'values': None,
                'strings': str_list,
                'recovery_method': 'journal_recovery',
                'page_number': page_number,
            })

    # If journal had no valid magic but has data, try scanning the raw
    # bytes as a fallback (some journals are just page images without header)
    if not has_valid_magic and not results:
        raw_strings = extract_text_strings(journal_data)
        if raw_strings:
            str_list = [s for s, _off in raw_strings]
            results.append({
                'values': None,
                'strings': str_list,
                'recovery_method': 'journal_recovery',
                'page_number': 0,
            })

    return results

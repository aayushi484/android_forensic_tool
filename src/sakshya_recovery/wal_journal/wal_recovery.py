import struct
import os
import logging
from sakshya_recovery.carver.sqlite_format import (
    parse_page_header, get_cell_pointers, parse_leaf_table_cell,
    PAGE_TYPE_LEAF_TABLE, PAGE_TYPE_LEAF_INDEX,
)
from sakshya_recovery.carver.unstructured_fallback import extract_text_strings

logger = logging.getLogger(__name__)

WAL_HEADER_SIZE = 32
FRAME_HEADER_SIZE = 24


def get_page_size(wal_header: bytes) -> int:
    """Extract page size from WAL header at offset 8."""
    if len(wal_header) < WAL_HEADER_SIZE:
        return 0
    return struct.unpack('>I', wal_header[8:12])[0]


def extract_wal_pages(wal_path: str):
    """Extract pages from a WAL file."""
    pages = []
    try:
        with open(wal_path, 'rb') as f:
            header = f.read(WAL_HEADER_SIZE)
            if len(header) < WAL_HEADER_SIZE:
                return pages

            magic = struct.unpack('>I', header[0:4])[0]
            if magic not in (0x377f0682, 0x377f0683):
                logger.warning(f"Invalid WAL magic: {magic:#x}")
                return pages

            page_size = get_page_size(header)
            if page_size == 0 or page_size > 65536 or page_size < 512:
                logger.warning(f"Invalid page size in WAL: {page_size}")
                return pages

            frame_index = 0
            while True:
                frame_header = f.read(FRAME_HEADER_SIZE)
                if len(frame_header) < FRAME_HEADER_SIZE:
                    break

                page_number = struct.unpack('>I', frame_header[0:4])[0]
                page_data = f.read(page_size)

                if len(page_data) < page_size:
                    break

                pages.append({
                    'page_number': page_number,
                    'frame_index': frame_index,
                    'data': page_data,
                })
                frame_index += 1

    except Exception as e:
        logger.error(f"Error reading WAL {wal_path}: {e}")

    return pages


def recover_from_wal(db_path: str, wal_path: str) -> list[dict]:
    """Recover structured and unstructured data from a WAL file.

    For each WAL page, FIRST tries the b-tree page parser for structured
    record recovery. If structured parsing fails, falls back to UTF-8
    string extraction (handles Devanagari/Gujarati).
    """
    results = []
    pages = extract_wal_pages(wal_path)

    for p in pages:
        page_data = p['data']
        page_num = p['page_number']
        frame_idx = p['frame_index']

        # Determine b-tree header offset (page 1 has 100-byte DB header)
        btree_offset = 100 if page_num == 1 else 0

        # Try structured parsing first
        ph = parse_page_header(page_data, btree_offset)
        if ph is not None and ph.page_type == PAGE_TYPE_LEAF_TABLE:
            pointers = get_cell_pointers(page_data, ph, btree_offset)
            for ptr in pointers:
                cell = parse_leaf_table_cell(page_data, ptr)
                if cell is not None:
                    results.append({
                        'values': cell['values'],
                        'strings': None,
                        'recovery_method': 'wal_recovery',
                        'page_number': page_num,
                        'frame_index': frame_idx,
                    })

        # Always also run unstructured extraction (catches data the
        # structured parser misses — freeblocks within WAL pages, etc.)
        raw_strings = extract_text_strings(page_data)
        if raw_strings:
            str_list = [s for s, _offset in raw_strings]
            results.append({
                'values': None,
                'strings': str_list,
                'recovery_method': 'wal_recovery',
                'page_number': page_num,
                'frame_index': frame_idx,
            })

    return results

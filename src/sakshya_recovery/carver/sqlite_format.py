import struct
from dataclasses import dataclass
from typing import Tuple, List, Optional, Any, Dict

SQLITE_MAGIC = b'SQLite format 3\x00'

PAGE_TYPE_LEAF_TABLE = 0x0D
PAGE_TYPE_INTERIOR_TABLE = 0x05
PAGE_TYPE_LEAF_INDEX = 0x0A
PAGE_TYPE_INTERIOR_INDEX = 0x02

@dataclass(frozen=True)
class DbHeader:
    """Represents the 100-byte SQLite database header."""
    page_size: int
    reserved_per_page: int
    first_freelist_trunk: int
    freelist_page_count: int
    text_encoding: int

    @property
    def usable_page_size(self) -> int:
        return self.page_size - self.reserved_per_page

@dataclass(frozen=True)
class PageHeader:
    """Represents a B-Tree page header."""
    page_type: int
    first_freeblock: int
    cell_count: int
    cell_content_offset: int
    fragmented_free_bytes: int
    right_child: Optional[int]

    @property
    def header_size(self) -> int:
        return 12 if self.page_type in (PAGE_TYPE_INTERIOR_TABLE, PAGE_TYPE_INTERIOR_INDEX) else 8

def decode_varint(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """
    Decodes a SQLite variable-length integer.
    Returns (value, bytes_consumed).
    """
    result = 0
    bytes_consumed = 0
    for i in range(9):
        if offset + i >= len(data):
            break
        b = data[offset + i]
        bytes_consumed += 1
        if i == 8:
            result = (result << 8) | b
            break
        result = (result << 7) | (b & 0x7F)
        if (b & 0x80) == 0:
            break
    return result, bytes_consumed

def serial_type_size(serial_type: int) -> int:
    """Returns the size of the payload for a given serial type."""
    if serial_type == 0: return 0
    if serial_type == 1: return 1
    if serial_type == 2: return 2
    if serial_type == 3: return 3
    if serial_type == 4: return 4
    if serial_type == 5: return 6
    if serial_type == 6: return 8
    if serial_type == 7: return 8
    if serial_type == 8: return 0
    if serial_type == 9: return 0
    if serial_type >= 12 and serial_type % 2 == 0:
        return (serial_type - 12) // 2
    if serial_type >= 13 and serial_type % 2 == 1:
        return (serial_type - 13) // 2
    return -1  # 10 and 11 are reserved

def decode_serial_value(serial_type: int, data: bytes, offset: int) -> Tuple[Any, int]:
    """
    Decodes a SQLite record value based on its serial type.
    Returns (value, bytes_consumed).
    """
    size = serial_type_size(serial_type)
    if size < 0 or offset + size > len(data):
        return None, size

    val_data = data[offset:offset+size]
    
    if serial_type == 0:
        return None, 0
    if serial_type == 1:
        return int.from_bytes(val_data, 'big', signed=True), 1
    if serial_type == 2:
        return int.from_bytes(val_data, 'big', signed=True), 2
    if serial_type == 3:
        return int.from_bytes(val_data, 'big', signed=True), 3
    if serial_type == 4:
        return int.from_bytes(val_data, 'big', signed=True), 4
    if serial_type == 5:
        return int.from_bytes(val_data, 'big', signed=True), 6
    if serial_type == 6:
        return int.from_bytes(val_data, 'big', signed=True), 8
    if serial_type == 7:
        if len(val_data) == 8:
            return struct.unpack('>d', val_data)[0], 8
        return None, 8
    if serial_type == 8:
        return 0, 0
    if serial_type == 9:
        return 1, 0
    if serial_type >= 12 and serial_type % 2 == 0:
        return val_data, size
    if serial_type >= 13 and serial_type % 2 == 1:
        return val_data.decode('utf-8', errors='replace'), size
    
    return None, 0

def parse_record_header(data: bytes, offset: int) -> Optional[Tuple[List[int], int]]:
    """
    Parses a SQLite record header.
    Returns (list_of_serial_types, header_size).
    """
    if offset >= len(data):
        return None
        
    header_size, consumed = decode_varint(data, offset)
    if header_size < 1 or header_size > 1000 or offset + header_size > len(data):
        return None
        
    current_offset = offset + consumed
    serial_types = []
    
    while current_offset < offset + header_size:
        serial_type, st_consumed = decode_varint(data, current_offset)
        if st_consumed == 0 or serial_type in (10, 11):
            return None
        serial_types.append(serial_type)
        current_offset += st_consumed
        
    if current_offset != offset + header_size:
        return None
        
    return serial_types, header_size

def parse_record(data: bytes, offset: int) -> Optional[Tuple[List[Any], int]]:
    """
    Parses a full SQLite record.
    Returns (list_of_values, total_bytes_consumed).
    """
    header_info = parse_record_header(data, offset)
    if not header_info:
        return None
        
    serial_types, header_size = header_info
    current_offset = offset + header_size
    values = []
    
    for serial_type in serial_types:
        val, consumed = decode_serial_value(serial_type, data, current_offset)
        if consumed < 0:
            return None
        values.append(val)
        current_offset += consumed
        
    return values, current_offset - offset

def parse_leaf_table_cell(page_data: bytes, cell_offset: int) -> Optional[Dict[str, Any]]:
    """
    Parses a B-tree leaf table cell.
    """
    if cell_offset >= len(page_data):
        return None
        
    payload_size, consumed1 = decode_varint(page_data, cell_offset)
    if consumed1 == 0:
        return None
        
    rowid, consumed2 = decode_varint(page_data, cell_offset + consumed1)
    if consumed2 == 0:
        return None
        
    record_offset = cell_offset + consumed1 + consumed2
    
    # Check if payload overflows. We don't handle overflow pages in carving currently.
    # Just parse what's here if possible.
    record_result = parse_record(page_data, record_offset)
    if not record_result:
        return None
        
    values, _ = record_result
    return {'rowid': rowid, 'values': values}

def get_cell_pointers(page_data: bytes, header: PageHeader, page_offset: int) -> List[int]:
    """
    Returns the cell pointers from a page.
    """
    pointers = []
    pointer_array_offset = page_offset + header.header_size
    for i in range(header.cell_count):
        pt_off = pointer_array_offset + (i * 2)
        if pt_off + 2 > len(page_data):
            break
        pointer = struct.unpack('>H', page_data[pt_off:pt_off+2])[0]
        pointers.append(pointer)
    return pointers

def parse_db_header(data: bytes) -> Optional[DbHeader]:
    """
    Parses the 100-byte SQLite database header.
    """
    if len(data) < 100:
        return None
    if data[:16] != SQLITE_MAGIC:
        return None
        
    try:
        page_size = struct.unpack('>H', data[16:18])[0]
        if page_size == 1:
            page_size = 65536
            
        reserved_per_page = data[20]
        first_freelist_trunk = struct.unpack('>I', data[32:36])[0]
        freelist_page_count = struct.unpack('>I', data[36:40])[0]
        text_encoding = struct.unpack('>I', data[56:60])[0]
        
        return DbHeader(
            page_size=page_size,
            reserved_per_page=reserved_per_page,
            first_freelist_trunk=first_freelist_trunk,
            freelist_page_count=freelist_page_count,
            text_encoding=text_encoding
        )
    except struct.error:
        return None

def parse_page_header(page_data: bytes, page_offset: int) -> Optional[PageHeader]:
    """
    Parses a B-Tree page header.
    """
    if page_offset + 8 > len(page_data):
        return None
        
    page_type = page_data[page_offset]
    if page_type not in (PAGE_TYPE_LEAF_TABLE, PAGE_TYPE_INTERIOR_TABLE, PAGE_TYPE_LEAF_INDEX, PAGE_TYPE_INTERIOR_INDEX):
        return None
        
    try:
        first_freeblock = struct.unpack('>H', page_data[page_offset+1:page_offset+3])[0]
        cell_count = struct.unpack('>H', page_data[page_offset+3:page_offset+5])[0]
        cell_content_offset = struct.unpack('>H', page_data[page_offset+5:page_offset+7])[0]
        if cell_content_offset == 0:
            cell_content_offset = 65536
        fragmented_free_bytes = page_data[page_offset+7]
        
        right_child = None
        if page_type in (PAGE_TYPE_INTERIOR_TABLE, PAGE_TYPE_INTERIOR_INDEX):
            if page_offset + 12 > len(page_data):
                return None
            right_child = struct.unpack('>I', page_data[page_offset+8:page_offset+12])[0]
            
        return PageHeader(
            page_type=page_type,
            first_freeblock=first_freeblock,
            cell_count=cell_count,
            cell_content_offset=cell_content_offset,
            fragmented_free_bytes=fragmented_free_bytes,
            right_child=right_child
        )
    except struct.error:
        return None

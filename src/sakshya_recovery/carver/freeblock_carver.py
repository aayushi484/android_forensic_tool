from dataclasses import dataclass
from typing import List, Tuple, Optional, Any
from .sqlite_format import (
    parse_page_header,
    parse_record,
    get_cell_pointers
)

@dataclass
class CarvedRecord:
    """Represents a record carved from SQLite free space."""
    values: List[Any]
    rowid: Optional[int]
    recovery_method: str
    source_page: int
    confidence: float

def walk_freeblocks(page_data: bytes, first_freeblock_offset: int) -> List[Tuple[int, int]]:
    """
    Walks the freeblock chain on a page.
    Returns a list of (offset, size).
    """
    freeblocks = []
    current_offset = first_freeblock_offset
    
    while current_offset != 0:
        if current_offset + 4 > len(page_data):
            break
            
        import struct
        next_offset = struct.unpack('>H', page_data[current_offset:current_offset+2])[0]
        size = struct.unpack('>H', page_data[current_offset+2:current_offset+4])[0]
        
        if size >= 4:
            freeblocks.append((current_offset, size))
            
        if next_offset == 0 or next_offset <= current_offset:
            break
            
        current_offset = next_offset
        
    return freeblocks

def carve_freeblock_records(page_data: bytes, freeblocks: List[Tuple[int, int]], page_num: int = 0) -> List[CarvedRecord]:
    """
    Attempts to carve records from freeblock regions.
    """
    carved_records = []
    
    for offset, size in freeblocks:
        data_offset = offset + 4
        # We try to parse a record directly in the freeblock data
        # Note: we don't have rowid here since we are just parsing the record format
        # If it was a deleted cell, the payload header (size, rowid) might be present or overwritten
        # For simplicity, we scan for parse_record directly in the block
        
        # We can just try at the start of the data offset
        for i in range(data_offset, offset + size):
            record_info = parse_record(page_data, i)
            if record_info:
                values, consumed = record_info
                carved_records.append(CarvedRecord(
                    values=values,
                    rowid=None,
                    recovery_method='carved_freeblock',
                    source_page=page_num,
                    confidence=1.0  # Will be adjusted by false_positive_filter
                ))
                
    return carved_records

def carve_page_freeblocks(page_data: bytes, page_offset: int = 0, page_num: int = 0) -> List[CarvedRecord]:
    """
    Carves records from freeblocks and unallocated space on a page.
    """
    header = parse_page_header(page_data, page_offset)
    if not header:
        return []
        
    records = []
    
    # 1. Walk freeblocks
    if header.first_freeblock != 0:
        freeblocks = walk_freeblocks(page_data, header.first_freeblock)
        records.extend(carve_freeblock_records(page_data, freeblocks, page_num))
        
    # 2. Unallocated space (gap between cell pointers and cell content area)
    pointers = get_cell_pointers(page_data, header, page_offset)
    pointer_array_end = page_offset + header.header_size + (header.cell_count * 2)
    
    unallocated_start = pointer_array_end
    unallocated_end = header.cell_content_offset
    
    if unallocated_start < unallocated_end and unallocated_end <= len(page_data):
        # We treat this gap as a single freeblock
        gap_size = unallocated_end - unallocated_start
        if gap_size >= 4:
            records.extend(carve_freeblock_records(page_data, [(unallocated_start, gap_size)], page_num))
            
    return records

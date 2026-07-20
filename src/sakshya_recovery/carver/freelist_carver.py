import struct
from typing import Dict, List
from .sqlite_format import DbHeader, parse_record
from .freeblock_carver import CarvedRecord

def walk_freelist_chain(db_data: bytes, page_size: int, first_trunk_page: int) -> Dict[str, List[int]]:
    """
    Walks the SQLite freelist chain and returns trunk and leaf pages.
    """
    trunk_pages = []
    leaf_pages = []
    
    current_trunk = first_trunk_page
    visited = set()
    
    while current_trunk != 0 and current_trunk not in visited:
        visited.add(current_trunk)
        trunk_pages.append(current_trunk)
        
        offset = (current_trunk - 1) * page_size
        if offset + 8 > len(db_data):
            break
            
        next_trunk = struct.unpack('>I', db_data[offset:offset+4])[0]
        leaf_count = struct.unpack('>I', db_data[offset+4:offset+8])[0]
        
        if offset + 8 + (leaf_count * 4) > len(db_data):
            break
            
        for i in range(leaf_count):
            leaf_offset = offset + 8 + (i * 4)
            leaf_page = struct.unpack('>I', db_data[leaf_offset:leaf_offset+4])[0]
            leaf_pages.append(leaf_page)
            
        current_trunk = next_trunk
        
    return {'trunk_pages': trunk_pages, 'leaf_pages': leaf_pages}

def carve_freelist_page(db_data: bytes, page_number: int, page_size: int) -> List[CarvedRecord]:
    """
    Carves records from a freelist page.
    """
    records = []
    offset = (page_number - 1) * page_size
    if offset < 0 or offset + page_size > len(db_data):
        return records
        
    page_data = db_data[offset:offset+page_size]
    
    # Check if it looks like a valid page (could have been re-used but not wiped)
    if len(page_data) > 0 and page_data[0] in (0x02, 0x05, 0x0A, 0x0D):
        from .freeblock_carver import carve_page_freeblocks
        # Even if it looks like a valid page, it's in the freelist, so we carve the whole thing
        # Since it's unstructured in nature (freelist), we just try to scan it for records.
        pass
        
    # Scan through the page for records
    i = 0
    while i < len(page_data) - 4:
        record_info = parse_record(page_data, i)
        if record_info:
            values, consumed = record_info
            if consumed > 0:
                records.append(CarvedRecord(
                    values=values,
                    rowid=None,
                    recovery_method='carved_freelist',
                    source_page=page_number,
                    confidence=1.0
                ))
                i += consumed
                continue
        i += 1
        
    return records

def carve_all_freelist(db_data: bytes, header: DbHeader) -> List[CarvedRecord]:
    """
    Carves all pages in the freelist.
    """
    all_records = []
    if header.first_freelist_trunk == 0:
        return all_records
        
    freelist_info = walk_freelist_chain(db_data, header.page_size, header.first_freelist_trunk)
    
    for page_num in freelist_info['trunk_pages'] + freelist_info['leaf_pages']:
        all_records.extend(carve_freelist_page(db_data, page_num, header.page_size))
        
    return all_records

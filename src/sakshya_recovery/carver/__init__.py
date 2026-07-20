import hashlib
from typing import List

from .sqlite_format import parse_db_header
from .freeblock_carver import CarvedRecord, carve_page_freeblocks
from .freelist_carver import carve_all_freelist
from .unstructured_fallback import extract_text_strings, extract_strings_from_region
from .false_positive_filter import filter_carved_records

__all__ = [
    'CarvedRecord',
    'carve_sqlite_db',
    'parse_db_header',
    'carve_page_freeblocks',
    'carve_all_freelist',
    'extract_text_strings',
    'extract_strings_from_region',
    'filter_carved_records'
]

def carve_sqlite_db(db_path: str) -> List[CarvedRecord]:
    """
    Main entry point for carving an SQLite database.
    """
    try:
        with open(db_path, 'rb') as f:
            db_data = f.read()
    except Exception:
        return []
        
    if not db_data:
        return []
        
    header = parse_db_header(db_data)
    if not header:
        return []
        
    all_records = []
    
    # 3. Run freelist carving
    freelist_records = carve_all_freelist(db_data, header)
    all_records.extend(freelist_records)
    
    # 4. Run freeblock carving for each page
    total_pages = len(db_data) // header.page_size
    for i in range(total_pages):
        page_num = i + 1
        page_offset = i * header.page_size
        
        # Page 1 has 100 byte offset for b-tree header
        btree_offset = 100 if page_num == 1 else 0
        
        page_data = db_data[page_offset:page_offset+header.page_size]
        if len(page_data) < header.page_size:
            continue
            
        freeblock_records = carve_page_freeblocks(page_data, page_offset=btree_offset, page_num=page_num)
        all_records.extend(freeblock_records)
        
    # 5. Unstructured fallback (skipped here for structured records, unstructured can be added directly if needed)
    
    # 6. False positive filter
    filtered_records = filter_carved_records(all_records, min_score=0.3)
    
    # 7. Deduplicate (by record content hash)
    unique_records = {}
    for r in filtered_records:
        # Create a hash of the values
        value_repr = str(r.values).encode('utf-8')
        h = hashlib.md5(value_repr).hexdigest()
        
        if h not in unique_records or unique_records[h].confidence < r.confidence:
            unique_records[h] = r
            
    # 8. Sort by source page
    final_list = list(unique_records.values())
    final_list.sort(key=lambda x: x.source_page)
    
    return final_list

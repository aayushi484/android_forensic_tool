from typing import List, Tuple

def extract_text_strings(data: bytes, min_len: int = 6) -> List[Tuple[str, int]]:
    """
    Extracts printable UTF-8 and ASCII strings from binary data.
    Returns a list of (string, offset).
    """
    strings = []
    current_string = bytearray()
    start_offset = 0
    i = 0
    
    while i < len(data):
        b = data[i]
        
        # Check for ASCII printable
        if 32 <= b <= 126:
            if not current_string:
                start_offset = i
            current_string.append(b)
            i += 1
            continue
            
        # Check for UTF-8 multibyte sequence
        if (b & 0xE0) == 0xC0 and i + 1 < len(data) and (data[i+1] & 0xC0) == 0x80:
            if not current_string:
                start_offset = i
            current_string.extend(data[i:i+2])
            i += 2
            continue
            
        if (b & 0xF0) == 0xE0 and i + 2 < len(data) and (data[i+1] & 0xC0) == 0x80 and (data[i+2] & 0xC0) == 0x80:
            if not current_string:
                start_offset = i
            current_string.extend(data[i:i+3])
            i += 3
            continue
            
        if (b & 0xF8) == 0xF0 and i + 3 < len(data) and (data[i+1] & 0xC0) == 0x80 and (data[i+2] & 0xC0) == 0x80 and (data[i+3] & 0xC0) == 0x80:
            if not current_string:
                start_offset = i
            current_string.extend(data[i:i+4])
            i += 4
            continue
            
        # Not printable or valid UTF-8 sequence, finish current string
        if current_string:
            try:
                decoded = current_string.decode('utf-8')
                if len(decoded) >= min_len:
                    strings.append((decoded, start_offset))
            except UnicodeDecodeError:
                pass
            current_string = bytearray()
            
        i += 1
        
    if current_string:
        try:
            decoded = current_string.decode('utf-8')
            if len(decoded) >= min_len:
                strings.append((decoded, start_offset))
        except UnicodeDecodeError:
            pass
            
    return strings

def extract_strings_from_region(data: bytes, offset: int, size: int, min_len: int = 6) -> List[Tuple[str, int]]:
    """
    Extracts strings from a specific region.
    """
    region = data[offset:offset+size]
    strings = extract_text_strings(region, min_len)
    
    return [(s, offset + o) for s, o in strings]

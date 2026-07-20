from dataclasses import dataclass
from typing import List
from .freeblock_carver import CarvedRecord
import math

@dataclass
class CarvedRecordScore:
    score: float
    reasons: List[str]
    is_likely_genuine: bool

def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    entropy_val = 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    for count in counts:
        if count > 0:
            p = count / len(data)
            entropy_val -= p * math.log2(p)
    return entropy_val

def score_carved_record(record: CarvedRecord) -> CarvedRecordScore:
    """
    Applies heuristic rules to score a carved record.
    """
    score = 1.0
    reasons = []
    
    if len(record.values) <= 1:
        score -= 0.2
        reasons.append("suspiciously few fields (0-1)")
        
    if record.recovery_method in ('carved_freeblock', 'carved_freelist'):
        score += 0.3
        reasons.append("structurally parsed")
        
    for val in record.values:
        if isinstance(val, str):
            # Entropy check on text values
            val_bytes = val.encode('utf-8', errors='ignore')
            if len(val_bytes) > 10:
                ent = entropy(val_bytes)
                if ent > 6.5:
                    score -= 0.3
                    reasons.append("high entropy text (>6.5)")
                    
            # Printable ratio
            printable_count = sum(1 for c in val if 32 <= ord(c) <= 126 or ord(c) > 127)
            if len(val) > 0 and (printable_count / len(val)) < 0.7:
                score -= 0.4
                reasons.append("low printable ratio (<70%)")
                
            # Known garbage patterns
            val_upper = val.upper()
            if len(val) >= 16 and all(c in '0123456789ABCDEFabcdef' for c in val):
                score -= 0.5
                reasons.append("hex ID")
            if any(op in val_upper for op in ('INSERT INTO', 'UPDATE ', 'DELETE FROM', 'SELECT ')):
                score -= 0.5
                reasons.append("SQL operation string")
            if any(path in val for path in ('C:\\', '/data/', '/system/')):
                score -= 0.5
                reasons.append("filesystem path")
                
    score = max(0.0, min(1.0, score))
    is_likely_genuine = score >= 0.3
    
    return CarvedRecordScore(
        score=score,
        reasons=reasons,
        is_likely_genuine=is_likely_genuine
    )

def filter_carved_records(records: List[CarvedRecord], min_score: float = 0.3) -> List[CarvedRecord]:
    """
    Filters carved records based on minimum score.
    """
    filtered = []
    for record in records:
        record_score = score_carved_record(record)
        if record_score.is_likely_genuine and record_score.score >= min_score:
            record.confidence = record_score.score
            filtered.append(record)
    return filtered

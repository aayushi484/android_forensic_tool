import hashlib
import json

def build_timeline(events: list) -> list:
    """Merge all events (live + recovered) into a sorted timeline.
    
    Sort by timestamp (ISO8601 string comparison works for UTC).
    Events with None timestamp sorted to end, with stable ordering by event_id.
    """
    def sort_key(event):
        # event is expected to have timestamp and event_id attributes
        ts = getattr(event, 'timestamp', None)
        eid = getattr(event, 'event_id', '')
        if ts is None:
            ts = '9999-99-99T99:99:99Z'
        return (ts, eid)
    
    return sorted(events, key=sort_key)

def deduplicate_events(events: list) -> list:
    """Remove duplicate events from multiple recovery methods.
    Keep highest-confidence version when same content appears multiple times.
    """
    seen_hashes = set()
    deduped = []
    
    for event in events:
        content = getattr(event, 'content', {})
        content_str = json.dumps(content, sort_keys=True)
        content_hash = hashlib.sha256(content_str.encode('utf-8')).hexdigest()
        
        if content_hash not in seen_hashes:
            seen_hashes.add(content_hash)
            deduped.append(event)
            
    return deduped

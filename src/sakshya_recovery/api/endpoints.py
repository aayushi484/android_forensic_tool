import os
import json
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="Sakshya API")

CASE_OUTPUT_DIR = os.getenv("CASE_OUTPUT_DIR", "test_output")
# Assuming api is one level deep inside sakshya_recovery, so package root is parent of parent
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FULL_OUTPUT_DIR = os.path.join(BASE_DIR, CASE_OUTPUT_DIR)

def get_case_dir(case_id: str) -> str:
    return os.path.join(FULL_OUTPUT_DIR, case_id)

def load_case_events(case_id: str) -> list:
    case_dir = get_case_dir(case_id)
    if not os.path.exists(case_dir):
        raise HTTPException(status_code=404, detail="Case not found")
        
    events_file = os.path.join(case_dir, "events.json")
    if not os.path.exists(events_file):
        return []
        
    with open(events_file, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/cases")
def list_cases():
    if not os.path.exists(FULL_OUTPUT_DIR):
        return []
    return [d for d in os.listdir(FULL_OUTPUT_DIR) if os.path.isdir(os.path.join(FULL_OUTPUT_DIR, d))]

@app.get("/case/{case_id}/events")
def get_events(case_id: str, 
               keyword: str = Query(None), 
               date_from: str = Query(None), 
               date_to: str = Query(None), 
               deletion_state: str = Query(None), 
               app_name: str = Query(None, alias="app")):
    events = load_case_events(case_id)
    return events

@app.get("/case/{case_id}/audit-log")
def get_audit_log(case_id: str):
    case_dir = get_case_dir(case_id)
    if not os.path.exists(case_dir):
        raise HTTPException(status_code=404, detail="Case not found")
        
    audit_file = os.path.join(case_dir, "audit_log.json")
    if not os.path.exists(audit_file):
        return []
        
    with open(audit_file, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/case/{case_id}/timeline")
def get_timeline(case_id: str):
    events = load_case_events(case_id)
    
    class DictEvent:
        def __init__(self, d):
            self.__dict__.update(d)
            self.timestamp = d.get('timestamp')
            self.event_id = d.get('event_id')
            self.content = d.get('content', {})
            
    event_objs = [DictEvent(e) for e in events]
    
    from sakshya_recovery.triage.timeline import build_timeline
    timeline_objs = build_timeline(event_objs)
    
    return [e.__dict__ for e in timeline_objs]

@app.get("/case/{case_id}/red-flags")
def get_red_flags(case_id: str):
    events = load_case_events(case_id)
    red_flags = []
    for event in events:
        content = event.get('content', {})
        if 'red_flag_hit' in content or event.get('red_flag_hit'):
            red_flags.append(event)
    return red_flags

@app.post("/case/{case_id}/recover")
def trigger_recovery(case_id: str):
    case_dir = get_case_dir(case_id)
    if not os.path.exists(case_dir):
        raise HTTPException(status_code=404, detail="Case not found")
        
    # Logic to load CaseBundle and run recovery would go here
    return {"status": "success", "message": f"Recovery triggered for case {case_id}"}

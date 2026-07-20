"""
sakshya_acquisition — DEVELOPMENT SHIM.

Faithful implementation of Harshit's sakshya-acquisition contract,
used for development and testing until the real package is available.

WARNING: This shim MUST be replaced with Harshit's real package before
the sakshya-recovery package is considered done. See Component 11
(Mandatory Shim-Swap Integration Gate) in the implementation plan.

Contract source: §2 of the sakshya-recovery spec.
"""

from dataclasses import dataclass, fields, asdict
from typing import Optional
import hashlib
import json
import os

EVENT_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class Event:
    """A single forensic event — frozen (immutable) after creation.

    All events received from acquisition have deletion_state='live'
    and recovery_method='live'. The recovery package creates new Event
    instances with different values for recovered data.
    """

    event_id: str  # deterministic hash-derived ID
    timestamp: Optional[str]  # ISO8601 UTC, or None if unrecoverable
    app: str  # "sms" | "call_log" | "contacts" | "media" | "whatsapp" | "device_info"
    event_type: str  # "call" | "sms" | "contact" | "media" | "chat" | "location" | "meta"
    direction: Optional[str]
    party: Optional[str]
    content: dict
    deletion_state: str  # "live" | "deleted"
    recovery_method: str  # "live" | "carved_freelist" | "carved_freeblock" | etc.
    source_file: str
    integrity_hash: str
    amount: Optional[float] = None
    currency: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    exif_time: Optional[str] = None

    def compute_hash(self) -> str:
        """Deterministic SHA-256 hash of all non-hash fields."""
        d = asdict(self)
        d.pop("integrity_hash", None)
        d.pop("event_id", None)
        canonical = json.dumps(d, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        """Convert to plain dict for JSON serialization."""
        return asdict(self)


def make_event_id(content_hash: str, source_file: str, index: int = 0) -> str:
    """Deterministic event ID — no uuid4, no randomness."""
    seed = f"{content_hash}:{source_file}:{index}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


@dataclass
class CaseBundle:
    """A case containing events and an audit trail.

    events is a mutable list — the recovery package appends to it.
    audit_log_path points to the JSONL file that BOTH packages write to
    (acquisition starts the chain, recovery continues it).
    """

    case_id: str  # "CASE_{device_id}_{acquired_at_compact}"
    device_id: str
    schema_version: str  # must match EVENT_SCHEMA_VERSION
    events: list  # list[Event]
    audit_log_path: str  # path to the audit_log.jsonl

    def seal(self) -> dict:
        """Produce a tamper-evident summary of the case."""
        events_json = self.to_json()
        canonical = json.dumps(events_json, sort_keys=True, ensure_ascii=False)
        return {
            "case_id": self.case_id,
            "device_id": self.device_id,
            "schema_version": self.schema_version,
            "event_count": len(self.events),
            "events_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }

    def to_json(self) -> list[dict]:
        """Serialize all events to a list of dicts. Deterministic output."""
        return [e.to_dict() for e in self.events]


class AuditLog:
    """Hash-chained, append-only audit log.

    Continues an existing chain if the file already has entries
    (i.e., when recovery appends to acquisition's log).
    """

    def __init__(self, path: str):
        self.path = path
        self.last_hash = "0" * 64  # genesis hash
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        self.last_hash = entry["entry_hash"]

    def log(self, action: str, details: dict, timestamp: Optional[str] = None):
        """Append a hash-chained entry to the audit log.

        If timestamp is None, uses current UTC time. For deterministic
        replay, pass an explicit timestamp.
        """
        if timestamp is None:
            from datetime import datetime, timezone

            timestamp = datetime.now(timezone.utc).isoformat()

        entry = {
            "timestamp": timestamp,
            "action": action,
            "details": details,
            "prev_hash": self.last_hash,
        }
        entry_str = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        entry_hash = hashlib.sha256(entry_str.encode("utf-8")).hexdigest()
        entry["entry_hash"] = entry_hash

        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        self.last_hash = entry_hash
        return entry_hash


def verify_audit_chain(log_path: str) -> bool:
    """Verify the entire audit chain. Returns True if intact."""
    with open(log_path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    expected_prev = "0" * 64
    for i, line in enumerate(lines):
        entry = json.loads(line)
        stored_hash = entry.pop("entry_hash")

        if entry["prev_hash"] != expected_prev:
            return False

        recomputed = hashlib.sha256(
            json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        if recomputed != stored_hash:
            return False

        expected_prev = stored_hash

    return True


def _hash_file(path: str) -> str:
    """SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_acquisition(
    device_id: str = "TEST_DEVICE_01",
    fixture_mode: bool = False,
    pull_full_files: bool = True,
    fixture_dir: Optional[str] = None,
) -> "CaseBundle":
    """Run acquisition (shim version).

    In fixture_mode, builds a CaseBundle from test fixture databases
    rather than connecting to a real device via ADB.
    """
    if not fixture_mode:
        raise RuntimeError(
            "This is the sakshya_acquisition shim. Only fixture_mode=True is supported. "
            "Install Harshit's real sakshya-acquisition package for live device acquisition."
        )

    import sqlite3
    import tempfile
    import shutil

    # Locate fixtures
    if fixture_dir is None:
        # Look relative to this file, then relative to cwd
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "..", "fixtures"),
            os.path.join(os.getcwd(), "fixtures"),
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "fixtures"),
        ]
        for c in candidates:
            if os.path.isdir(c):
                fixture_dir = os.path.abspath(c)
                break
        if fixture_dir is None:
            raise FileNotFoundError(
                f"Cannot locate fixtures/ directory. Searched: {candidates}"
            )

    # Create case directory
    case_id = f"CASE_{device_id}_20260719T000000"
    case_dir = os.path.join(fixture_dir, "..", "test_output", case_id)
    os.makedirs(case_dir, exist_ok=True)

    # Initialize audit log
    audit_path = os.path.join(case_dir, "audit_log.jsonl")
    # Remove old log if exists (for deterministic reruns)
    if os.path.exists(audit_path):
        os.remove(audit_path)
    audit = AuditLog(audit_path)
    audit.log("case_opened", {"device_id": device_id, "case_id": case_id, "fixture_mode": True})

    events: list[Event] = []

    # --- Parse SMS database fixture ---
    sms_db = os.path.join(fixture_dir, "emulator_mmssms_delete_test.db")
    if os.path.exists(sms_db):
        file_hash = _hash_file(sms_db)
        audit.log("acquire_artifact", {"type": "sms_db", "path": sms_db, "sha256": file_hash})
        try:
            conn = sqlite3.connect(f"file:{sms_db}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT _id, address, date, body, type, read FROM sms ORDER BY date"
            )
            for idx, row in enumerate(cursor.fetchall()):
                ts = None
                if row["date"]:
                    from datetime import datetime, timezone

                    try:
                        ts = datetime.fromtimestamp(
                            int(row["date"]) / 1000, tz=timezone.utc
                        ).isoformat()
                    except (ValueError, OSError):
                        pass
                content = {
                    "body": row["body"] or "",
                    "address": row["address"] or "",
                    "type": row["type"],
                    "read": row["read"],
                    "_id": row["_id"],
                }
                content_hash = hashlib.sha256(
                    json.dumps(content, sort_keys=True).encode()
                ).hexdigest()
                eid = make_event_id(content_hash, sms_db, idx)
                events.append(
                    Event(
                        event_id=eid,
                        timestamp=ts,
                        app="sms",
                        event_type="sms",
                        direction="in" if row["type"] == 1 else "out",
                        party=row["address"],
                        content=content,
                        deletion_state="live",
                        recovery_method="live",
                        source_file=sms_db,
                        integrity_hash=file_hash,
                    )
                )
            conn.close()
        except Exception as e:
            audit.log("sms_parse_error", {"error": str(e)})

    # --- Parse chat_test.db fixture ---
    chat_db = os.path.join(fixture_dir, "chat_test.db")
    if os.path.exists(chat_db):
        file_hash = _hash_file(chat_db)
        audit.log(
            "acquire_artifact", {"type": "chat_db", "path": chat_db, "sha256": file_hash}
        )
        try:
            conn = sqlite3.connect(f"file:{chat_db}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM messages ORDER BY timestamp")
            for idx, row in enumerate(cursor.fetchall()):
                from datetime import datetime, timezone

                ts = None
                if row["timestamp"]:
                    try:
                        ts = datetime.fromtimestamp(
                            int(row["timestamp"]), tz=timezone.utc
                        ).isoformat()
                    except (ValueError, OSError):
                        pass
                content = {
                    "body": row["body"] or "",
                    "sender": row["sender"] or "",
                    "id": row["id"],
                }
                content_hash = hashlib.sha256(
                    json.dumps(content, sort_keys=True).encode()
                ).hexdigest()
                eid = make_event_id(content_hash, chat_db, idx)
                events.append(
                    Event(
                        event_id=eid,
                        timestamp=ts,
                        app="sms",
                        event_type="chat",
                        direction=None,
                        party=row["sender"],
                        content=content,
                        deletion_state="live",
                        recovery_method="live",
                        source_file=chat_db,
                        integrity_hash=file_hash,
                    )
                )
            conn.close()
        except Exception as e:
            audit.log("chat_parse_error", {"error": str(e)})

    # --- WhatsApp encrypted backup reference ---
    wa_crypt = os.path.join(fixture_dir, "whatsapp", "msgstore.db.crypt14")
    wa_key = os.path.join(fixture_dir, "whatsapp", "whatsapp_key")
    if os.path.exists(wa_crypt) and os.path.exists(wa_key):
        crypt_hash = _hash_file(wa_crypt)
        key_hash = _hash_file(wa_key)
        audit.log(
            "acquire_artifact",
            {"type": "whatsapp_backup", "crypt_path": wa_crypt, "key_path": wa_key,
             "crypt_sha256": crypt_hash, "key_sha256": key_hash},
        )
        content_hash = hashlib.sha256(
            f"{crypt_hash}:{key_hash}".encode()
        ).hexdigest()
        eid = make_event_id(content_hash, wa_crypt, 0)
        events.append(
            Event(
                event_id=eid,
                timestamp=None,
                app="whatsapp",
                event_type="chat",
                direction=None,
                party=None,
                content={
                    "encrypted_db_path": wa_crypt,
                    "key_path": wa_key,
                    "crypt_version": "crypt14",
                },
                deletion_state="live",
                recovery_method="live",
                source_file=wa_crypt,
                integrity_hash=crypt_hash,
            )
        )

    audit.log("acquisition_complete", {"event_count": len(events)})

    return CaseBundle(
        case_id=case_id,
        device_id=device_id,
        schema_version=EVENT_SCHEMA_VERSION,
        events=events,
        audit_log_path=audit_path,
    )

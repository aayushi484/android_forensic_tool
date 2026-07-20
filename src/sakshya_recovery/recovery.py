"""
recovery.py — run_recovery() entry point.

Takes a CaseBundle from sakshya_acquisition (all events deletion_state='live'),
runs SQLite carving, WhatsApp decrypt+carve, trash media recovery, timeline
fusion, and RED-FLAG keyword matching. Returns the updated CaseBundle with
recovered events appended.

Deterministic: running this twice on the same input CaseBundle produces
byte-identical case.to_json() output. No uuid4(), no datetime.now() in
any event data.
"""

import hashlib
import json
import os
from typing import Optional

from sakshya_acquisition import AuditLog, CaseBundle, Event, make_event_id


def _hash_file(path: str) -> str:
    """SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_source_files(case: CaseBundle) -> dict[str, str]:
    """Collect all unique source file paths from the case and hash them.

    Returns {path: sha256_hash} for every file that exists on disk.
    """
    paths = set()
    for event in case.events:
        if event.source_file and os.path.isfile(event.source_file):
            paths.add(event.source_file)
        # Also collect associated WAL/journal/shm files
        for ext in ("-wal", "-journal", "-shm"):
            companion = event.source_file + ext
            if os.path.isfile(companion):
                paths.add(companion)
        # WhatsApp-specific: key and encrypted DB
        if event.app == "whatsapp" and isinstance(event.content, dict):
            for key in ("encrypted_db_path", "key_path"):
                p = event.content.get(key)
                if p and os.path.isfile(p):
                    paths.add(p)

    return {p: _hash_file(p) for p in sorted(paths)}


def _make_recovered_event(
    *,
    content: dict,
    app: str,
    event_type: str,
    recovery_method: str,
    source_file: str,
    integrity_hash: str,
    timestamp: Optional[str] = None,
    direction: Optional[str] = None,
    party: Optional[str] = None,
    amount: Optional[float] = None,
    currency: Optional[str] = None,
    gps_lat: Optional[float] = None,
    gps_lon: Optional[float] = None,
    exif_time: Optional[str] = None,
    index: int = 0,
) -> Event:
    """Create a recovered Event with deterministic ID."""
    content_canonical = json.dumps(content, sort_keys=True, ensure_ascii=False)
    content_hash = hashlib.sha256(content_canonical.encode("utf-8")).hexdigest()
    event_id = make_event_id(content_hash, source_file, index)

    return Event(
        event_id=event_id,
        timestamp=timestamp,
        app=app,
        event_type=event_type,
        direction=direction,
        party=party,
        content=content,
        deletion_state="deleted",
        recovery_method=recovery_method,
        source_file=source_file,
        integrity_hash=integrity_hash,
        amount=amount,
        currency=currency,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        exif_time=exif_time,
    )


def _run_sqlite_carving(case: CaseBundle, audit: AuditLog) -> list[Event]:
    """Run SQLite b-tree carving on all local SQLite sources."""
    from sakshya_recovery.carver import carve_sqlite_db

    recovered = []
    seen_sources = set()

    for event in case.events:
        source = event.source_file
        if not source or source in seen_sources:
            continue
        if not os.path.isfile(source):
            continue
        # Only carve SQLite databases (check magic header)
        try:
            with open(source, "rb") as f:
                magic = f.read(16)
            if magic != b"SQLite format 3\x00":
                continue
        except (IOError, OSError):
            continue

        seen_sources.add(source)
        file_hash = _hash_file(source)

        audit.log("carve_sqlite_start", {"path": source, "sha256": file_hash})

        try:
            carved_records = carve_sqlite_db(source)
            audit.log(
                "carve_sqlite_complete",
                {"path": source, "records_found": len(carved_records)},
            )

            for idx, record in enumerate(carved_records):
                content = {
                    "values": [
                        v if not isinstance(v, bytes) else v.hex()
                        for v in (record.values or [])
                    ],
                    "strings": record.strings if hasattr(record, "strings") else [],
                    "source_page": record.source_page,
                    "confidence": record.confidence,
                }
                recovered.append(
                    _make_recovered_event(
                        content=content,
                        app=event.app,
                        event_type=event.event_type,
                        recovery_method=record.recovery_method,
                        source_file=source,
                        integrity_hash=file_hash,
                        index=idx,
                    )
                )
        except Exception as e:
            audit.log("carve_sqlite_error", {"path": source, "error": str(e)})

    return recovered


def _run_wal_journal_recovery(case: CaseBundle, audit: AuditLog) -> list[Event]:
    """Run WAL and journal recovery on all SQLite sources."""
    from sakshya_recovery.wal_journal.wal_recovery import recover_from_wal
    from sakshya_recovery.wal_journal.journal_recovery import recover_from_journal

    recovered = []
    seen_sources = set()

    for event in case.events:
        source = event.source_file
        if not source or source in seen_sources:
            continue
        if not os.path.isfile(source):
            continue
        seen_sources.add(source)
        file_hash = _hash_file(source)

        # WAL recovery
        wal_path = source + "-wal"
        if os.path.isfile(wal_path):
            audit.log("recover_wal_start", {"db_path": source, "wal_path": wal_path})
            try:
                wal_records = recover_from_wal(source, wal_path)
                audit.log(
                    "recover_wal_complete",
                    {"wal_path": wal_path, "records_found": len(wal_records)},
                )
                for idx, rec in enumerate(wal_records):
                    content = {
                        "values": rec.get("values"),
                        "strings": rec.get("strings"),
                        "page_number": rec.get("page_number"),
                        "frame_index": rec.get("frame_index"),
                    }
                    recovered.append(
                        _make_recovered_event(
                            content=content,
                            app=event.app,
                            event_type=event.event_type,
                            recovery_method="wal_recovery",
                            source_file=wal_path,
                            integrity_hash=_hash_file(wal_path),
                            index=idx,
                        )
                    )
            except Exception as e:
                audit.log("recover_wal_error", {"wal_path": wal_path, "error": str(e)})

        # Journal recovery
        journal_path = source + "-journal"
        if os.path.isfile(journal_path):
            audit.log(
                "recover_journal_start",
                {"db_path": source, "journal_path": journal_path},
            )
            try:
                journal_records = recover_from_journal(source, journal_path)
                audit.log(
                    "recover_journal_complete",
                    {"journal_path": journal_path, "records_found": len(journal_records)},
                )
                for idx, rec in enumerate(journal_records):
                    content = {
                        "values": rec.get("values"),
                        "strings": rec.get("strings"),
                        "page_number": rec.get("page_number"),
                    }
                    recovered.append(
                        _make_recovered_event(
                            content=content,
                            app=event.app,
                            event_type=event.event_type,
                            recovery_method="journal_recovery",
                            source_file=journal_path,
                            integrity_hash=_hash_file(journal_path),
                            index=idx,
                        )
                    )
            except Exception as e:
                audit.log(
                    "recover_journal_error",
                    {"journal_path": journal_path, "error": str(e)},
                )

    return recovered


def _run_whatsapp_recovery(case: CaseBundle, audit: AuditLog) -> list[Event]:
    """Decrypt WhatsApp backup and carve for deleted chats."""
    from sakshya_recovery.whatsapp.decrypt import decrypt_whatsapp_backup
    from sakshya_recovery.whatsapp.chat_carve import carve_whatsapp_deleted_chats

    recovered = []

    for event in case.events:
        if event.app != "whatsapp":
            continue
        if not isinstance(event.content, dict):
            continue

        crypt_path = event.content.get("encrypted_db_path")
        key_path = event.content.get("key_path")
        if not crypt_path or not key_path:
            continue
        if not os.path.isfile(crypt_path) or not os.path.isfile(key_path):
            continue

        audit.log(
            "whatsapp_decrypt_start",
            {"crypt_path": crypt_path, "key_path": key_path},
        )

        try:
            # Decrypt
            decrypted_bytes = decrypt_whatsapp_backup(key_path, crypt_path)

            # Write decrypted DB to temp file for carving
            case_dir = os.path.dirname(case.audit_log_path)
            decrypted_path = os.path.join(case_dir, "whatsapp_decrypted.db")
            with open(decrypted_path, "wb") as f:
                f.write(decrypted_bytes)

            decrypted_hash = hashlib.sha256(decrypted_bytes).hexdigest()
            audit.log(
                "whatsapp_decrypt_complete",
                {
                    "decrypted_path": decrypted_path,
                    "decrypted_sha256": decrypted_hash,
                    "size_bytes": len(decrypted_bytes),
                },
            )

            # Carve for deleted chats
            audit.log("whatsapp_carve_start", {"path": decrypted_path})
            chat_records = carve_whatsapp_deleted_chats(decrypted_path)
            audit.log(
                "whatsapp_carve_complete",
                {"path": decrypted_path, "records_found": len(chat_records)},
            )

            for idx, rec in enumerate(chat_records):
                content = {
                    "text": rec.get("text", ""),
                    "sender_jid": rec.get("sender_jid"),
                    "wa_timestamp": rec.get("timestamp"),
                    "key_id": rec.get("key_id"),
                    "deletion_type": rec.get("deletion_type", "hard_delete"),
                    "confidence": rec.get("confidence", 0.5),
                }

                # Try to extract timestamp
                ts = None
                if rec.get("timestamp"):
                    try:
                        from datetime import datetime, timezone

                        ts = datetime.fromtimestamp(
                            int(rec["timestamp"]) / 1000, tz=timezone.utc
                        ).isoformat()
                    except (ValueError, OSError, TypeError):
                        pass

                recovered.append(
                    _make_recovered_event(
                        content=content,
                        app="whatsapp",
                        event_type="chat",
                        recovery_method=rec.get("recovery_method", "whatsapp_carved"),
                        source_file=crypt_path,
                        integrity_hash=event.integrity_hash,
                        timestamp=ts,
                        index=idx,
                    )
                )

        except Exception as e:
            audit.log(
                "whatsapp_recovery_error",
                {"crypt_path": crypt_path, "error": str(e), "error_type": type(e).__name__},
            )

    return recovered


def _run_media_recovery(case: CaseBundle, audit: AuditLog) -> list[Event]:
    """Recover recently-deleted media from Android Trash locations."""
    from sakshya_recovery.media.trash_recovery import recover_trashed_files

    media_paths = []
    for event in case.events:
        if event.app == "media" and event.source_file:
            # Collect directory of media sources
            parent = os.path.dirname(event.source_file)
            if parent and os.path.isdir(parent):
                media_paths.append(parent)

    if not media_paths:
        return []

    audit.log("media_trash_recovery_start", {"search_paths": media_paths})

    try:
        trashed = recover_trashed_files(media_paths)
        audit.log(
            "media_trash_recovery_complete", {"files_found": len(trashed)}
        )

        recovered = []
        for idx, item in enumerate(trashed):
            content = {
                "original_path": item.get("original_path"),
                "trash_path": item.get("trash_path"),
                "file_hash": item.get("file_hash"),
                "size": item.get("size"),
            }
            recovered.append(
                _make_recovered_event(
                    content=content,
                    app="media",
                    event_type="media",
                    recovery_method="trash_recovery",
                    source_file=item.get("trash_path", ""),
                    integrity_hash=item.get("file_hash", ""),
                    index=idx,
                )
            )
        return recovered

    except Exception as e:
        audit.log("media_trash_recovery_error", {"error": str(e)})
        return []


def _run_keyword_matching(events: list[Event], audit: AuditLog) -> list[Event]:
    """Run RED-FLAG keyword matching across all events.

    Returns a NEW list of events — events with keyword hits have
    red_flag_hit entries added to their content dict. Since Event is
    frozen, we create new Event instances for hits.
    """
    from sakshya_recovery.triage.keyword_match import match_keywords

    result = []
    total_hits = 0

    for event in events:
        # Extract text content to search
        text_parts = []
        if isinstance(event.content, dict):
            for key in ("body", "text", "recovered_string", "original_path"):
                val = event.content.get(key)
                if isinstance(val, str):
                    text_parts.append(val)
            # Also check values list
            values = event.content.get("values")
            if isinstance(values, list):
                for v in values:
                    if isinstance(v, str):
                        text_parts.append(v)
            # Check strings list
            strings = event.content.get("strings")
            if isinstance(strings, list):
                for s in strings:
                    if isinstance(s, str):
                        text_parts.append(s)

        if not text_parts:
            result.append(event)
            continue

        combined_text = " ".join(text_parts)
        hits = match_keywords(combined_text)

        if hits:
            total_hits += 1
            # Create new Event with red_flag_hit in content
            new_content = dict(event.content)
            new_content["red_flag_hit"] = [
                {"keyword": h["keyword"], "match_type": h["match_type"], "score": h["score"]}
                for h in hits
            ]
            # Re-derive event_id since content changed
            content_canonical = json.dumps(new_content, sort_keys=True, ensure_ascii=False)
            content_hash = hashlib.sha256(content_canonical.encode("utf-8")).hexdigest()
            new_id = make_event_id(content_hash, event.source_file, 0)

            result.append(
                Event(
                    event_id=new_id,
                    timestamp=event.timestamp,
                    app=event.app,
                    event_type=event.event_type,
                    direction=event.direction,
                    party=event.party,
                    content=new_content,
                    deletion_state=event.deletion_state,
                    recovery_method=event.recovery_method,
                    source_file=event.source_file,
                    integrity_hash=event.integrity_hash,
                    amount=event.amount,
                    currency=event.currency,
                    gps_lat=event.gps_lat,
                    gps_lon=event.gps_lon,
                    exif_time=event.exif_time,
                )
            )
        else:
            result.append(event)

    audit.log("keyword_matching_complete", {"total_events": len(events), "events_with_hits": total_hits})
    return result


def run_recovery(case: CaseBundle) -> CaseBundle:
    """Run full recovery pipeline on a CaseBundle.

    Takes Harshit's CaseBundle (all events deletion_state='live'), runs:
      1. Read-only proof: hash every source SQLite/WhatsApp file before touching it.
      2. Carving (freelist + freeblock) on local SQLite sources.
      3. WAL and journal recovery on local SQLite sources.
      4. WhatsApp decrypt + carve.
      5. Trash/recently-deleted media recovery.
      6. Read-only proof: re-hash the same source files, assert unchanged.
      7. Timeline fusion + RED-FLAG keyword matching across the full merged event set.

    Appends all newly-recovered Events (deletion_state='deleted', with accurate
    recovery_method) to case.events, and returns the updated CaseBundle.

    Deterministic: running this twice on the same input CaseBundle must produce
    byte-identical case.to_json() output.
    """
    audit = AuditLog(case.audit_log_path)
    audit.log("recovery_started", {"case_id": case.case_id, "input_event_count": len(case.events)})

    # Step 1: Read-only proof — hash all source files BEFORE any processing
    pre_hashes = _collect_source_files(case)
    audit.log("read_only_proof_before", {"file_hashes": pre_hashes})

    # Step 2: SQLite b-tree carving (freelist + freeblock)
    carved_events = _run_sqlite_carving(case, audit)

    # Step 3: WAL and journal recovery
    wal_journal_events = _run_wal_journal_recovery(case, audit)

    # Step 4: WhatsApp decrypt + carve
    whatsapp_events = _run_whatsapp_recovery(case, audit)

    # Step 5: Trash/recently-deleted media recovery
    media_events = _run_media_recovery(case, audit)

    # Step 6: Read-only proof — re-hash and assert unchanged
    post_hashes = _collect_source_files(case)
    mismatches = {
        path: {"before": pre_hashes.get(path), "after": post_hashes.get(path)}
        for path in set(pre_hashes) | set(post_hashes)
        if pre_hashes.get(path) != post_hashes.get(path)
    }
    if mismatches:
        audit.log("READ_ONLY_VIOLATION", {"mismatches": mismatches})
        raise RuntimeError(
            f"Read-only proof FAILED: source files were modified during recovery. "
            f"Mismatches: {mismatches}"
        )
    audit.log("read_only_proof_after", {"file_hashes": post_hashes, "all_match": True})

    # Combine all recovered events
    all_recovered = carved_events + wal_journal_events + whatsapp_events + media_events
    audit.log(
        "recovery_events_collected",
        {
            "carved": len(carved_events),
            "wal_journal": len(wal_journal_events),
            "whatsapp": len(whatsapp_events),
            "media": len(media_events),
            "total_recovered": len(all_recovered),
        },
    )

    # Append recovered events to case
    case.events.extend(all_recovered)

    # Step 7: Timeline fusion + RED-FLAG keyword matching across ALL events
    from sakshya_recovery.triage.timeline import build_timeline

    case.events = build_timeline(case.events)
    case.events = _run_keyword_matching(case.events, audit)

    audit.log(
        "recovery_complete",
        {
            "case_id": case.case_id,
            "total_events": len(case.events),
            "recovered_events": len(all_recovered),
        },
    )

    return case

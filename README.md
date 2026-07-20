# sakshya-recovery

Forensic evidence recovery module for Android devices — part of the
Sakshya forensic triage pipeline (E-RAKSHAK 2026, PS-02).

## What This Package Does

Takes a `CaseBundle` from [`sakshya-acquisition`](../sakshya-acquisition/)
(Harshit's package) and:

1. **Recovers deleted records** from SQLite databases via real b-tree carving
   (freelist chain walking + in-page freeblock parsing + SQLite record format
   decoding), plus WAL and rollback-journal recovery as separate additional
   methods.
2. **Decrypts WhatsApp backups** (`.crypt14` format, pure Python AES-256-GCM,
   no subprocess dependency) and carves the decrypted database for deleted chats.
3. **Recovers recently-deleted media** from Android's `.Trash/` and `.trashed-*`
   soft-delete locations (scoped storage, Android 11+).
4. **Builds a unified triage timeline** across all event types with **RED-FLAG
   keyword matching** (Hindi/Gujarati/English mixed-script, exact + fuzzy
   transliteration matching).

## Recovery Techniques — Accurate Description

### SQLite B-Tree Carving (the core differentiator)

This is **real byte-level carving**, not string scraping:

- **Freelist carving**: Reads the freelist trunk page number from the database
  header (bytes 32–35), walks the entire trunk chain (each trunk page points
  to the next trunk + lists leaf pages), extracts page images from every
  freelist leaf, and parses them as b-tree pages to recover structured records
  using the SQLite record format (varint-encoded serial types → column values).
- **Freeblock carving**: For each active b-tree page, parses the cell pointer
  array to identify used cells, then walks the in-page freeblock linked list
  (2-byte next-offset + 2-byte size per block) and the unallocated gap between
  the cell pointer array and cell content area. Attempts structured record
  parsing in each freeblock region.
- **Unstructured fallback**: Where freeblock/freelist regions are too damaged
  for structured record parsing, falls back to UTF-8 printable-string
  extraction (handles Devanagari and Gujarati scripts, not just ASCII).
  Results tagged `recovery_method="carved_unstructured"` so downstream
  consumers know the confidence level.

### WAL and Journal Recovery (separate, additional methods)

These recover **different content** than b-tree carving:

- **WAL recovery**: Extracts page images from WAL frames (after the 32-byte
  WAL header + 24-byte frame headers), runs b-tree parsing on each page,
  falls back to string extraction. Recovers in-flight transaction data.
- **Journal recovery**: Parses rollback journal header (8-byte magic, page
  count, sector/page sizes), extracts pre-modification page snapshots at
  correct offsets, runs b-tree parsing. Recovers pre-transaction state.

### WhatsApp Decrypt + Recovery

- **Boundary**: The encrypted backup (`.crypt14`) and key file are already
  acquired by `sakshya-acquisition`. This package only decrypts and carves.
- **Decryption**: Pure Python using `pycryptodome` (AES-256-GCM). Key
  extracted from bytes 126–157 of the 158-byte key file. IV from crypt14
  header. Zlib decompression after decryption.
- **Recovery**: Runs the real b-tree carver on the decrypted database. Also
  queries for soft-deleted tombstones (`text_data IS NULL, message_type IN
  (7, 15)`) and cross-references `message_revoked` table.

### Deleted-Media Recovery — Honest Scope

**What this does**: Recovers files still sitting in Android's `.Trash/` and
`.trashed-*` soft-delete locations (scoped storage, Android 11+). These are
genuinely "recently deleted, not yet purged" — a real capability.

**What this does NOT do**: Unallocated-space file-fragment recovery on shared
storage. That requires raw block device access, which non-root ADB genuinely
does not provide. This limitation is inherent to the non-rooted acquisition
model, not a missing feature.

### RED-FLAG Keyword Matching

- **Exact matching**: Case-insensitive, Unicode NFC-normalized substring
  search across all keyword categories (Hindi, Gujarati, English,
  transliteration variants).
- **Fuzzy matching**: Levenshtein edit distance ≤ 2 for transliteration
  variants (catches "paise" vs "paisa", spelling variants of Hindi/Gujarati
  phrases in Latin script).
- **Configurable**: Keywords loaded from `red_flags.yaml`, not hardcoded.
- **Heuristic-only**: No AI/ML models in v1 — the optional AI enhancements
  (embedding-based similarity for keywords, logistic regression for false-
  positive filtering) are documented as future work, not implemented. The
  heuristic versions are sufficient for a working prototype.

## Non-Negotiable Constraints

- **Read-only**: Source files hashed before and after every operation; hashes
  logged and equality asserted. Violation raises `RuntimeError`.
- **Deterministic**: Identical input → byte-identical `case.to_json()` output.
  No `uuid.uuid4()`, no `datetime.now()` in event data.
- **No LLM/generative model**: All recovery, parsing, scoring, and matching
  is deterministic, explainable, and reproducible.
- **Single audit chain**: Recovery appends to the same `audit_log.jsonl` that
  acquisition started — one continuous hash chain per case.

## Installation

```bash
cd sakshya-recovery
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

## Usage

```python
from sakshya_acquisition import run_acquisition
from sakshya_recovery import run_recovery

# From fixtures (development)
case = run_acquisition("TEST_DEVICE_01", fixture_mode=True)
case = run_recovery(case)

# Inspect results
deleted = [e for e in case.events if e.deletion_state == "deleted"]
print(f"{len(deleted)} deleted events recovered")
for e in deleted:
    print(e.recovery_method, e.integrity_hash[:8], e.app, e.content)

red_flags = [e for e in case.events if e.content.get("red_flag_hit")]
print(f"{len(red_flags)} RED-FLAG hits")
```

## API

```bash
uvicorn sakshya_recovery.api.endpoints:app --reload
```

Endpoints:
- `GET /cases` — list available cases
- `GET /case/{id}/events` — all events (filterable by keyword, date, deletion_state, app)
- `GET /case/{id}/audit-log` — audit chain
- `GET /case/{id}/timeline` — merged timeline
- `GET /case/{id}/red-flags` — events with red-flag hits
- `POST /case/{id}/recover` — trigger recovery on a case

## Project Structure

```
sakshya-recovery/
├── pyproject.toml
├── README.md
├── src/
│   ├── sakshya_acquisition/     # Development shim (MUST be replaced before ship)
│   └── sakshya_recovery/
│       ├── carver/              # Real SQLite b-tree carving
│       │   ├── sqlite_format.py     # Page/header/varint/record parsing
│       │   ├── freeblock_carver.py  # In-page freeblock recovery
│       │   ├── freelist_carver.py   # Freelist chain walking
│       │   ├── unstructured_fallback.py  # UTF-8 string extraction
│       │   └── false_positive_filter.py  # Heuristic scoring
│       ├── wal_journal/         # WAL + journal recovery (separate from carver)
│       ├── whatsapp/            # Decrypt + carve WhatsApp backups
│       ├── media/               # Trash/recently-deleted recovery
│       ├── triage/              # Keyword matching + timeline
│       ├── recovery.py          # run_recovery() entry point
│       └── api/                 # FastAPI endpoints
├── fixtures/                    # Real test databases + WhatsApp fixtures
└── tests/                       # Full test suite
```

## Integration with Sakshya Pipeline

```
[sakshya-acquisition]  →  [sakshya-recovery]  →  [sakshya-report]
     Harshit                  This package            Krish
```

The `sakshya_acquisition` shim in `src/` is a development stopgap.
**Component 11 (Mandatory Shim-Swap Gate)** requires replacing it with
Harshit's real package and rerunning all tests before this package ships.

## Dependencies

- Python 3.10+
- `pycryptodome` — WhatsApp AES-256-GCM decryption
- `pyyaml` — RED-FLAG keyword configuration
- `fastapi` + `uvicorn` — API layer
- `pytest` — testing (dev dependency)

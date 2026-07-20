"""
sakshya_recovery — Forensic evidence recovery for Android devices.

Takes a CaseBundle from sakshya_acquisition and:
  1. Recovers deleted records via real SQLite b-tree carving (freelist + freeblock).
  2. Decrypts WhatsApp backups and recovers deleted chats.
  3. Recovers recently-deleted media from Android Trash locations.
  4. Builds a unified triage timeline with RED-FLAG keyword matching.

Public API:
    from sakshya_recovery import run_recovery
    updated_case = run_recovery(case_bundle)
"""

from sakshya_recovery.recovery import run_recovery

__all__ = ["run_recovery"]
__version__ = "0.1.0"

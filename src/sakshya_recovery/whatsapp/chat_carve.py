"""
WhatsApp chat recovery — carves decrypted WhatsApp DB for deleted messages.

Runs the real SQLite b-tree carver on the decrypted database AND queries
for soft-deleted tombstones (Delete for me / Delete for everyone).
"""

import sqlite3
import os
from sakshya_recovery.carver import carve_sqlite_db


def carve_whatsapp_deleted_chats(decrypted_db_path: str) -> list[dict]:
    """Carve a decrypted WhatsApp database for deleted messages.

    Returns list of dicts with: text, sender_jid, timestamp, key_id,
    deletion_type, recovery_method, confidence.
    """
    results = []

    if not os.path.exists(decrypted_db_path):
        return results

    # 1. Run the real b-tree carver for hard-deleted records
    try:
        carved_records = carve_sqlite_db(decrypted_db_path)
        for record in carved_records:
            # CarvedRecord is a dataclass with .values, .rowid, .recovery_method, etc.
            values = record.values or []
            # Try to extract meaningful text from carved values
            text_parts = [str(v) for v in values if isinstance(v, str) and len(v) > 2]
            if text_parts:
                results.append({
                    'text': ' '.join(text_parts),
                    'sender_jid': None,
                    'timestamp': None,
                    'key_id': None,
                    'deletion_type': 'hard_delete',
                    'recovery_method': record.recovery_method,
                    'confidence': record.confidence,
                })
    except Exception:
        pass

    # 2. Query live data for soft-deleted tombstones
    try:
        conn = sqlite3.connect(f"file:{decrypted_db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # "Delete for me" (type 7) and "Delete for everyone" (type 15)
        # are soft-deletes: text_data is nulled but the row stays
        try:
            cursor.execute(
                "SELECT * FROM message WHERE text_data IS NULL "
                "AND message_type IN (7, 15)"
            )
            rows = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description] if cursor.description else []

            for row in rows:
                row_dict = dict(zip(col_names, row))
                msg_type = row_dict.get('message_type', 0)
                del_type = 'delete_for_me' if msg_type == 7 else 'delete_for_everyone'

                results.append({
                    'text': None,
                    'sender_jid': row_dict.get('sender_jid_row_id'),
                    'timestamp': row_dict.get('timestamp'),
                    'key_id': row_dict.get('key_id'),
                    'deletion_type': del_type,
                    'recovery_method': 'live_tombstone',
                    'confidence': 1.0,
                })
        except sqlite3.OperationalError:
            # Table or column doesn't exist in this WhatsApp version
            pass

        # 3. Cross-reference message_revoked table (Delete for everyone metadata)
        try:
            cursor.execute("SELECT * FROM message_revoked")
            revoked_rows = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description] if cursor.description else []
            for row in revoked_rows:
                row_dict = dict(zip(col_names, row))
                results.append({
                    'text': None,
                    'sender_jid': row_dict.get('from_me'),
                    'timestamp': row_dict.get('revoke_timestamp'),
                    'key_id': row_dict.get('key_id'),
                    'deletion_type': 'delete_for_everyone',
                    'recovery_method': 'revoked_table',
                    'confidence': 1.0,
                })
        except sqlite3.OperationalError:
            pass

        conn.close()
    except Exception:
        pass

    return results

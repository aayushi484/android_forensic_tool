import pytest
import os
import hashlib
from sakshya_recovery.media.trash_recovery import recover_trashed_files


def test_recover_trashed_files(tmp_path):
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir()

    test_file_path = trash_dir / "test.jpg"
    content = b"test content for forensic recovery"
    with open(test_file_path, "wb") as f:
        f.write(content)

    trashed_file = tmp_path / ".trashed-1234-test.jpg"
    with open(trashed_file, "wb") as f:
        f.write(content)

    recovered = recover_trashed_files([str(tmp_path)])
    assert len(recovered) == 2

    expected_hash = hashlib.sha256(content).hexdigest()
    for r in recovered:
        assert r["recovery_method"] == "trash_recovery"
        assert r["file_hash"] == expected_hash
        assert r["trash_path"] in [str(test_file_path), str(trashed_file)]
        assert r["size"] == len(content)


def test_recover_empty_dir(tmp_path):
    recovered = recover_trashed_files([str(tmp_path)])
    assert len(recovered) == 0

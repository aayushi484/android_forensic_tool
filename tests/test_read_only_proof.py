import pytest
import os
from sakshya_acquisition import run_acquisition, _hash_file
from sakshya_recovery.recovery import run_recovery
import glob

def hash_all_files(directory):
    hashes = {}
    for root, dirs, files in os.walk(directory):
        for file in files:
            path = os.path.join(root, file)
            try:
                hashes[path] = _hash_file(path)
            except Exception:
                pass
    return hashes

def test_read_only_proof(fixture_dir, tmp_path):
    # Setup temporary fixture dir to not pollute the main one
    import shutil
    test_fixture_dir = tmp_path / "fixtures"
    shutil.copytree(fixture_dir, test_fixture_dir)
    
    hashes_before = hash_all_files(str(test_fixture_dir))
    
    case = run_acquisition(fixture_mode=True, fixture_dir=str(test_fixture_dir))
    recovered_case = run_recovery(case)
    
    hashes_after = hash_all_files(str(test_fixture_dir))
    
    assert hashes_before == hashes_after
    
    # Verify audit log contains proofs
    with open(recovered_case.audit_log_path, "r") as f:
        audit_data = f.read()
        assert "read_only_proof_before" in audit_data or "read_only_proof" in audit_data

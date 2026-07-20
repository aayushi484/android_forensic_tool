import pytest
import os
import json
from sakshya_acquisition import run_acquisition, verify_audit_chain
from sakshya_recovery.recovery import run_recovery


def test_integration_with_acquisition(fixture_dir):
    case = run_acquisition(fixture_mode=True, fixture_dir=fixture_dir)
    recovered_case = run_recovery(case)

    # Verify deleted events recovered
    deleted_events = [e for e in recovered_case.events if e.deletion_state == "deleted"]
    assert len(deleted_events) > 0, "No deleted events recovered"

    # Verify at least some events have non-live recovery_method
    recovered_methods = [e for e in recovered_case.events if e.recovery_method != "live"]
    assert len(recovered_methods) > 0, "No recovered events found"

    # Verify audit chain integrity (returns bool)
    is_valid = verify_audit_chain(recovered_case.audit_log_path)
    assert is_valid, "Audit chain integrity check failed"

    # Verify to_json returns list of dicts (not a JSON string)
    json_data = recovered_case.to_json()
    assert isinstance(json_data, list), f"to_json() should return list, got {type(json_data)}"

    # Verify it's JSON-serializable
    json_str = json.dumps(json_data, sort_keys=True, ensure_ascii=False)
    parsed = json.loads(json_str)
    assert len(parsed) == len(recovered_case.events)

    # Print summary
    method_counts = {}
    red_flags = 0
    for e in recovered_case.events:
        method_counts[e.recovery_method] = method_counts.get(e.recovery_method, 0) + 1
        if isinstance(e.content, dict) and e.content.get("red_flag_hit"):
            red_flags += 1

    print("\nRecovery Summary:")
    print(f"Total events: {len(recovered_case.events)}")
    for method, count in sorted(method_counts.items()):
        print(f"  {method}: {count}")
    print(f"Red flag hits: {red_flags}")

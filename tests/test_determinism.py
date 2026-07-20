import pytest
import json
import os
from sakshya_acquisition import run_acquisition, CaseBundle
from sakshya_recovery.recovery import run_recovery


def test_determinism(fixture_dir, tmp_path):
    """Run run_recovery twice on identical CaseBundles — output must be byte-identical."""
    case = run_acquisition(fixture_mode=True, fixture_dir=fixture_dir)

    # Create two independent copies with separate audit logs
    case1 = CaseBundle(
        case_id=case.case_id,
        device_id=case.device_id,
        schema_version=case.schema_version,
        events=list(case.events),
        audit_log_path=str(tmp_path / "audit1.jsonl"),
    )

    case2 = CaseBundle(
        case_id=case.case_id,
        device_id=case.device_id,
        schema_version=case.schema_version,
        events=list(case.events),
        audit_log_path=str(tmp_path / "audit2.jsonl"),
    )

    recovered_case1 = run_recovery(case1)
    recovered_case2 = run_recovery(case2)

    # to_json() returns list[dict], not a JSON string
    json1 = recovered_case1.to_json()
    json2 = recovered_case2.to_json()

    # Serialize deterministically and compare
    str1 = json.dumps(json1, sort_keys=True, ensure_ascii=False)
    str2 = json.dumps(json2, sort_keys=True, ensure_ascii=False)

    assert str1 == str2, "Recovery output is NOT deterministic"

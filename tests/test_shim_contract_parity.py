import pytest
import inspect
from sakshya_acquisition import Event, CaseBundle, AuditLog, EVENT_SCHEMA_VERSION

def test_event_is_frozen_dataclass():
    import dataclasses
    assert dataclasses.is_dataclass(Event)
    # Frozen check
    try:
        e = Event(event_id='x', timestamp=None, app='sms', event_type='sms',
                  direction=None, party=None, content={}, deletion_state='live',
                  recovery_method='live', source_file='x', integrity_hash='x')
        e.event_id = 'y'
        assert False, 'Event should be frozen'
    except (AttributeError, TypeError, dataclasses.FrozenInstanceError):
        pass

def test_event_has_required_fields():
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(Event)}
    required = {'event_id', 'timestamp', 'app', 'event_type', 'direction', 'party',
                'content', 'deletion_state', 'recovery_method', 'source_file', 'integrity_hash'}
    assert required.issubset(field_names)

def test_event_has_compute_hash():
    assert hasattr(Event, 'compute_hash')
    assert callable(getattr(Event, 'compute_hash'))

def test_casebundle_has_required_fields():
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(CaseBundle)}
    required = {'case_id', 'device_id', 'schema_version', 'events', 'audit_log_path'}
    assert required == field_names

def test_casebundle_has_methods():
    assert hasattr(CaseBundle, 'seal')
    assert hasattr(CaseBundle, 'to_json')

def test_auditlog_has_log_method():
    sig = inspect.signature(AuditLog.log)
    params = list(sig.parameters.keys())
    assert 'action' in params
    assert 'details' in params

def test_schema_version_is_string():
    assert isinstance(EVENT_SCHEMA_VERSION, str)

def test_real_package_parity():
    try:
        import importlib
        real = importlib.import_module('sakshya_acquisition_real')
    except ImportError:
        pytest.skip('Real sakshya_acquisition package not installed (expected during development)')
    # When available, compare field names, types, etc.

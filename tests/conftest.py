import os
import sys
import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), '..', 'fixtures')

@pytest.fixture
def fixture_dir():
    return os.path.abspath(FIXTURE_DIR)

@pytest.fixture
def chat_test_db(fixture_dir):
    return os.path.join(fixture_dir, 'chat_test.db')

@pytest.fixture
def journal_test_db(fixture_dir):
    return os.path.join(fixture_dir, 'journal_test.db')

@pytest.fixture
def sms_test_db(fixture_dir):
    return os.path.join(fixture_dir, 'emulator_mmssms_delete_test.db')

@pytest.fixture
def whatsapp_crypt14(fixture_dir):
    path = os.path.join(fixture_dir, 'whatsapp', 'msgstore.db.crypt14')
    if not os.path.exists(path):
        pytest.skip('WhatsApp crypt14 fixture not available')
    return path

@pytest.fixture
def whatsapp_key(fixture_dir):
    path = os.path.join(fixture_dir, 'whatsapp', 'whatsapp_key')
    if not os.path.exists(path):
        pytest.skip('WhatsApp key fixture not available')
    return path

@pytest.fixture
def whatsapp_expected_db(fixture_dir):
    path = os.path.join(fixture_dir, 'whatsapp', 'whatsapp_decrypted.db')
    if not os.path.exists(path):
        pytest.skip('WhatsApp expected DB fixture not available')
    return path

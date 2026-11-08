from pathlib import Path
import os
import tempfile
import unittest
from session_store import SessionStore, StorageError, WindowsProtection
from test_api import SESSION, BASE, VERIFY


class TestProtection:
    """Opaque test transport, not a production encryption implementation."""
    supported = True

    def __init__(self):
        self.values = {}

    def encrypt(self, value):
        handle = os.urandom(40)
        self.values[handle] = value
        return handle

    def decrypt(self, value):
        if value not in self.values:
            raise StorageError('cannot decrypt')
        return self.values[value]


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'session.dat'
        self.protection = TestProtection()
        self.store = SessionStore(self.path, self.protection)

    def test_roundtrip_and_clear(self):
        self.store.save(SESSION, 'account', BASE, VERIFY)
        self.assertNotIn(SESSION.session_id.encode(), self.path.read_bytes())
        second = SessionStore(self.path, self.protection)
        self.assertEqual(second.load(BASE, VERIFY), (SESSION, 'account'))
        second.clear()
        self.assertIsNone(self.store.load(BASE, VERIFY))

    def test_different_service_never_receives_cached_session(self):
        self.store.save(SESSION, 'account', BASE, VERIFY)
        self.assertIsNone(self.store.load('https://other.example/app/', VERIFY))
        self.assertFalse(self.path.exists())

    def test_corrupt_and_oversized_data_are_rejected(self):
        for data in [b'garbage', self.protection.encrypt(b'{}'), b'x' * 64001]:
            self.path.write_bytes(data)
            with self.subTest(size=len(data)), self.assertRaises(StorageError):
                self.store.load(BASE, VERIFY)

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI requires Windows or Wine')
    def test_actual_windows_dpapi_roundtrip(self):
        store = SessionStore(self.path)
        store.save(SESSION, 'account', BASE, VERIFY)
        self.assertNotIn(SESSION.session_id.encode(), self.path.read_bytes())
        self.assertNotIn(b'account', self.path.read_bytes())
        self.assertEqual(SessionStore(self.path).load(BASE, VERIFY), (SESSION, 'account'))
        with self.assertRaises(StorageError):
            WindowsProtection().decrypt(b'invalid DPAPI data')
        store.clear()

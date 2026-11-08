# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-Windows-user DPAPI session storage. No passwords or plaintext fallback."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile

from ucas_api import Session


class StorageError(Exception):
    pass


class WindowsProtection:
    supported = os.name == 'nt'

    def transform(self, value, decrypt=False):
        if not self.supported:
            raise StorageError('当前系统不支持 Windows 会话加密')
        class Blob(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
        crypt = ctypes.WinDLL('crypt32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        protect = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        protect.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        protect.restype = wintypes.BOOL
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        source_buf = ctypes.create_string_buffer(value)
        entropy_bytes = b'UCAS-in-windows/session-v1'
        entropy_buf = ctypes.create_string_buffer(entropy_bytes)
        source = Blob(len(value), ctypes.cast(source_buf, ctypes.POINTER(ctypes.c_ubyte)))
        entropy = Blob(len(entropy_bytes), ctypes.cast(entropy_buf, ctypes.POINTER(ctypes.c_ubyte)))
        result = Blob()
        # No LOCAL_MACHINE flag: only the current Windows user can unprotect it.
        if not protect(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 1, ctypes.byref(result)):
            raise StorageError('Windows 无法加密或恢复本机登录信息，请重新登录')
        try:
            return ctypes.string_at(result.data, result.size)
        finally:
            kernel.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))

    def encrypt(self, value):
        return self.transform(value)

    def decrypt(self, value):
        return self.transform(value, decrypt=True)


class SessionStore:
    def __init__(self, path, protection=None):
        self.path = Path(path)
        self.protection = protection or WindowsProtection()

    @property
    def supported(self):
        return self.protection.supported

    def save(self, session, account, base_url, verify_template):
        payload = {'version': 1, 'user_id': session.user_id, 'session_id': session.session_id,
                   'student_no': session.student_no, 'account': account,
                   'base_url': base_url, 'verify_template': verify_template}
        raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        if len(raw) > 16000:
            raise StorageError('登录信息异常，未保存本机会话')
        encrypted = self.protection.encrypt(raw)
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='session-', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(encrypted)
            temporary.replace(self.path)
        except OSError:
            raise StorageError('无法保存本机加密会话，请检查应用数据目录权限') from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def load(self, base_url, verify_template):
        try:
            with self.path.open('rb') as stream:
                encrypted = stream.read(64001)
        except FileNotFoundError:
            return None
        except OSError:
            raise StorageError('无法读取本机登录信息，请重新登录') from None
        if len(encrypted) > 64000:
            raise StorageError('本机登录文件异常，请重新登录')
        try:
            data = json.loads(self.protection.decrypt(encrypted).decode('utf-8'))
            keys = ('user_id', 'session_id', 'student_no', 'account', 'base_url', 'verify_template')
            if (not isinstance(data, dict) or data.get('version') != 1
                    or any(not isinstance(data.get(k), str) or not data[k].strip() for k in keys)):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise StorageError('本机登录文件损坏，请重新登录') from None
        # Bind the saved token to its original service configuration.
        if data['base_url'] != base_url or data['verify_template'] != verify_template:
            self.clear()
            return None
        return Session(data['user_id'], data['session_id'], data['student_no']), data['account']

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            raise StorageError('无法删除本机登录文件，请检查应用数据目录权限') from None

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline diagnostic for the packaged desktop, invoked only by --smoke-test."""
import io
import json
from pathlib import Path
import platform
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

from ucas_api import Client, DEFAULT_API_BASE, DEFAULT_VERIFY_TEMPLATE, VERSION


def run(app_class, report):
    result = {'ok': False, 'version': VERSION, 'python': platform.python_version(),
              'platform': sys.platform, 'frozen': bool(getattr(sys, 'frozen', False))}
    root = None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = tk.Tk()
            app = app_class(root, Path(tmp) / 'settings.json')
            root.update()
            assert root.winfo_ismapped(), 'window not mapped'
            assert app.base.get() == DEFAULT_API_BASE
            assert app.verify.get() == DEFAULT_VERIFY_TEMPLATE
            payloads = [
                {'STATUS': '0', 'result': {'id': 'offline-user', 'sessionId': 'offline-session', 'studentNo': 'offline-student'}},
                {'STATUS': '0', 'result': [{'id': '1234567', 'courseName': '离线测试课程', 'signStatus': '0'}]},
                {'STATUS': '0', 'timestamp': 1794100000000},
                {'STATUS': '0', 'result': {'stuSignStatus': '1'}},
            ]
            requests = []
            class OfflineTransport:
                def open(self, req, timeout):
                    requests.append(req)
                    return io.BytesIO(json.dumps(payloads.pop(0)).encode())
            client = Client(DEFAULT_API_BASE, DEFAULT_VERIFY_TEMPLATE, OfflineTransport())
            def wait():
                deadline = time.monotonic() + 10
                while app.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.01)
                assert not app.busy, 'worker timed out'
                root.update()
            with patch.object(sys.modules[app_class.__module__], 'Client', return_value=client), \
                    patch('tkinter.messagebox.askyesno', return_value=True), \
                    patch('tkinter.messagebox.showinfo'), patch('tkinter.messagebox.showwarning'), \
                    patch('tkinter.messagebox.showerror') as error:
                app.account.set('offline-account')
                app.password.set('offline-password')
                app.login()
                wait()
                assert len(app.courses) == 1
                app.table.selection_set('0')
                app.sign_selected()
                wait()
                assert app.courses[0].signed
                assert app.table.set('0', 'state') == '已签到'
                app.sign_selected()
                assert len(requests) == 4
                app.save_config()
                assert 'offline-password' not in app.settings_path.read_text(encoding='utf-8')
                app.logout()
                assert app.session is None
                error.assert_not_called()
            result.update(ok=True, checks=['window', 'defaults', 'login', 'courses', 'sign',
                                           'duplicate_guard', 'no_saved_password', 'logout'])
    except Exception as exc:
        result['error_type'] = type(exc).__name__
    finally:
        if root is not None:
            root.destroy()
        report = Path(report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if not result['ok']:
        raise SystemExit(1)

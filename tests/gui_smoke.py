"""Actual Tk workflow with a fake school server; requires an available desktop."""
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from app import App
from ucas_api import Client
from test_api import BASE, VERIFY, CLOCK, LOGIN, SUCCESS, FakeOpener


class DesktopSmoke(unittest.TestCase):
    def test_login_query_sign_logout_and_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tk.Tk()
            self.addCleanup(root.destroy)
            app = App(root, Path(tmp) / 'settings.json')
            app.base.set(BASE)
            app.verify.set(VERIFY)
            app.save_config()
            root.update()
            self.assertTrue(app.settings_path.exists())
            transport = FakeOpener(LOGIN, {'STATUS': '0', 'result': [
                {'id': '1234567', 'courseName': '测试课程', 'signStatus': '0'}]}, CLOCK, SUCCESS)
            client = Client(BASE, VERIFY, transport)
            def wait():
                deadline = time.monotonic() + 8
                while app.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.01)
                self.assertFalse(app.busy)
                root.update()
            with patch('app.Client', return_value=client), patch('app.messagebox.askyesno', return_value=True), \
                    patch('app.messagebox.showinfo'), patch('app.messagebox.showerror') as errors:
                app.account.set('test-account')
                app.password.set('not-persisted-password')
                app.login()
                wait()
                self.assertEqual(len(app.table.get_children()), 1)
                self.assertEqual(app.password.get(), '')
                self.assertNotIn('not-persisted-password', app.settings_path.read_text())
                app.table.selection_set('0')
                app.sign_selected()
                wait()
                self.assertEqual(app.table.set('0', 'state'), '已签到')
                self.assertTrue(app.courses[0].signed)
                app.sign_selected()
                self.assertEqual(len(transport.requests), 4)
                transport.responses.extend([{'STATUS': '1'}, {'STATUS': '0'}])
                app.day.set('20261109')
                app.refresh()
                wait()
                self.assertFalse(app.table.get_children())
                self.assertIsNotNone(app.session)
                self.assertIn('已登录', app.status.get())
                errors.assert_not_called()
                app.logout()
                self.assertIsNone(app.session)
                self.assertFalse(app.table.get_children())


if __name__ == '__main__':
    unittest.main()

"""Actual Tk workflow with a fake school server; requires an available desktop."""
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from app import App
from ucas_api import Client
from urllib.error import HTTPError
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
                self.assertIn('已登录', app.login_status.get())
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
                self.assertEqual(app.login_status.get(), '未登录')
                self.assertFalse(app.table.get_children())

    def test_group_calendar_and_login_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = tk.Tk()
            self.addCleanup(root.destroy)
            app = App(root, Path(tmp) / 'settings.json')
            app.base.set(BASE)
            app.verify.set(VERIFY)
            row = {'id': '1234567', 'courseName': '新中特', 'classBeginTime': '2026-11-11 08:30:00',
                   'classEndTime': '2026-11-11 12:00:00', 'signStatus': '0'}
            transport = FakeOpener(LOGIN, {'STATUS': '0', 'result': [row, row, {**row, 'id': '1234568'},
                {**row, 'id': '1234569', 'courseName': '自然辩证法'}]}, CLOCK, SUCCESS,
                {'STATUS': '0', 'result': []}, {'STATUS': '0'})
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
                app.password.set('password')
                app.login()
                self.assertEqual(app.login_status.get(), '正在登录…')
                wait()
                self.assertEqual(app.login_status.get(), '已登录 · test-account')
                self.assertEqual(len(app.table.get_children()), 2)
                self.assertEqual(len(app.groups[0].records), 2)
                self.assertEqual(app.table.set('0', 'begin'), '08:30')
                app.table.selection_set('0')
                app.sign_selected()
                self.assertEqual(len(transport.requests), 2)  # group never triggers bulk signing
                self.assertTrue(app.table.item('0', 'open'))
                app.table.selection_set('0:0')
                app.sign_selected()
                wait()
                self.assertEqual(app.table.set('0', 'state'), '已签 1/2')
                self.assertTrue(app.courses[0].signed and app.courses[1].signed)
                self.assertFalse(app.courses[2].signed)
                app.date_picker.open_calendar()
                popup = app.date_picker.popup
                popup.year.set('2024')
                popup.month.set('2')
                popup.render()
                self.assertIn(29, popup.day_buttons)
                popup.day_buttons[29].invoke()
                wait()
                self.assertEqual(app.day.get(), '20240229')
                self.assertIn('2024-02-29', app.date_picker.caption.get())
                self.assertFalse(app.courses)
                self.assertIn('已登录', app.login_status.get())
                errors.assert_not_called()
                transport.responses.append(HTTPError(BASE, 401, 'expired', {}, None))
                app.refresh()
                wait()
                self.assertIsNone(app.session)
                self.assertIn('登录已失效', app.login_status.get())
                transport.responses.append({'STATUS': '1'})
                app.password.set('incorrect')
                app.login()
                wait()
                self.assertIsNone(app.session)
                self.assertIn('登录失败', app.login_status.get())


if __name__ == '__main__':
    unittest.main()

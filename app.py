# SPDX-License-Identifier: AGPL-3.0-or-later
"""Windows desktop entry point; Python 3.10+ and Tk, no third-party dependencies."""
import json
from dataclasses import replace
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from ucas_api import (ApiError, SessionExpired, Client, DEFAULT_API_BASE, DEFAULT_VERIFY_TEMPLATE,
                      VERSION, today, validate_base, validate_template)
from course_view import group_courses, code_key, display_time
from date_picker import DatePicker
from session_store import SessionStore, StorageError


def config_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.config'))) / 'UCAS-in-windows' / 'settings.json'


class App:
    def __init__(self, root, settings_path=None, session_store=None):
        self.root = root
        self.settings_path = settings_path or config_path()
        self.session_store = session_store or SessionStore(self.settings_path.parent / 'session.dat')
        self.restoring = False
        self.client = None
        self.session = None
        self.courses = []
        self.groups = []
        self.row_targets = {}
        self.login_pending = False
        self.logged_account = ''
        self.busy = False
        self.events = queue.Queue()
        root.title(f'UCAS 课程签到 · v{VERSION}')
        root.geometry('880x650')
        root.minsize(740, 600)
        self.base = tk.StringVar(value=DEFAULT_API_BASE)
        self.verify = tk.StringVar(value=DEFAULT_VERIFY_TEMPLATE)
        self.account = tk.StringVar()
        self.password = tk.StringVar()
        self.day = tk.StringVar(value=today())
        self.code = tk.StringVar()
        self.login_status = tk.StringVar(value='未登录')
        self.remember_login = tk.BooleanVar(value=self.session_store.supported)
        self.keep_status = tk.StringVar(value='仅本机加密保存会话，不保存密码。' if self.session_store.supported else '当前系统不支持 Windows 会话保存，仅本次登录。')
        self.status = tk.StringVar(value='请输入学校账号和密码登录。')
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill='both', expand=True)
        header = ttk.Frame(frame)
        header.pack(fill='x')
        ttk.Label(header, text='UCAS 课程签到', font=('Microsoft YaHei UI', 18, 'bold')).pack(side='left')
        ttk.Label(frame, text='登录 → 查询课表 → 选中课程 → 签到。勾选保持登录，下次打开自动恢复。').pack(anchor='w', pady=(4, 12))
        self.login_badge = ttk.Label(header, textvariable=self.login_status, foreground='#666666', font=('Microsoft YaHei UI', 11, 'bold'))
        self.login_badge.pack(side='right')
        self.editables = []
        self.buttons = []
        login = ttk.Frame(frame)
        login.pack(fill='x', pady=12)
        ttk.Label(login, text='账号').pack(side='left')
        e = ttk.Entry(login, textvariable=self.account, width=26)
        e.pack(side='left', padx=6)
        self.editables.append(e)
        ttk.Label(login, text='密码').pack(side='left')
        e = ttk.Entry(login, textvariable=self.password, show='●', width=24)
        e.pack(side='left', padx=6)
        self.editables.append(e)
        self.password_entry = e
        self.show_password = tk.BooleanVar(value=False)
        show = ttk.Checkbutton(login, text='显示', variable=self.show_password,
                               command=lambda: self.password_entry.configure(show='' if self.show_password.get() else '●'))
        show.pack(side='left')
        self.editables.append(show)
        self.button(login, '登录', self.login).pack(side='left', padx=4)
        self.button(login, '退出登录', self.logout).pack(side='left')
        keep = ttk.Frame(frame)
        keep.pack(fill='x', pady=(0, 10))
        self.remember_button = ttk.Checkbutton(keep, text='保持登录', variable=self.remember_login, command=self.remember_changed)
        self.remember_button.pack(side='left')
        self.editables.append(self.remember_button)
        ttk.Label(keep, textvariable=self.keep_status, wraplength=650).pack(side='left', padx=8)
        if not self.session_store.supported:
            self.remember_button.configure(state='disabled')
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill='x', pady=(0, 8))
        ttk.Label(toolbar, text='日期').pack(side='left')
        self.date_picker = DatePicker(toolbar, self.day, self.date_changed)
        self.date_picker.pack(side='left', padx=4)
        self.button(toolbar, '查询课表', self.refresh).pack(side='left')
        self.button(toolbar, '今天', self.go_today).pack(side='left', padx=4)
        self.button(toolbar, '签到选中课程', self.sign_selected).pack(side='right')
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill='both', expand=True)
        self.table = ttk.Treeview(table_frame, columns=('begin', 'end', 'state'), show='tree headings', selectmode='browse', height=8)
        for col, name, width in [('#0', '课程（可展开查看签到记录）', 380), ('begin', '开始', 90), ('end', '结束', 90), ('state', '状态', 100)]:
            self.table.heading(col, text=name)
            self.table.column(col, width=width, minwidth=70)
        self.table.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        scroll.pack(side='right', fill='y')
        self.table.configure(yscrollcommand=scroll.set)
        manual = ttk.Frame(frame)
        manual.pack(fill='x', pady=10)
        ttk.Label(manual, text='手动课程 ID / UUID').pack(side='left')
        e = ttk.Entry(manual, textvariable=self.code)
        e.pack(side='left', fill='x', expand=True, padx=8)
        self.editables.append(e)
        self.button(manual, '手动签到', self.sign_manual).pack(side='right')
        ttk.Label(frame, textvariable=self.status, wraplength=800).pack(anchor='w', pady=6)
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.pack(fill='x', pady=(0, 6))
        ttk.Label(frame, text='结果以学校服务器为准；网络超时后先查课表确认，避免重复提交。').pack(anchor='w')
        try:
            settings = json.loads(self.settings_path.read_text(encoding='utf-8'))
            base = settings.get('api_base_url', DEFAULT_API_BASE)
            verify = settings.get('verify_url_template', DEFAULT_VERIFY_TEMPLATE)
            if not isinstance(base, str) or not isinstance(verify, str):
                raise ValueError('配置字段类型错误')
            self.base.set(validate_base(base))
            self.verify.set(validate_template(verify))
            self.remember_login.set(self.session_store.supported and settings.get('remember_login', True) is True)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError, ApiError):
            self.base.set(DEFAULT_API_BASE)
            self.verify.set(DEFAULT_VERIFY_TEMPLATE)
            self.status.set('本地配置无效，已使用国科大默认接口；原配置文件没有被覆盖。')
        if self.session_store.supported and not self.remember_login.get():
            self.keep_status.set('未开启保持登录，关闭后需要重新登录。')
        self.poll_id = root.after(100, self.poll)
        self.restore_id = root.after_idle(self.restore_saved_session)
        root.bind('<Destroy>', self.stop_poll, add='+')

    def stop_poll(self, event):
        if event.widget is self.root:
            self.root.after_cancel(self.poll_id)
            if self.restore_id is not None:
                self.root.after_cancel(self.restore_id)

    def button(self, parent, text, command):
        b = ttk.Button(parent, text=text, command=command)
        self.buttons.append(b)
        return b

    def clear_login(self):
        erased = True
        try:
            self.session_store.clear()
        except StorageError as exc:
            self.keep_status.set(str(exc))
            erased = False
        self.session = None
        self.client = None
        self.courses = []
        self.groups = []
        self.row_targets = {}
        self.login_pending = False
        self.logged_account = ''
        self.restoring = False
        self.set_login_state('未登录')
        self.table.delete(*self.table.get_children())
        return erased

    def set_login_state(self, state, color='#666666'):
        self.login_status.set(state)
        self.login_badge.configure(foreground=color)

    def save_config(self):
        try:
            base = validate_base(self.base.get())
            template = validate_template(self.verify.get())
            self.save_preferences()
            if self.client and (base != self.client.base_url or template != self.client.verify_template):
                self.clear_login()
            self.status.set('配置已保存。' if self.session else '配置已保存，请登录。')
        except (OSError, ApiError, ValueError) as exc:
            messagebox.showerror('配置未保存', str(exc), parent=self.root)

    def save_preferences(self):
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'api_base_url': self.base.get(), 'verify_url_template': self.verify.get(),
                                         'remember_login': self.remember_login.get()}, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.settings_path)

    def remember_changed(self):
        if not self.remember_login.get():
            try:
                self.session_store.clear()
                self.save_preferences()
                self.keep_status.set('已关闭保持登录；关闭程序后需要重新登录。')
            except (StorageError, OSError):
                self.keep_status.set('未能清除或保存登录设置，请检查应用数据目录权限。')
                messagebox.showerror('保存失败', self.keep_status.get(), parent=self.root)
        else:
            self.persist_session()

    def persist_session(self):
        try:
            self.save_preferences()
            if self.remember_login.get() and self.session_store.supported and self.session:
                self.session_store.save(self.session, self.logged_account, self.client.base_url, self.client.verify_template)
                self.keep_status.set('会话已加密保存，下次打开自动恢复；不保存密码。')
            elif self.remember_login.get():
                self.keep_status.set('成功登录后将加密保存本机会话，不保存密码。')
            else:
                self.keep_status.set('仅本次登录，关闭程序后需要重新登录。')
        except (StorageError, OSError):
            self.keep_status.set('本机会话未能保存，下次打开需要重新登录。')

    def restore_saved_session(self):
        self.restore_id = None
        if not self.remember_login.get() or not self.session_store.supported:
            return
        try:
            saved = self.session_store.load(self.base.get(), self.verify.get())
            if saved is None:
                return
            self.client = Client(self.base.get(), self.verify.get())
            self.session, self.logged_account = saved
            self.account.set(self.logged_account)
            self.restoring = True
            self.set_login_state('正在恢复登录…', '#9a6700')
            self.keep_status.set('已读取本机加密会话，正在向学校验证…')
            self.refresh()
        except (StorageError, ApiError):
            self.clear_login()
            self.keep_status.set('本机保存的登录信息无法恢复，请重新登录。')

    def run(self, work, done):
        if self.busy:
            return
        self.busy = True
        self.date_picker.set_enabled(False)
        self.progress.start(12)
        for widget in self.buttons + self.editables:
            widget.configure(state='disabled')
        self.status.set('正在连接学校服务器，请稍候…')
        def worker():
            try:
                self.events.put((done, work(), None))
            except ApiError as exc:
                self.events.put((done, None, exc))
            except Exception:
                # Unexpected exception details may contain credentials/URLs.
                self.events.put((done, None, '操作失败：响应格式异常或程序发生错误，请检查配置后重试'))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            done, result, error = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.date_picker.set_enabled(True)
            self.progress.stop()
            for widget in self.buttons + self.editables:
                widget.configure(state='normal')
            if not self.session_store.supported:
                self.remember_button.configure(state='disabled')
            if error:
                if self.login_pending:
                    self.clear_login()
                    self.set_login_state('登录失败 · 请检查账号、密码或网络', '#b42318')
                elif isinstance(error, SessionExpired):
                    self.clear_login()
                    self.set_login_state('登录已失效 · 请重新登录', '#b42318')
                    self.keep_status.set('学校会话已失效，重新登录后可继续保持。')
                elif self.restoring:
                    self.set_login_state('登录待验证 · 请检查网络', '#9a6700')
                    self.keep_status.set('已保存的会话保留，网络恢复后点击查询课表重试。')
                self.status.set(str(error))
                messagebox.showerror('操作失败', str(error), parent=self.root)
            else:
                done(result)
        self.poll_id = self.root.after(100, self.poll)

    def login(self):
        if self.busy:
            return
        self.clear_login()  # a failed account switch must not retain the old identity
        try:
            client = Client(self.base.get(), self.verify.get())
        except ApiError as exc:
            messagebox.showerror('配置错误', str(exc), parent=self.root)
            return
        account, password = self.account.get(), self.password.get()
        self.password.set('')
        def done(session):
            self.login_pending = False
            self.client, self.session = client, session
            self.logged_account = account.strip()
            self.set_login_state(f'已登录 · {self.logged_account}', '#087443')
            self.persist_session()
            self.status.set('登录成功，可以查询课表。')
            self.refresh()
        self.login_pending = True
        self.set_login_state('正在登录…', '#9a6700')
        self.run(lambda: client.login(account, password), done)

    def logout(self):
        erased = self.clear_login()
        self.password.set('')
        self.account.set('')
        self.status.set('已退出登录，并清除本机保存的会话。' if erased else '已退出本次登录，但本机会话文件无法删除。')
        if erased:
            self.keep_status.set('本机保存的会话已清除。')
        else:
            messagebox.showerror('会话未清除', self.keep_status.get(), parent=self.root)

    def restore_defaults(self):
        self.clear_login()
        self.base.set(DEFAULT_API_BASE)
        self.verify.set(DEFAULT_VERIFY_TEMPLATE)
        self.status.set('已恢复默认接口。可直接登录，或点保存配置以覆盖本地配置。')

    def test_connection(self):
        try:
            client = Client(self.base.get(), self.verify.get())
        except ApiError as exc:
            messagebox.showerror('配置错误', str(exc), parent=self.root)
            return
        from datetime import datetime, timedelta, timezone
        def done(ts):
            clock = datetime.fromtimestamp(ts / 1000, timezone(timedelta(hours=8)))
            self.status.set(f'连接成功 · 学校时间：{clock:%Y-%m-%d %H:%M:%S}（北京时间）；此检查不验证账号。')
        self.run(client.server_timestamp, done)

    def go_today(self):
        self.day.set(today())
        self.date_changed()

    def date_changed(self):
        if self.session is not None:
            self.refresh()
        else:
            self.status.set('日期已选择，请先登录后查询课程。')

    def require_login(self):
        if self.client is None or self.session is None:
            messagebox.showinfo('请先登录', '请先输入学校账号和密码登录。', parent=self.root)
            return False
        if (self.base.get().strip().rstrip('/') + '/' != self.client.base_url
                or self.verify.get().strip() != self.client.verify_template):
            self.clear_login()
            messagebox.showinfo('配置已改变', '请使用新配置重新登录。', parent=self.root)
            return False
        return True

    def refresh(self):
        if not self.require_login():
            return
        day = self.day.get().strip()
        # Never leave an old day's actionable rows under a newly selected date.
        self.courses = []
        self.render_courses()
        def done(courses):
            if self.restoring:
                self.restoring = False
                self.set_login_state(f'已登录 · {self.logged_account}', '#087443')
                self.keep_status.set('已恢复本机登录；不保存密码。')
            self.loaded_day = day
            self.courses = courses
            self.render_courses()
            count = f'（原始 {len(courses)} 条记录，已合并显示）' if len(courses) != len(self.groups) else ''
            self.status.set(f'{day}：共 {len(self.groups)} 门课程{count}。' if courses else f'已登录 · {day}：学校未返回该日课程，可切换到确定有课的日期。')
        self.run(lambda: self.client.courses(self.session, day), done)

    def render_courses(self):
        expanded = {iid for iid in self.table.get_children() if self.table.item(iid, 'open')}
        selection = self.table.selection()
        self.groups = group_courses(self.courses)
        self.row_targets = {}
        self.table.delete(*self.table.get_children())
        for i, group in enumerate(self.groups):
            iid = str(i)
            title = group.name + (f'（{len(group.records)} 条记录）' if len(group.records) > 1 else '')
            self.table.insert('', 'end', iid=iid, text=title, open=iid in expanded,
                              values=(display_time(group.begin), display_time(group.end), group.state))
            self.row_targets[iid] = group
            if len(group.records) > 1:
                for j, record in enumerate(group.records):
                    child = f'{iid}:{j}'
                    title = f'{record.teacher + " · " if record.teacher else ""}编号 {record.code or "缺失"}'
                    self.table.insert(iid, 'end', iid=child, text=title,
                                      values=(display_time(record.begin), display_time(record.end), '已签到' if record.signed else '未签到'))
                    self.row_targets[child] = record
        if selection and self.table.exists(selection[0]):
            self.table.selection_set(selection[0])

    def sign_selected(self):
        if not self.require_login():
            return
        selection = self.table.selection()
        if not selection:
            messagebox.showinfo('请选择课程', '先查询课表并选中一门课程。', parent=self.root)
            return
        target = self.row_targets[selection[0]]
        from course_view import CourseGroup
        if isinstance(target, CourseGroup):
            pending = [record for record in target.records if not record.signed]
            if len(pending) > 1:
                self.table.item(selection[0], open=True)
                self.status.set('此课程含多个不同签到编号，已展开；请选择一条对应记录后签到。')
                return
            course = pending[0] if pending else target.records[0]
        else:
            course = target
        if course.signed:
            self.status.set('这门课程已签到，无需再次提交。')
            return
        self.submit(course.code, f'{self.loaded_day} · {course.name}' + (f' · {course.teacher}' if course.teacher else ''))

    def sign_manual(self):
        if self.require_login():
            self.submit(self.code.get().strip(), '手动课程')

    def submit(self, code, name):
        from ucas_api import sign_parameter
        try:
            sign_parameter(code)
        except ApiError as exc:
            messagebox.showerror('课程编号无效', str(exc), parent=self.root)
            return
        if not messagebox.askyesno('确认签到', f'向学校提交「{name}」的签到？\n编号：{code}', parent=self.root):
            return
        def done(result):
            self.status.set(result.message)
            if result.ok:
                # Reflect only an explicit server confirmation. Refresh remains user-controlled.
                for i, course in enumerate(self.courses):
                    if code_key(course.code) == code_key(code):
                        self.courses[i] = replace(course, signed=True)
                self.render_courses()
                messagebox.showinfo('签到结果', result.message, parent=self.root)
            else:
                messagebox.showwarning('学校未确认签到', result.message, parent=self.root)
        self.run(lambda: self.client.sign(self.session, code), done)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='UCAS 课程签到')
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--smoke-test', metavar='REPORT', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.smoke_test:
        from smoke_check import run
        run(App, Path(args.smoke_test))
        return
    root = tk.Tk()
    if os.name == 'nt':
        ttk.Style(root).theme_use('vista')
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()

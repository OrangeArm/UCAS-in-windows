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

from ucas_api import (ApiError, Client, DEFAULT_API_BASE, DEFAULT_VERIFY_TEMPLATE,
                      VERSION, today, validate_base, validate_template)


def config_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.config'))) / 'UCAS-in-windows' / 'settings.json'


class App:
    def __init__(self, root, settings_path=None):
        self.root = root
        self.settings_path = settings_path or config_path()
        self.client = None
        self.session = None
        self.courses = []
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
        self.status = tk.StringVar(value='已预填国科大轻新课堂接口，可以直接登录；也可先测试连接。')
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='UCAS 课程签到', font=('Microsoft YaHei UI', 18, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='登录 → 查询课表 → 选中课程 → 签到。关闭窗口即退出登录。').pack(anchor='w', pady=(4, 12))
        config = ttk.LabelFrame(frame, text='学校接口（已预填；仅接口变更时需要修改）', padding=10)
        config.pack(fill='x')
        config.columnconfigure(1, weight=1)
        self.editables = []
        for i, (label, var) in enumerate((('API 根地址', self.base), ('登录校验 URL 模板', self.verify))):
            ttk.Label(config, text=label).grid(row=i, column=0, sticky='w', padx=(0, 8), pady=3)
            entry = ttk.Entry(config, textvariable=var)
            entry.grid(row=i, column=1, sticky='ew')
            self.editables.append(entry)
        self.buttons = []
        actions = ttk.Frame(config)
        actions.grid(row=2, column=1, sticky='e', pady=(6, 0))
        self.button(actions, '恢复默认', self.restore_defaults).pack(side='left', padx=4)
        self.button(actions, '测试连接', self.test_connection).pack(side='left', padx=4)
        self.button(actions, '保存配置', self.save_config).pack(side='left')
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
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill='x', pady=(0, 8))
        ttk.Label(toolbar, text='日期 YYYYMMDD').pack(side='left')
        e = ttk.Entry(toolbar, textvariable=self.day, width=12)
        e.pack(side='left', padx=6)
        self.editables.append(e)
        self.button(toolbar, '查询课表', self.refresh).pack(side='left')
        self.button(toolbar, '今天', self.go_today).pack(side='left', padx=4)
        self.button(toolbar, '签到选中课程', self.sign_selected).pack(side='right')
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill='both', expand=True)
        self.table = ttk.Treeview(table_frame, columns=('name', 'begin', 'end', 'state'), show='headings', selectmode='browse', height=8)
        for col, name, width in [('name', '课程', 280), ('begin', '开始', 150), ('end', '结束', 150), ('state', '状态', 90)]:
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
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError, ApiError):
            self.base.set(DEFAULT_API_BASE)
            self.verify.set(DEFAULT_VERIFY_TEMPLATE)
            self.status.set('本地配置无效，已使用国科大默认接口；原配置文件没有被覆盖。')
        root.after(100, self.poll)

    def button(self, parent, text, command):
        b = ttk.Button(parent, text=text, command=command)
        self.buttons.append(b)
        return b

    def clear_login(self):
        self.session = None
        self.client = None
        self.courses = []
        self.table.delete(*self.table.get_children())

    def save_config(self):
        try:
            base = validate_base(self.base.get())
            template = validate_template(self.verify.get())
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.settings_path.with_suffix('.tmp')
            temp.write_text(json.dumps({'api_base_url': base, 'verify_url_template': template}, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(self.settings_path)
            self.clear_login()
            self.status.set('配置已保存，请登录。')
        except (OSError, ApiError, ValueError) as exc:
            messagebox.showerror('配置未保存', str(exc), parent=self.root)

    def run(self, work, done):
        if self.busy:
            return
        self.busy = True
        self.progress.start(12)
        for widget in self.buttons + self.editables:
            widget.configure(state='disabled')
        self.status.set('正在连接学校服务器，请稍候…')
        def worker():
            try:
                self.events.put((done, work(), None))
            except ApiError as exc:
                self.events.put((done, None, str(exc)))
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
            self.progress.stop()
            for widget in self.buttons + self.editables:
                widget.configure(state='normal')
            if error:
                self.status.set(error)
                messagebox.showerror('操作失败', error, parent=self.root)
            else:
                done(result)
        self.root.after(100, self.poll)

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
            self.client, self.session = client, session
            self.status.set('登录成功，可以查询课表。')
            self.refresh()
        self.run(lambda: client.login(account, password), done)

    def logout(self):
        self.clear_login()
        self.password.set('')
        self.account.set('')
        self.status.set('已退出登录。')

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
        if self.session is not None:
            self.refresh()

    def require_login(self):
        if self.client is None or self.session is None:
            messagebox.showinfo('请先登录', '请填写接口配置并登录学校账号。', parent=self.root)
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
        def done(courses):
            self.loaded_day = day
            self.courses = courses
            self.table.delete(*self.table.get_children())
            for i, course in enumerate(courses):
                self.table.insert('', 'end', iid=str(i), values=(course.name, course.begin, course.end, '已签到' if course.signed else '未签到'))
            self.status.set(f'{day}：共 {len(courses)} 门课程。' if courses else f'已登录 · {day}：学校未返回该日课程，可切换到确定有课的日期。')
        self.run(lambda: self.client.courses(self.session, day), done)

    def sign_selected(self):
        if not self.require_login():
            return
        selection = self.table.selection()
        if not selection:
            messagebox.showinfo('请选择课程', '先查询课表并选中一门课程。', parent=self.root)
            return
        course = self.courses[int(selection[0])]
        if course.signed:
            self.status.set('这门课程已签到，无需再次提交。')
            return
        self.submit(course.code, f'{self.loaded_day} · {course.name}')

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
                    if course.code.replace('-', '').upper() == code.replace('-', '').upper():
                        self.courses[i] = replace(course, signed=True)
                        self.table.set(str(i), 'state', '已签到')
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

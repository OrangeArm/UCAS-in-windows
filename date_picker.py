# SPDX-License-Identifier: AGPL-3.0-or-later
"""Calendar picker using only Python/Tk; the API date remains YYYYMMDD internally."""
import calendar
from datetime import date, datetime, timedelta
import tkinter as tk
from tkinter import ttk

WEEKDAYS = ('一', '二', '三', '四', '五', '六', '日')


def parse_day(value):
    return datetime.strptime(value, '%Y%m%d').date()


def month_shift(year, month, delta):
    index = year * 12 + month - 1 + delta
    y, m = divmod(index, 12)
    return y, m + 1


class DatePicker(ttk.Frame):
    def __init__(self, parent, variable, on_change):
        super().__init__(parent)
        self.variable = variable
        self.on_change = on_change
        self.caption = tk.StringVar()
        self.popup = None
        self.controls = []
        self.controls.append(ttk.Button(self, text='‹', width=3, command=lambda: self.move(-1)))
        self.controls.append(ttk.Button(self, textvariable=self.caption, width=24, command=self.open_calendar))
        self.controls.append(ttk.Button(self, text='›', width=3, command=lambda: self.move(1)))
        for control in self.controls:
            control.pack(side='left', padx=2)
        self.trace_id = variable.trace_add('write', self.update_caption)
        self.update_caption()
        self.bind('<Destroy>', self.cleanup, add='+')

    def cleanup(self, event):
        if event.widget is self:
            self.variable.trace_remove('write', self.trace_id)

    def update_caption(self, *_):
        try:
            day = parse_day(self.variable.get())
            self.caption.set(f'{day:%Y-%m-%d}  星期{WEEKDAYS[day.weekday()]} ▾')
        except ValueError:
            self.caption.set('选择日期 ▾')

    def choose(self, selected):
        self.variable.set(selected.strftime('%Y%m%d'))
        self.on_change()

    def move(self, delta):
        self.choose(parse_day(self.variable.get()) + timedelta(days=delta))

    def set_enabled(self, enabled):
        for control in self.controls:
            control.configure(state='normal' if enabled else 'disabled')

    def open_calendar(self):
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.lift()
            return
        self.popup = CalendarPopup(self, parse_day(self.variable.get()), self.choose)


class CalendarPopup(tk.Toplevel):
    def __init__(self, parent, selected, on_select):
        super().__init__(parent)
        self.selected = selected
        self.on_select = on_select
        self.title('选择课程日期')
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.year = tk.StringVar(value=str(selected.year))
        self.month = tk.StringVar(value=str(selected.month))
        head = ttk.Frame(self, padding=10)
        head.pack(fill='x')
        ttk.Button(head, text='‹', width=3, command=lambda: self.change_month(-1)).pack(side='left')
        year = ttk.Spinbox(head, from_=1900, to=9998, textvariable=self.year, width=6, command=self.render)
        year.pack(side='left', padx=(6, 0))
        ttk.Label(head, text='年').pack(side='left')
        month = ttk.Combobox(head, values=tuple(range(1, 13)), textvariable=self.month, state='readonly', width=4)
        month.pack(side='left')
        ttk.Label(head, text='月').pack(side='left', padx=(0, 6))
        ttk.Button(head, text='›', width=3, command=lambda: self.change_month(1)).pack(side='left')
        year.bind('<Return>', self.render)
        year.bind('<FocusOut>', self.render)
        month.bind('<<ComboboxSelected>>', self.render)
        self.grid_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        self.grid_frame.pack()
        footer = ttk.Frame(self, padding=(10, 0, 10, 10))
        footer.pack(fill='x')
        from ucas_api import today
        ttk.Button(footer, text='今天', command=lambda: self.pick(parse_day(today()))).pack(side='left')
        ttk.Button(footer, text='取消', command=self.destroy).pack(side='right')
        self.bind('<Escape>', lambda e: self.destroy())
        self.render()
        self.update_idletasks()
        x = min(parent.winfo_rootx(), self.winfo_screenwidth() - self.winfo_reqwidth())
        y = min(parent.winfo_rooty() + parent.winfo_height(), self.winfo_screenheight() - self.winfo_reqheight())
        self.geometry(f'+{max(0, x)}+{max(0, y)}')
        self.grab_set()
        self.focus_set()

    def render(self, *_):
        try:
            year, month = int(self.year.get()), int(self.month.get())
            if not (1 <= year <= 9998 and 1 <= month <= 12):
                return
        except ValueError:
            return
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.day_buttons = {}
        for col, label in enumerate(WEEKDAYS):
            ttk.Label(self.grid_frame, text=label, anchor='center', width=4).grid(row=0, column=col, pady=4)
        for row, week in enumerate(calendar.Calendar(firstweekday=0).monthdayscalendar(year, month), start=1):
            for col, number in enumerate(week):
                if number:
                    day = date(year, month, number)
                    label = f'[{number}]' if day == self.selected else str(number)
                    button = ttk.Button(self.grid_frame, text=label, width=4, command=lambda d=day: self.pick(d))
                    button.grid(row=row, column=col, padx=1, pady=2)
                    self.day_buttons[number] = button

    def change_month(self, delta):
        try:
            year, month = month_shift(int(self.year.get()), int(self.month.get()), delta)
            if not (1 <= year <= 9998):
                return
        except ValueError:
            return
        self.year.set(str(year))
        self.month.set(str(month))
        self.render()

    def pick(self, day):
        self.destroy()
        self.on_select(day)

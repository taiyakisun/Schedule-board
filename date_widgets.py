from __future__ import annotations

import calendar
from datetime import date, datetime, time
import tkinter as tk
from tkinter import ttk
from typing import Callable


class CalendarPopup:
    def __init__(
        self,
        owner: tk.Misc,
        initial: date,
        on_select: Callable[[date], None],
    ) -> None:
        self.on_select = on_select
        self.year = initial.year
        self.month = initial.month
        self.window = tk.Toplevel(owner)
        self.window.title("日付を選択")
        self.window.transient(owner.winfo_toplevel())
        self.window.resizable(False, False)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        header = ttk.Frame(self.window, padding=(10, 10, 10, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Button(header, text="‹", width=3, command=lambda: self._move_month(-1)).grid(
            row=0, column=0
        )
        self.month_label = ttk.Label(header, anchor="center")
        self.month_label.grid(row=0, column=1, sticky="ew", padx=12)
        ttk.Button(header, text="›", width=3, command=lambda: self._move_month(1)).grid(
            row=0, column=2
        )

        self.days_frame = ttk.Frame(self.window, padding=(10, 4, 10, 10))
        self.days_frame.grid(row=1, column=0)
        self._render()
        self.window.update_idletasks()
        x = owner.winfo_rootx()
        y = owner.winfo_rooty() + owner.winfo_height() + 4
        self.window.geometry(f"+{x}+{y}")
        self.window.focus_set()

    def _move_month(self, amount: int) -> None:
        month_index = (self.year * 12 + self.month - 1) + amount
        year, zero_based_month = divmod(month_index, 12)
        if not 1 <= year <= 9999:
            return
        self.year = year
        self.month = zero_based_month + 1
        self._render()

    def _render(self) -> None:
        for child in self.days_frame.winfo_children():
            child.destroy()
        self.month_label.configure(text=f"{self.year}年{self.month}月")
        for column, text in enumerate(("月", "火", "水", "木", "金", "土", "日")):
            ttk.Label(self.days_frame, text=text, anchor="center", width=4).grid(
                row=0, column=column, padx=1, pady=(0, 3)
            )
        today = date.today()
        for row, week in enumerate(calendar.monthcalendar(self.year, self.month), start=1):
            for column, day in enumerate(week):
                if day == 0:
                    ttk.Label(self.days_frame, text="", width=4).grid(
                        row=row, column=column, padx=1, pady=1
                    )
                    continue
                selected = date(self.year, self.month, day)
                label = f"[{day}]" if selected == today else str(day)
                ttk.Button(
                    self.days_frame,
                    text=label,
                    width=4,
                    command=lambda value=selected: self._select(value),
                ).grid(row=row, column=column, padx=1, pady=1)

    def _select(self, value: date) -> None:
        self.on_select(value)
        self.close()

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()


class DateInput(tk.Frame):
    """Segmented YYYY-MM-DD input with an optional calendar popup."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        value: date | None = None,
        allow_empty: bool = False,
        background: str | None = None,
        on_change: Callable[[date], None] | None = None,
    ) -> None:
        super().__init__(master, bg=background or master.cget("background"))
        self.allow_empty = allow_empty
        self.on_change = on_change
        self.year_var = tk.StringVar()
        self.month_var = tk.StringVar()
        self.day_var = tk.StringVar()
        self.entries: list[ttk.Entry] = []

        for column, (variable, width, maximum) in enumerate(
            ((self.year_var, 4, 4), (self.month_var, 2, 2), (self.day_var, 2, 2))
        ):
            entry = ttk.Entry(
                self,
                textvariable=variable,
                width=width,
                justify="center",
                style="Modern.TEntry",
            )
            entry.grid(row=0, column=column * 2, sticky="ew")
            self.columnconfigure(column * 2, weight=1)
            entry.bind("<FocusIn>", lambda _event, item=entry: item.after_idle(item.select_range, 0, "end"))
            entry.bind("<space>", lambda _event, index=column: self._advance(index))
            entry.bind("<minus>", lambda _event, index=column: self._advance(index))
            entry.bind("<slash>", lambda _event, index=column: self._advance(index))
            entry.bind("<<Paste>>", self._paste)
            entry.bind("<KeyRelease>", self._notify_complete_date)
            entry.bind("<FocusOut>", self._notify_date)
            entry.configure(
                validate="key",
                validatecommand=(
                    self.register(lambda proposed, limit=maximum: proposed.isdigit() and len(proposed) <= limit or proposed == ""),
                    "%P",
                ),
            )
            self.entries.append(entry)
            if column < 2:
                tk.Label(
                    self,
                    text="-",
                    bg=self.cget("background"),
                    padx=3,
                ).grid(row=0, column=column * 2 + 1)

        self.calendar_button = ttk.Button(
            self,
            text="カレンダー",
            style="Secondary.TButton",
            command=self._open_calendar,
        )
        self.calendar_button.grid(row=0, column=6, padx=(8, 0))
        self.set_date(value, notify=False)

    @property
    def year_entry(self) -> ttk.Entry:
        return self.entries[0]

    @property
    def month_entry(self) -> ttk.Entry:
        return self.entries[1]

    @property
    def day_entry(self) -> ttk.Entry:
        return self.entries[2]

    def _advance(self, index: int) -> str:
        if index < len(self.entries) - 1:
            self.entries[index + 1].focus_set()
        else:
            self.entries[index].selection_clear()
        return "break"

    def _paste(self, _event: tk.Event) -> str | None:
        try:
            text = self.clipboard_get().strip()
            value = date.fromisoformat(text)
        except (tk.TclError, ValueError):
            return None
        self.set_date(value)
        return "break"

    def _notify_complete_date(self, _event: tk.Event | None = None) -> None:
        parts = (
            self.year_var.get().strip(),
            self.month_var.get().strip(),
            self.day_var.get().strip(),
        )
        if tuple(map(len, parts)) == (4, 2, 2):
            self._notify_date()

    def _notify_date(self, _event: tk.Event | None = None) -> None:
        if self.on_change is None:
            return
        try:
            value = self.get_date(required=False)
        except ValueError:
            return
        if value is not None:
            self.on_change(value)

    def _open_calendar(self) -> None:
        try:
            initial = self.get_date(required=False) or date.today()
        except ValueError:
            initial = date.today()
        CalendarPopup(self.calendar_button, initial, self.set_date)

    def set_date(self, value: date | None, *, notify: bool = True) -> None:
        if value is None:
            self.year_var.set("")
            self.month_var.set("")
            self.day_var.set("")
            return
        self.year_var.set(f"{value.year:04d}")
        self.month_var.set(f"{value.month:02d}")
        self.day_var.set(f"{value.day:02d}")
        if notify:
            self._notify_date()

    def set_on_change(self, callback: Callable[[date], None] | None) -> None:
        self.on_change = callback

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for entry in self.entries:
            entry.configure(state=state)
        self.calendar_button.configure(state=state)

    def get_date(self, *, required: bool = True) -> date | None:
        parts = (self.year_var.get().strip(), self.month_var.get().strip(), self.day_var.get().strip())
        if not any(parts) and (self.allow_empty or not required):
            return None
        if not all(parts):
            raise ValueError("日付をすべて入力してください。")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))

    def focus_year(self) -> None:
        self.year_entry.focus_set()


class TimeInput(tk.Frame):
    """Segmented HH:MM input."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        value: time | None = None,
        background: str | None = None,
    ) -> None:
        super().__init__(master, bg=background or master.cget("background"))
        self.hour_var = tk.StringVar()
        self.minute_var = tk.StringVar()
        self.entries: list[ttk.Entry] = []

        for column, variable in enumerate((self.hour_var, self.minute_var)):
            entry = ttk.Entry(
                self,
                textvariable=variable,
                width=2,
                justify="center",
                style="Modern.TEntry",
            )
            entry.grid(row=0, column=column * 2)
            entry.bind(
                "<FocusIn>",
                lambda _event, item=entry: item.after_idle(
                    item.select_range, 0, "end"
                ),
            )
            entry.bind("<colon>", lambda _event, index=column: self._advance(index))
            entry.bind("<space>", lambda _event, index=column: self._advance(index))
            entry.bind("<<Paste>>", self._paste)
            entry.configure(
                validate="key",
                validatecommand=(
                    self.register(
                        lambda proposed: proposed.isdigit() and len(proposed) <= 2
                        or proposed == ""
                    ),
                    "%P",
                ),
            )
            self.entries.append(entry)
            if column == 0:
                tk.Label(
                    self,
                    text=":",
                    bg=self.cget("background"),
                    padx=3,
                ).grid(row=0, column=1)

        self.set_time(value or time(0, 0))

    @property
    def hour_entry(self) -> ttk.Entry:
        return self.entries[0]

    @property
    def minute_entry(self) -> ttk.Entry:
        return self.entries[1]

    def _advance(self, index: int) -> str:
        if index == 0:
            self.minute_entry.focus_set()
        else:
            self.minute_entry.selection_clear()
        return "break"

    def _paste(self, _event: tk.Event) -> str | None:
        try:
            value = time.fromisoformat(self.clipboard_get().strip())
        except (tk.TclError, ValueError):
            return None
        self.set_time(value)
        return "break"

    def set_time(self, value: time) -> None:
        self.hour_var.set(f"{value.hour:02d}")
        self.minute_var.set(f"{value.minute:02d}")

    def get_time(self) -> time:
        hour_text = self.hour_var.get().strip()
        minute_text = self.minute_var.get().strip()
        if not hour_text or not minute_text:
            raise ValueError("時刻をすべて入力してください。")
        return time(int(hour_text), int(minute_text))

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for entry in self.entries:
            entry.configure(state=state)


class DateTimeInput(tk.Frame):
    """DateInput combined with an HH:MM input."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        value: date | datetime | None = None,
        background: str | None = None,
    ) -> None:
        super().__init__(master, bg=background or master.cget("background"))
        initial_date = value.date() if isinstance(value, datetime) else value
        initial_time = value.time() if isinstance(value, datetime) else time(0, 0)
        self.date_input = DateInput(
            self,
            value=initial_date,
            background=self.cget("background"),
        )
        self.date_input.grid(row=0, column=0, sticky="ew")
        self.columnconfigure(0, weight=1)
        tk.Label(
            self,
            text="時刻",
            bg=self.cget("background"),
            padx=8,
        ).grid(row=0, column=1)
        self.time_input = TimeInput(
            self,
            value=initial_time,
            background=self.cget("background"),
        )
        self.time_input.grid(row=0, column=2)

    def set_datetime(self, value: date | datetime) -> None:
        if isinstance(value, datetime):
            self.date_input.set_date(value.date())
            self.time_input.set_time(value.time())
        else:
            self.date_input.set_date(value)
            self.time_input.set_time(time(0, 0))

    def get_datetime(self) -> datetime:
        selected_date = self.date_input.get_date()
        if selected_date is None:
            raise ValueError("日付を入力してください。")
        return datetime.combine(selected_date, self.time_input.get_time())

    def set_enabled(self, enabled: bool) -> None:
        self.date_input.set_enabled(enabled)
        self.time_input.set_enabled(enabled)

    def focus_year(self) -> None:
        self.date_input.focus_year()

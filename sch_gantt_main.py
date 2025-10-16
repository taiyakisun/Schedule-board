import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox


DATA_FILE = os.path.join(os.path.dirname(__file__), "schedules.json")

TITLE_APP = "\u30b7\u30f3\u30d7\u30eb\u30fb\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb\uff08\u30ac\u30f3\u30c8\uff09"
LABEL_VISIBILITY = "\u8868\u793a\u53ef\u5426"
LABEL_TASK = "\u30bf\u30b9\u30af"
LABEL_GANTT = "\u30ac\u30f3\u30c8\u30c1\u30e3\u30fc\u30c8"
TEXT_ADD = "\u8ffd\u52a0"
TEXT_DELETE = "\u524a\u9664"
TEXT_UP = "\u4e0a\u3078"
TEXT_DOWN = "\u4e0b\u3078"
VISIBLE_TEXT = "\u8868\u793a"
HIDDEN_TEXT = "\u975e\u8868\u793a"
DIALOG_ADD_TITLE = "\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb\u8ffd\u52a0"
DIALOG_EDIT_TITLE = "\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb\u7de8\u96c6"
LABEL_TASK_NAME = "\u30bf\u30b9\u30af\u540d"
LABEL_START_DATE = "\u958b\u59cb\u65e5 (YYYY-MM-DD)"
LABEL_END_DATE = "\u7d42\u4e86\u65e5 (YYYY-MM-DD)"
BUTTON_OK = "OK"
BUTTON_CANCEL = "\u30ad\u30e3\u30f3\u30bb\u30eb"
ERROR_INPUT_TITLE = "\u5165\u529b\u30a8\u30e9\u30fc"
ERROR_END_BEFORE_START = "\u7d42\u4e86\u65e5\u306f\u958b\u59cb\u65e5\u4ee5\u964d\u3092\u6307\u5b9a\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
ERROR_EMPTY_TASK = "\u30bf\u30b9\u30af\u540d\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
ERROR_INVALID_DATE = "\u65e5\u4ed8\u306fYYYY-MM-DD\u5f62\u5f0f\u3067\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
ERROR_LOAD = "\u30c7\u30fc\u30bf\u306e\u8aad\u307f\u8fbc\u307f\u306b\u5931\u6557\u3057\u307e\u3057\u305f\u3002"
ERROR_SAVE = "\u30c7\u30fc\u30bf\u306e\u4fdd\u5b58\u306b\u5931\u6557\u3057\u307e\u3057\u305f\u3002"


def parse_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def format_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


@dataclass
class RowWidgets:
    container: tk.Frame
    visibility_label: tk.Label
    task_frame: tk.Frame
    task_label: tk.Label
    gantt_canvas: tk.Canvas


class ScheduleApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(TITLE_APP)
        self.root.minsize(720, 360)

        self.entries: list[dict] = []
        self.row_widgets: list[RowWidgets] = []
        self.selected_index: int | None = None

        self.task_font = tkfont.nametofont("TkDefaultFont")
        self.task_column_width = 260
        self.splitter_width = 6
        self._drag_start_x: int | None = None
        self._drag_start_width: int | None = None

        self._build_ui()
        self._load()
        self._update_initial_task_width()
        self._rebuild_rows()
        self.root.after(100, self._redraw_scale)
        self.root.after(100, self._redraw_all_gantt)

    # ----- persistence -----
    def _load(self) -> None:
        if not os.path.exists(DATA_FILE):
            return
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_LOAD}\n{exc}")
            return

        self.entries = []
        for item in raw.get("entries", []):
            try:
                self.entries.append(
                    {
                        "task": item.get("task", ""),
                        "start": parse_date(item["start"]),
                        "end": parse_date(item["end"]),
                        "visible": bool(item.get("visible", True)),
                    }
                )
            except Exception:
                continue

    def _save(self) -> None:
        data = {
            "entries": [
                {
                    "task": entry["task"],
                    "start": format_date(entry["start"]),
                    "end": format_date(entry["end"]),
                    "visible": bool(entry.get("visible", True)),
                }
                for entry in self.entries
            ]
        }
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_SAVE}\n{exc}")

    # ----- UI construction -----
    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        button_frame = tk.Frame(self.root)
        button_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        for col in range(4):
            button_frame.columnconfigure(col, weight=0)

        tk.Button(button_frame, text=TEXT_ADD, command=self._on_add).grid(row=0, column=0, padx=(0, 6))
        tk.Button(button_frame, text=TEXT_DELETE, command=self._on_delete).grid(row=0, column=1, padx=(0, 6))
        tk.Button(button_frame, text=TEXT_UP, command=self._on_up).grid(row=0, column=2, padx=(0, 6))
        tk.Button(button_frame, text=TEXT_DOWN, command=self._on_down).grid(row=0, column=3)

        header = tk.Frame(self.root)
        header.grid(row=1, column=0, sticky="ew", padx=8)
        header.columnconfigure(0, weight=0)
        header.columnconfigure(1, weight=0)
        header.columnconfigure(2, weight=0)
        header.columnconfigure(3, weight=1)

        tk.Label(header, text=LABEL_VISIBILITY, width=6, anchor="w").grid(row=0, column=0, sticky="w", padx=(4, 8))
        self.task_header_label = tk.Label(header, text=LABEL_TASK, anchor="w")
        self.task_header_label.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        tk.Label(header, text=LABEL_GANTT, anchor="w").grid(row=0, column=3, sticky="w")

        self.scale_canvas = tk.Canvas(header, height=54, highlightthickness=0, background=self.root.cget("bg"))
        self.scale_canvas.grid(row=1, column=3, sticky="ew", pady=(2, 0), padx=(0, 4))
        self.scale_canvas.bind("<Configure>", lambda _event: self._redraw_scale())

        self.splitter = tk.Frame(header, width=self.splitter_width, cursor="sb_h_double_arrow", bg="#d0d0d0")
        self.splitter.grid(row=0, column=2, rowspan=2, sticky="ns")
        self.splitter.bind("<Button-1>", self._on_splitter_press)
        self.splitter.bind("<B1-Motion>", self._on_splitter_drag)
        self.splitter.bind("<ButtonRelease-1>", self._on_splitter_release)

        self.rows_container = tk.Frame(self.root, bd=1, relief="sunken")
        self.rows_container.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self.rows_container.columnconfigure(0, weight=1)
        self.rows_container.bind("<Configure>", lambda _event: self._redraw_all_gantt())

        self._apply_column_width()

    def _apply_column_width(self) -> None:
        header = self.task_header_label.nametowidget(self.task_header_label.winfo_parent())
        header.columnconfigure(1, minsize=self.task_column_width)
        for widgets in self.row_widgets:
            widgets.container.columnconfigure(1, minsize=self.task_column_width)
            widgets.task_frame.configure(width=self.task_column_width)
            widgets.task_frame.grid_propagate(False)

    def _update_initial_task_width(self) -> None:
        if not self.entries:
            return
        longest = max((self.task_font.measure(entry["task"]) for entry in self.entries), default=0)
        self.task_column_width = max(self.task_column_width, longest + 32)
        self._apply_column_width()

    def _ensure_task_width(self, text: str) -> None:
        required = self.task_font.measure(text) + 32
        if required > self.task_column_width:
            self.task_column_width = min(required, max(200, self.root.winfo_width() - 280))
            self._apply_column_width()

    # ----- row handling -----
    def _clear_rows(self) -> None:
        for child in self.rows_container.winfo_children():
            child.destroy()
        self.row_widgets.clear()

    def _rebuild_rows(self) -> None:
        self._clear_rows()
        for index, entry in enumerate(self.entries):
            self._add_row(index, entry)
        self._refresh_selection()
        self._apply_column_width()
        self._redraw_all_gantt()
        self._redraw_scale()

    def _add_row(self, index: int, entry: dict) -> None:
        row = tk.Frame(self.rows_container)
        row.grid(row=index, column=0, sticky="ew")
        row.columnconfigure(0, weight=0)
        row.columnconfigure(1, weight=0)
        row.columnconfigure(2, weight=0)
        row.columnconfigure(3, weight=1)
        row.bind("<Button-1>", lambda _event, idx=index: self._select(idx))

        vis_label = tk.Label(row, text=VISIBLE_TEXT if entry.get("visible", True) else HIDDEN_TEXT, width=6, cursor="hand2")
        vis_label.grid(row=0, column=0, sticky="w", padx=(4, 8), pady=2)
        vis_label.bind("<Button-1>", lambda _event, idx=index: self._toggle_visibility(idx))

        task_frame = tk.Frame(row)
        task_frame.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=2)
        task_frame.columnconfigure(0, weight=1)
        task_frame.grid_propagate(False)
        task_frame.bind("<Button-1>", lambda _event, idx=index: self._select(idx))

        task_label = tk.Label(task_frame, text=entry["task"], anchor="w", justify="left")
        task_label.pack(fill="both", expand=True)
        task_label.bind("<Button-1>", lambda _event, idx=index: self._select(idx))
        task_label.bind("<Double-1>", lambda _event, idx=index: self._on_edit(idx))

        gantt_canvas = tk.Canvas(row, height=28, background="#ffffff", highlightthickness=0)
        gantt_canvas.grid(row=0, column=3, sticky="ew", padx=(0, 4), pady=2)
        gantt_canvas.bind("<Button-1>", lambda _event, idx=index: self._select(idx))
        gantt_canvas.bind("<Configure>", lambda _event, idx=index: self._redraw_gantt_for(idx))

        self.row_widgets.append(RowWidgets(row, vis_label, task_frame, task_label, gantt_canvas))

    # ----- selection -----
    def _select(self, index: int) -> None:
        if not (0 <= index < len(self.entries)):
            return
        self.selected_index = index
        self._refresh_selection()

    def _refresh_selection(self) -> None:
        default_bg = self.rows_container.cget("bg")
        selected_bg = "#d9edf7"
        for idx, widgets in enumerate(self.row_widgets):
            is_selected = idx == self.selected_index
            bg = selected_bg if is_selected else default_bg
            widgets.container.configure(bg=bg)
            widgets.visibility_label.configure(bg=bg)
            widgets.task_frame.configure(bg=bg)
            widgets.task_label.configure(bg=bg)
            widgets.gantt_canvas.configure(bg="#eef7fb" if is_selected else "#ffffff")

    # ----- button actions -----
    def _on_add(self) -> None:
        self._open_entry_dialog()

    def _on_edit(self, index: int) -> None:
        if 0 <= index < len(self.entries):
            self._open_entry_dialog(index)

    def _on_delete(self) -> None:
        if self.selected_index is None:
            return
        idx = self.selected_index
        if 0 <= idx < len(self.entries):
            del self.entries[idx]
            self.selected_index = min(idx, len(self.entries) - 1) if self.entries else None
            self._save()
            self._rebuild_rows()

    def _on_up(self) -> None:
        if self.selected_index is None or self.selected_index <= 0:
            return
        idx = self.selected_index
        self.entries[idx - 1], self.entries[idx] = self.entries[idx], self.entries[idx - 1]
        self.selected_index = idx - 1
        self._save()
        self._rebuild_rows()

    def _on_down(self) -> None:
        if self.selected_index is None or self.selected_index >= len(self.entries) - 1:
            return
        idx = self.selected_index
        self.entries[idx + 1], self.entries[idx] = self.entries[idx], self.entries[idx + 1]
        self.selected_index = idx + 1
        self._save()
        self._rebuild_rows()

    def _toggle_visibility(self, index: int) -> None:
        if not (0 <= index < len(self.entries)):
            return
        entry = self.entries[index]
        entry["visible"] = not entry.get("visible", True)
        self.row_widgets[index].visibility_label.configure(text=VISIBLE_TEXT if entry["visible"] else HIDDEN_TEXT)
        self._save()
        self._redraw_all_gantt()
        self._redraw_scale()

    # ----- dialog -----
    def _open_entry_dialog(self, index: int | None = None) -> None:
        is_edit = index is not None
        dlg = tk.Toplevel(self.root)
        dlg.title(DIALOG_EDIT_TITLE if is_edit else DIALOG_ADD_TITLE)
        dlg.grab_set()
        dlg.resizable(False, False)

        tk.Label(dlg, text=LABEL_TASK_NAME).grid(row=0, column=0, sticky="e", padx=6, pady=(8, 4))
        tk.Label(dlg, text=LABEL_START_DATE).grid(row=1, column=0, sticky="e", padx=6, pady=4)
        tk.Label(dlg, text=LABEL_END_DATE).grid(row=2, column=0, sticky="e", padx=6, pady=4)

        task_var = tk.StringVar()
        start_var = tk.StringVar()
        end_var = tk.StringVar()

        if is_edit:
            entry = self.entries[index]
            task_var.set(entry["task"])
            start_var.set(format_date(entry["start"]))
            end_var.set(format_date(entry["end"]))
        else:
            today = date.today()
            start_var.set(format_date(today))
            end_var.set(format_date(today))

        task_entry = tk.Entry(dlg, textvariable=task_var, width=36)
        start_entry = tk.Entry(dlg, textvariable=start_var, width=16)
        end_entry = tk.Entry(dlg, textvariable=end_var, width=16)
        task_entry.grid(row=0, column=1, sticky="w", padx=(0, 8), pady=(8, 4))
        start_entry.grid(row=1, column=1, sticky="w", padx=(0, 8), pady=4)
        end_entry.grid(row=2, column=1, sticky="w", padx=(0, 8), pady=4)

        button_box = tk.Frame(dlg)
        button_box.grid(row=3, column=0, columnspan=2, sticky="e", padx=8, pady=(8, 8))

        def submit() -> None:
            try:
                task_text = task_var.get().strip()
                start_value = parse_date(start_var.get())
                end_value = parse_date(end_var.get())
            except Exception:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_INVALID_DATE)
                return

            if not task_text:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_EMPTY_TASK)
                return
            if end_value < start_value:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_END_BEFORE_START)
                return

            if is_edit:
                entry = self.entries[index]
                entry.update({"task": task_text, "start": start_value, "end": end_value})
                self.selected_index = index
            else:
                self.entries.append({"task": task_text, "start": start_value, "end": end_value, "visible": True})
                self.selected_index = len(self.entries) - 1

            self._ensure_task_width(task_text)
            self._save()
            self._rebuild_rows()
            dlg.destroy()

        def cancel() -> None:
            dlg.destroy()

        tk.Button(button_box, text=BUTTON_OK, width=10, command=submit).grid(row=0, column=0)
        tk.Button(button_box, text=BUTTON_CANCEL, width=10, command=cancel).grid(row=0, column=1, padx=(8, 0))

        task_entry.focus_set()
        dlg.bind("<Return>", lambda _event: submit())
        dlg.bind("<Escape>", lambda _event: cancel())

        # Center dialog relative to the main window
        dlg.update_idletasks()
        self.root.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        dlg_w = dlg.winfo_width()
        dlg_h = dlg.winfo_height()
        x = root_x + max((root_w - dlg_w) // 2, 0)
        y = root_y + max((root_h - dlg_h) // 2, 0)
        dlg.geometry(f"+{x}+{y}")

    # ----- splitter -----
    def _on_splitter_press(self, event: tk.Event) -> None:
        self._drag_start_x = event.x_root
        self._drag_start_width = self.task_column_width

    def _on_splitter_drag(self, event: tk.Event) -> None:
        if self._drag_start_x is None or self._drag_start_width is None:
            return
        delta = event.x_root - self._drag_start_x
        new_width = self._drag_start_width + delta
        min_width = 180
        max_width = max(min_width, self.root.winfo_width() - 300)
        self.task_column_width = int(max(min_width, min(new_width, max_width)))
        self._apply_column_width()
        self._redraw_all_gantt()
        self._redraw_scale()

    def _on_splitter_release(self, _event: tk.Event) -> None:
        self._drag_start_x = None
        self._drag_start_width = None

    # ----- gantt helpers -----
    def _visible_range(self) -> tuple[date | None, date | None]:
        visible_entries = [entry for entry in self.entries if entry.get("visible", True)]
        if not visible_entries:
            return None, None
        start = min(entry["start"] for entry in visible_entries)
        end = max(entry["end"] for entry in visible_entries)
        return start, end

    def _redraw_all_gantt(self) -> None:
        for idx in range(len(self.row_widgets)):
            self._redraw_gantt_for(idx)

    def _redraw_gantt_for(self, index: int) -> None:
        if not (0 <= index < len(self.row_widgets)):
            return
        widgets = self.row_widgets[index]
        canvas = widgets.gantt_canvas
        canvas.delete("all")

        if not (0 <= index < len(self.entries)):
            return
        entry = self.entries[index]
        if not entry.get("visible", True):
            return

        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 4 or height <= 4:
            canvas.after(40, lambda idx=index: self._redraw_gantt_for(idx))
            return

        start_all, end_all = self._visible_range()
        if start_all is None or end_all is None:
            return

        vis_days = (end_all - start_all).days + 1
        if vis_days <= 0:
            vis_days = 1

        pad = 4
        usable_w = max(1, width - 2 * pad)

        def x_for(idx_value: int | float) -> float:
            return pad + usable_w * (idx_value / vis_days)

        start_idx = (entry["start"] - start_all).days
        span_days = (entry["end"] - entry["start"]).days + 1
        end_idx = start_idx + span_days

        start_idx = max(0, min(vis_days, start_idx))
        end_idx = max(0, min(vis_days, end_idx))

        x0 = x_for(start_idx)
        x1 = x_for(end_idx)
        if x1 <= x0:
            x1 = min(width - pad, x0 + 1)
        y0, y1 = 4, height - 4
        canvas.create_rectangle(x0, y0, x1, y1, fill="#4caf50", outline="")
        canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=str(span_days), fill="white")

    def _redraw_scale(self) -> None:
        if not hasattr(self, "scale_canvas"):
            return
        canvas = self.scale_canvas
        canvas.delete("all")

        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 4 or height <= 4:
            canvas.after(40, self._redraw_scale)
            return

        start_all, end_all = self._visible_range()
        if start_all is None or end_all is None:
            return

        vis_days = (end_all - start_all).days + 1
        if vis_days <= 0:
            vis_days = 1

        pad = 4
        usable_w = max(1, width - 2 * pad)
        px_per_day = usable_w / vis_days

        def x_for(idx_value: int | float) -> float:
            return pad + usable_w * (idx_value / vis_days)

        y_year = 12
        y_month = height / 2
        y_day = height - 3

        current_year = date(start_all.year, 1, 1)
        while current_year.year <= end_all.year:
            segment_start = max(start_all, date(current_year.year, 1, 1))
            segment_end = min(end_all, date(current_year.year + 1, 1, 1) - timedelta(days=1))
            if segment_start <= segment_end:
                idx0 = (segment_start - start_all).days
                idx1 = (segment_end - start_all).days + 1
                x0 = x_for(idx0)
                x1 = x_for(idx1)
                if x1 - x0 > 40:
                    canvas.create_text((x0 + x1) / 2, y_year, text=str(current_year.year), anchor="n")
            current_year = date(current_year.year + 1, 1, 1)

        current_month = date(start_all.year, start_all.month, 1)
        while current_month <= end_all:
            next_month = (current_month.replace(day=28) + timedelta(days=4)).replace(day=1)
            segment_start = max(start_all, current_month)
            segment_end = min(end_all, next_month - timedelta(days=1))
            idx0 = (segment_start - start_all).days
            idx1 = (segment_end - start_all).days + 1
            x0 = x_for(idx0)
            x1 = x_for(idx1)
            if x1 - x0 > 24:
                canvas.create_text((x0 + x1) / 2, y_month, text=str(current_month.month))
            if pad <= x0 <= width - pad:
                canvas.create_line(x0, 0, x0, height - 1, fill="#cccccc")
            current_month = next_month

        min_spacing = 24
        step = max(1, int((min_spacing / px_per_day) + 0.999))
        day_cursor = start_all
        while day_cursor <= end_all:
            idx_value = (day_cursor - start_all).days
            x = x_for(idx_value)
            canvas.create_line(x, height - 18, x, height - 1, fill="#999999")
            canvas.create_text(x, y_day, text=str(day_cursor.day), anchor="s")
            day_cursor += timedelta(days=step)

        final_day = end_all + timedelta(days=1)
        x_last = x_for(vis_days)
        canvas.create_line(x_last, height - 18, x_last, height - 1, fill="#999999")
        canvas.create_text(x_last, y_day, text=str(final_day.day), anchor="s")
        canvas.create_line(pad, height - 1, width - pad, height - 1, fill="#bdbdbd")


def main() -> None:
    root = tk.Tk()
    ScheduleApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

import copy
import json
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from excel_export import export_to_excel
from schedule_model import (
    delay_days,
    deserialize_schedule,
    find_entry,
    iter_all_entries,
    move_entry,
    new_entry,
    progress_ratio,
    progress_text,
    remove_entry,
    serialize_schedule,
)


DATA_FILE = os.path.join(os.path.dirname(__file__), "schedules.json")
COMPLETE_LOG_FILE = os.path.join(os.path.dirname(__file__), "completed_tasks.jsonl")

TITLE_APP = "Schedule Board（ガントチャート）"
LABEL_VISIBILITY = "表示"
LABEL_TASK = "タスク"
LABEL_PROGRESS = "進捗度"
LABEL_DELAY = "遅延日数"
LABEL_COMPLETE = "完了"
LABEL_GANTT = "ガントチャート"
TEXT_ADD_PARENT = "親を追加"
TEXT_ADD_CHILD = "子を追加"
TEXT_DELETE = "削除"
TEXT_UP = "上へ"
TEXT_DOWN = "下へ"
TEXT_COMPLETE = "完了"
TEXT_EXPORT_EXCEL = "Excel出力"
TEXT_RELOAD_INCOMPLETE = "未完了タスクの再読み込み"
VISIBLE_TEXT = "表示"
HIDDEN_TEXT = "非表示"
PARENT_HIDDEN_TEXT = "親非表示"
TEXT_COLLAPSE = "▼"
TEXT_EXPAND = "▶"
TEXT_PARENT = "親"
TEXT_CHILD = "子"
TEXT_PERCENT_MODE = "0～100%"
TEXT_VALUE_MODE = "指定数値"
COMPLETE_BUTTON_WIDTH = 8
ROW_CONTENT_MIN_HEIGHT = 40
VISIBILITY_COLUMN_WIDTH = 82
PROGRESS_COLUMN_MIN_WIDTH = 78
PROGRESS_COLUMN_MAX_WIDTH = 220
PROGRESS_COLUMN_PADDING = 16

DIALOG_ADD_PARENT_TITLE = "親スケジュール追加"
DIALOG_ADD_CHILD_TITLE = "子スケジュール追加"
DIALOG_EDIT_TITLE = "スケジュール編集"
LABEL_TASK_NAME = "タスク名"
LABEL_START_DATE = "開始日 (YYYY-MM-DD)"
LABEL_END_DATE = "終了日 (YYYY-MM-DD)"
LABEL_PROGRESS_MODE = "進捗の単位"
LABEL_PROGRESS_VALUE = "現在の進捗"
LABEL_PROGRESS_TOTAL = "分母"
BUTTON_OK = "OK"
BUTTON_CANCEL = "キャンセル"

ERROR_INPUT_TITLE = "入力エラー"
ERROR_END_BEFORE_START = "終了日は開始日以降を指定してください。"
ERROR_EMPTY_TASK = "タスク名を入力してください。"
ERROR_INVALID_DATE = "日付はYYYY-MM-DD形式で入力してください。"
ERROR_INVALID_PROGRESS = "進捗は0以上の数値で入力してください。"
ERROR_PERCENT_RANGE = "パーセントの進捗は0～100で入力してください。"
ERROR_VALUE_RANGE = "指定数値の分母は0より大きく、進捗は分母以下で入力してください。"
ERROR_LOAD = "データの読み込みに失敗しました。"
ERROR_SAVE = "データの保存に失敗しました。"
ERROR_SAVE_AFTER_LOAD = "読み込みに失敗したデータを保護するため、保存を中止しました。アプリを終了し、schedules.jsonを確認してください。"
ERROR_COMPLETE_LOG_WRITE = "完了ログの書き込みに失敗しました。"
ERROR_COMPLETE_LOG_READ = "完了ログの読み込みに失敗しました。"
ERROR_EXCEL_EXPORT = "Excelファイルの出力に失敗しました。"
INFO_EXCEL_EXPORT_TITLE = "Excel出力"
INFO_EXCEL_EXPORT = "Excelファイルを出力しました。\n{path}"
WARNING_SELECT_PARENT_TITLE = "親の選択が必要です"
WARNING_SELECT_PARENT_MESSAGE = "子を追加する親、またはその親に属する子を選択してください。"

CONFIRM_DELETE_TITLE = "削除確認"
CONFIRM_DELETE_MESSAGE = "「{task}」を削除しますか？"
CONFIRM_DELETE_PARENT_MESSAGE = "「{task}」と配下の子タスク{count}件をすべて削除しますか？"
CONFIRM_COMPLETE_TITLE = "完了確認"
CONFIRM_COMPLETE_MESSAGE = "「{task}」を完了にしますか？"
CONFIRM_COMPLETE_PARENT_MESSAGE = "「{task}」と配下の子タスク{count}件をすべて完了にしますか？"

LOG_FIELD_TASK = "タスク名"
LOG_FIELD_START = "開始日"
LOG_FIELD_END = "終了日"
LOG_FIELD_COMPLETED_AT = "完了日時"
LOG_FIELD_COMPLETED = "完了状態"
LOG_FIELD_ID = "ID"
LOG_FIELD_KIND = "種別"
LOG_FIELD_PARENT_ID = "親ID"
LOG_FIELD_VISIBLE = "表示"
LOG_FIELD_PROGRESS_MODE = "進捗モード"
LOG_FIELD_PROGRESS_VALUE = "進捗値"
LOG_FIELD_PROGRESS_TOTAL = "進捗分母"

JST = timezone(timedelta(hours=9))
JST_MONITOR_MS = 30_000

COLOR_APP_BG = "#F7F7F5"
COLOR_SURFACE = "#FFFFFF"
COLOR_SURFACE_ALT = "#FAFAF8"
COLOR_HEADER = "#F1F1EE"
COLOR_TEXT = "#202124"
COLOR_TEXT_MUTED = "#6B6B66"
COLOR_BORDER = "#D8D7D2"
COLOR_BORDER_SOFT = "#E8E7E3"
COLOR_GRID = "#F0EFEC"
COLOR_PRIMARY = "#5B5CE2"
COLOR_PRIMARY_HOVER = "#4748C8"
COLOR_PRIMARY_SOFT = "#EEEEFF"
COLOR_SELECTED_GANTT = "#F6F5FF"
COLOR_DANGER = "#B42318"
COLOR_DANGER_HOVER = "#8F1C14"
COLOR_DANGER_SOFT = "#FFF1F0"
COLOR_SUCCESS = "#166534"
COLOR_SUCCESS_HOVER = "#14532D"
COLOR_SUCCESS_SOFT = "#ECFDF3"
COLOR_WARNING = "#92400E"
COLOR_WARNING_SOFT = "#FFFBEB"
COLOR_PARENT_REMAINING = "#C7D2FE"
COLOR_PARENT_COMPLETE = "#5B5CE2"
COLOR_CHILD_REMAINING = "#BDEBDD"
COLOR_CHILD_COMPLETE = "#0F9F6E"
COLOR_WEEKEND = "#F7F6F3"
COLOR_SELECTED_WEEKEND = "#EFEEFA"
TODAY_HIGHLIGHT_BG = "#FFF0EE"
TODAY_LINE_COLOR = "#E5484D"


def today_in_jst() -> date:
    return datetime.now(JST).date()


def parse_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def format_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def current_jst_timestamp() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def entry_key(task: str, start: date, end: date) -> tuple[str, str, str, str]:
    return "legacy", task, format_date(start), format_date(end)


def number_text(value: float | int) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return str(int(numeric))
    return repr(numeric)


def create_rounded_rectangle(
    canvas: tk.Canvas,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    radius: float,
    **options,
) -> int:
    radius = max(0, min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
    points = (
        x0 + radius,
        y0,
        x1 - radius,
        y0,
        x1,
        y0,
        x1,
        y0 + radius,
        x1,
        y1 - radius,
        x1,
        y1,
        x1 - radius,
        y1,
        x0 + radius,
        y1,
        x0,
        y1,
        x0,
        y1 - radius,
        x0,
        y0 + radius,
        x0,
        y0,
    )
    return canvas.create_polygon(points, smooth=True, splinesteps=12, **options)


@dataclass
class RowWidgets:
    entry_id: str
    container: tk.Frame
    selection_bar: tk.Frame
    visibility_label: tk.Label
    task_frame: tk.Frame
    tree_indicator: tk.Label
    task_label: tk.Label
    progress_frame: tk.Frame
    progress_label: tk.Label
    progress_canvas: tk.Canvas
    delay_label: tk.Label
    complete_button: ttk.Button
    gantt_canvas: tk.Canvas
    base_bg: str


class ScheduleApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(TITLE_APP)
        self.root.configure(bg=COLOR_APP_BG)
        self.root.minsize(1050, 560)
        initial_width = min(1360, max(1050, self.root.winfo_screenwidth() - 120))
        initial_height = min(760, max(560, self.root.winfo_screenheight() - 160))
        self.root.geometry(f"{initial_width}x{initial_height}")

        self.schedule: dict = {"version": 2, "parents": []}
        self.entries: list[dict] = self.schedule["parents"]
        self.load_failed = False
        self.row_widgets: list[RowWidgets] = []
        self.selected_id: str | None = None

        self.task_font = tkfont.nametofont("TkDefaultFont")
        self.task_font.configure(size=10)
        self.parent_font = self.task_font.copy()
        self.parent_font.configure(weight="bold")
        self.title_font = self.task_font.copy()
        self.title_font.configure(size=18, weight="bold")
        self.subtitle_font = self.task_font.copy()
        self.subtitle_font.configure(size=9)
        self.header_font = self.task_font.copy()
        self.header_font.configure(size=9, weight="bold")
        self.button_font = self.task_font.copy()
        self.button_font.configure(size=9, weight="bold")
        self.small_font = self.task_font.copy()
        self.small_font.configure(size=8)
        self._configure_theme()
        self.row_content_height = max(
            ROW_CONTENT_MIN_HEIGHT,
            self.task_font.metrics("linespace") + 8,
            self.parent_font.metrics("linespace") + 8,
        )
        self.task_column_width = 320
        self.progress_column_width = PROGRESS_COLUMN_MIN_WIDTH
        self.delay_column_width = 76
        self.complete_column_width = self._measure_complete_button_width()
        self.splitter_width = 6
        self._drag_start_x: int | None = None
        self._drag_start_width: int | None = None
        self.current_jst_date = today_in_jst()
        self.today_label_screen_x: float | None = None

        self._build_ui()
        self._load()
        self._update_initial_task_width()
        self._rebuild_rows()
        self.root.after(100, self._redraw_scale)
        self.root.after(100, self._redraw_all_gantt)
        self.root.after(JST_MONITOR_MS, self._monitor_jst_date)

    def _configure_theme(self) -> None:
        self.root.option_add("*Font", self.task_font)
        self.style = ttk.Style(self.root)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.style.configure(
            ".",
            background=COLOR_APP_BG,
            foreground=COLOR_TEXT,
            font=self.task_font,
        )
        self.style.configure(
            "Primary.TButton",
            background=COLOR_PRIMARY,
            foreground="white",
            bordercolor=COLOR_PRIMARY,
            lightcolor=COLOR_PRIMARY,
            darkcolor=COLOR_PRIMARY,
            borderwidth=1,
            focusthickness=2,
            focuscolor=COLOR_PRIMARY_HOVER,
            padding=(14, 8),
            font=self.button_font,
        )
        self.style.map(
            "Primary.TButton",
            background=[("pressed", COLOR_PRIMARY_HOVER), ("active", COLOR_PRIMARY_HOVER)],
            bordercolor=[("focus", COLOR_TEXT), ("pressed", COLOR_PRIMARY_HOVER)],
        )
        self.style.configure(
            "Secondary.TButton",
            background=COLOR_SURFACE,
            foreground=COLOR_TEXT,
            bordercolor=COLOR_BORDER,
            lightcolor=COLOR_BORDER,
            darkcolor=COLOR_BORDER,
            borderwidth=1,
            focusthickness=2,
            focuscolor=COLOR_PRIMARY,
            padding=(12, 7),
            font=self.button_font,
        )
        self.style.map(
            "Secondary.TButton",
            background=[("pressed", COLOR_HEADER), ("active", COLOR_SURFACE_ALT)],
            bordercolor=[("focus", COLOR_PRIMARY), ("active", COLOR_BORDER)],
        )
        self.style.configure(
            "Danger.TButton",
            background=COLOR_DANGER_SOFT,
            foreground=COLOR_DANGER,
            bordercolor=COLOR_DANGER_SOFT,
            lightcolor=COLOR_DANGER_SOFT,
            darkcolor=COLOR_DANGER_SOFT,
            borderwidth=1,
            focusthickness=2,
            focuscolor=COLOR_DANGER,
            padding=(12, 7),
            font=self.button_font,
        )
        self.style.map(
            "Danger.TButton",
            background=[("pressed", "#FFE4E1"), ("active", "#FFE4E1")],
            foreground=[("pressed", COLOR_DANGER_HOVER), ("active", COLOR_DANGER_HOVER)],
            bordercolor=[("focus", COLOR_DANGER)],
        )
        self.style.configure(
            "Success.TButton",
            background=COLOR_SUCCESS_SOFT,
            foreground=COLOR_SUCCESS,
            bordercolor=COLOR_SUCCESS_SOFT,
            lightcolor=COLOR_SUCCESS_SOFT,
            darkcolor=COLOR_SUCCESS_SOFT,
            borderwidth=1,
            focusthickness=2,
            focuscolor=COLOR_SUCCESS,
            padding=(10, 5),
            font=self.button_font,
        )
        self.style.map(
            "Success.TButton",
            background=[("pressed", "#D1FAE5"), ("active", "#D1FAE5")],
            foreground=[("pressed", COLOR_SUCCESS_HOVER), ("active", COLOR_SUCCESS_HOVER)],
            bordercolor=[("focus", COLOR_SUCCESS)],
        )
        self.style.configure(
            "Modern.TEntry",
            fieldbackground=COLOR_SURFACE,
            foreground=COLOR_TEXT,
            bordercolor=COLOR_BORDER,
            lightcolor=COLOR_BORDER,
            darkcolor=COLOR_BORDER,
            insertcolor=COLOR_TEXT,
            focusthickness=2,
            focuscolor=COLOR_PRIMARY,
            padding=7,
        )
        self.style.map(
            "Modern.TEntry",
            bordercolor=[("focus", COLOR_PRIMARY)],
            lightcolor=[("focus", COLOR_PRIMARY)],
            darkcolor=[("focus", COLOR_PRIMARY)],
        )
        self.style.configure(
            "Modern.TRadiobutton",
            background=COLOR_SURFACE,
            foreground=COLOR_TEXT,
            focuscolor=COLOR_PRIMARY,
            padding=(0, 4),
        )
        self.style.map(
            "Modern.TRadiobutton",
            background=[("active", COLOR_SURFACE)],
        )
        self.style.configure(
            "Modern.Vertical.TScrollbar",
            background=COLOR_BORDER,
            troughcolor=COLOR_SURFACE_ALT,
            bordercolor=COLOR_SURFACE_ALT,
            lightcolor=COLOR_BORDER,
            darkcolor=COLOR_BORDER,
            arrowcolor=COLOR_TEXT_MUTED,
            borderwidth=0,
        )

    def _monitor_jst_date(self) -> None:
        latest = today_in_jst()
        if latest != self.current_jst_date:
            self.current_jst_date = latest
            if hasattr(self, "today_label"):
                self.today_label.configure(text=latest.strftime("%Y年%m月%d日"))
            self._refresh_delay_labels()
            self._redraw_scale()
            self._redraw_all_gantt()
        self.root.after(JST_MONITOR_MS, self._monitor_jst_date)

    # ----- persistence -----
    def _load(self) -> None:
        if not os.path.exists(DATA_FILE):
            self.load_failed = False
            return
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            self.schedule = deserialize_schedule(raw)
            self.entries = self.schedule["parents"]
            self.load_failed = False
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_LOAD}\n{exc}")
            self.load_failed = True

    def _save(self) -> bool:
        if getattr(self, "load_failed", False):
            messagebox.showerror(ERROR_INPUT_TITLE, ERROR_SAVE_AFTER_LOAD)
            return False
        temp_file = f"{DATA_FILE}.tmp"
        try:
            data = serialize_schedule(self.schedule)
            with open(temp_file, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            os.replace(temp_file, DATA_FILE)
        except Exception as exc:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except OSError:
                pass
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_SAVE}\n{exc}")
            return False
        return True

    def _snapshot_schedule(self) -> dict:
        return copy.deepcopy(self.schedule)

    def _restore_schedule(self, snapshot: dict) -> None:
        self.schedule = snapshot
        self.entries = self.schedule["parents"]

    def _save_or_restore(self, snapshot: dict) -> bool:
        if self._save():
            return True
        self._restore_schedule(snapshot)
        return False

    def _completion_record(self, entry: dict) -> dict:
        return {
            LOG_FIELD_TASK: entry["task"],
            LOG_FIELD_START: format_date(entry["start"]),
            LOG_FIELD_END: format_date(entry["end"]),
            LOG_FIELD_COMPLETED_AT: current_jst_timestamp(),
            LOG_FIELD_COMPLETED: True,
            LOG_FIELD_ID: entry["id"],
            LOG_FIELD_KIND: TEXT_PARENT if entry["kind"] == "parent" else TEXT_CHILD,
            LOG_FIELD_PARENT_ID: entry.get("parent_id"),
            LOG_FIELD_VISIBLE: bool(entry.get("visible", True)),
            LOG_FIELD_PROGRESS_MODE: entry.get("progress_mode", "percent"),
            LOG_FIELD_PROGRESS_VALUE: entry.get("progress_value", 0),
            LOG_FIELD_PROGRESS_TOTAL: entry.get("progress_total", 100),
        }

    def _append_completion_logs(self, entries: list[dict]) -> bool:
        records = [self._completion_record(entry) for entry in entries]
        try:
            with open(COMPLETE_LOG_FILE, "a", encoding="utf-8", newline="\n") as fh:
                fh.writelines(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_COMPLETE_LOG_WRITE}\n{exc}")
            return False
        return True

    def _load_latest_completion_states(self) -> dict[tuple, dict] | None:
        if not os.path.exists(COMPLETE_LOG_FILE):
            return {}

        latest_records: dict[tuple, dict] = {}
        try:
            with open(COMPLETE_LOG_FILE, "r", encoding="utf-8") as fh:
                for line_no, line in enumerate(fh, start=1):
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        raw = json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"{line_no}行目: JSONの解析に失敗しました。 {exc}") from exc
                    if not isinstance(raw, dict):
                        raise ValueError(f"{line_no}行目: JSONオブジェクトを記載してください。")
                    missing = [
                        field
                        for field in (
                            LOG_FIELD_TASK,
                            LOG_FIELD_START,
                            LOG_FIELD_END,
                            LOG_FIELD_COMPLETED_AT,
                            LOG_FIELD_COMPLETED,
                        )
                        if field not in raw
                    ]
                    if missing:
                        raise ValueError(f"{line_no}行目: 必須キーが不足しています。 {', '.join(missing)}")

                    task = str(raw[LOG_FIELD_TASK])
                    try:
                        start = parse_date(str(raw[LOG_FIELD_START]))
                        end = parse_date(str(raw[LOG_FIELD_END]))
                    except Exception as exc:
                        raise ValueError(f"{line_no}行目: 開始日または終了日が不正です。") from exc

                    record_id = str(raw.get(LOG_FIELD_ID, "")).strip()
                    key = ("id", record_id) if record_id else entry_key(task, start, end)
                    latest_records.pop(key, None)
                    latest_records[key] = {
                        **raw,
                        "task": task,
                        "start": start,
                        "end": end,
                    }
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_COMPLETE_LOG_READ}\n{exc}")
            return None
        return latest_records

    # ----- model helpers -----
    def _display_items(self) -> list[tuple[dict, dict]]:
        rows: list[tuple[dict, dict]] = []
        for parent in self.entries:
            rows.append((parent, parent))
            if not parent.get("collapsed", False):
                rows.extend((child, parent) for child in parent.get("children", []))
        return rows

    def _find(self, entry_id: str | None):
        if not entry_id:
            return None
        return find_entry(self.schedule, entry_id)

    def _parent_for(self, entry: dict) -> dict | None:
        if entry.get("kind") == "parent":
            return entry
        location = self._find(entry.get("id"))
        return location.parent if location is not None else None

    def _effective_visible(self, entry: dict, parent: dict) -> bool:
        if entry.get("kind") == "parent":
            return bool(entry.get("visible", True))
        return bool(parent.get("visible", True) and entry.get("visible", True))

    def _delay_days(self, entry: dict) -> int:
        return delay_days(entry, self.current_jst_date)

    def _visibility_text(self, entry: dict, parent: dict) -> str:
        if not entry.get("visible", True):
            return HIDDEN_TEXT
        if entry.get("kind") == "child" and not parent.get("visible", True):
            return PARENT_HIDDEN_TEXT
        return VISIBLE_TEXT

    # ----- UI construction -----
    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        topbar = tk.Frame(
            self.root,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SOFT,
        )
        topbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))
        topbar.columnconfigure(0, weight=1)
        tk.Frame(topbar, width=4, bg=COLOR_PRIMARY).place(x=0, y=0, relheight=1)

        brand_frame = tk.Frame(topbar, bg=COLOR_SURFACE)
        brand_frame.grid(row=0, column=0, sticky="w", padx=20, pady=(16, 8))
        tk.Label(
            brand_frame,
            text="PROJECT TIMELINE",
            bg=COLOR_SURFACE,
            fg=COLOR_PRIMARY,
            font=self.small_font,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 3))
        tk.Label(
            brand_frame,
            text="Schedule Board",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=self.title_font,
            anchor="w",
        ).grid(row=1, column=0, sticky="w")
        tk.Label(
            brand_frame,
            text="タスクと進捗を、ひとつのタイムラインで管理",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=self.subtitle_font,
            anchor="w",
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

        overview_frame = tk.Frame(topbar, bg=COLOR_SURFACE)
        overview_frame.grid(row=0, column=1, sticky="e", padx=20, pady=(16, 8))
        self.summary_label = tk.Label(
            overview_frame,
            text="0グループ  •  0タスク",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=self.header_font,
            anchor="e",
        )
        self.summary_label.grid(row=0, column=0, sticky="e")
        self.today_label = tk.Label(
            overview_frame,
            text=self.current_jst_date.strftime("%Y年%m月%d日"),
            bg=COLOR_PRIMARY_SOFT,
            fg=COLOR_PRIMARY,
            font=self.small_font,
            anchor="e",
            padx=8,
            pady=3,
        )
        self.today_label.grid(row=1, column=0, sticky="e", pady=(6, 0))

        button_frame = tk.Frame(topbar, bg=COLOR_SURFACE)
        button_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=(4, 16))
        button_frame.columnconfigure(6, weight=1)
        self.toolbar_buttons: dict[str, ttk.Button] = {}

        button_specs = (
            (0, TEXT_ADD_PARENT, "＋ 親を追加", self._on_add_parent, "Primary.TButton"),
            (1, TEXT_ADD_CHILD, "＋ 子を追加", self._on_add_child, "Secondary.TButton"),
            (3, TEXT_UP, "↑ 上へ", self._on_up, "Secondary.TButton"),
            (4, TEXT_DOWN, "↓ 下へ", self._on_down, "Secondary.TButton"),
            (5, TEXT_DELETE, "削除", self._on_delete, "Danger.TButton"),
            (7, TEXT_EXPORT_EXCEL, "Excel出力", self._on_export_excel, "Secondary.TButton"),
            (
                8,
                TEXT_RELOAD_INCOMPLETE,
                "↻ 未完了タスクを再読込",
                self._on_reload_incomplete_tasks,
                "Secondary.TButton",
            ),
        )
        ttk.Separator(button_frame, orient="vertical").grid(
            row=0, column=2, sticky="ns", padx=10, pady=2
        )
        for column, key, text, command, style_name in button_specs:
            button = ttk.Button(
                button_frame,
                text=text,
                command=command,
                style=style_name,
                cursor="hand2",
            )
            button.grid(row=0, column=column, sticky="w", padx=(0, 7))
            self.toolbar_buttons[key] = button

        self.header = tk.Frame(
            self.root,
            bg=COLOR_HEADER,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SOFT,
        )
        self.header.grid(row=1, column=0, sticky="ew", padx=(16, 16))
        for column in range(7):
            self.header.columnconfigure(column, weight=1 if column == 6 else 0)

        self.header_labels: dict[str, tk.Label] = {}
        header_specs = (
            (0, LABEL_VISIBILITY, 8, (12, 8)),
            (1, LABEL_TASK, None, (0, 8)),
            (2, LABEL_PROGRESS, None, (0, 8)),
            (3, LABEL_DELAY, None, (0, 8)),
            (4, LABEL_COMPLETE, None, (0, 8)),
            (6, LABEL_GANTT, None, (8, 8)),
        )
        for column, text, width, padding in header_specs:
            label = tk.Label(
                self.header,
                text=text,
                width=width,
                anchor="w",
                bg=COLOR_HEADER,
                fg=COLOR_TEXT_MUTED,
                font=self.header_font,
            )
            label.grid(
                row=0,
                column=column,
                rowspan=1 if column == 6 else 2,
                sticky="nsew",
                padx=padding,
                pady=(10, 6),
            )
            self.header_labels[text] = label
        self.task_header_label = self.header_labels[LABEL_TASK]

        self.scale_canvas = tk.Canvas(
            self.header,
            height=58,
            highlightthickness=0,
            background=COLOR_HEADER,
        )
        self.scale_canvas.grid(row=1, column=6, sticky="ew", padx=(0, 4))
        self.scale_canvas.bind("<Configure>", lambda _event: self._redraw_scale())

        self.splitter = tk.Frame(
            self.header,
            width=self.splitter_width,
            cursor="sb_h_double_arrow",
            bg=COLOR_BORDER_SOFT,
        )
        self.splitter.grid(row=0, column=5, rowspan=2, sticky="ns")
        self.splitter.bind("<Button-1>", self._on_splitter_press)
        self.splitter.bind("<B1-Motion>", self._on_splitter_drag)
        self.splitter.bind("<ButtonRelease-1>", self._on_splitter_release)

        rows_shell = tk.Frame(
            self.root,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SOFT,
        )
        rows_shell.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 16))
        rows_shell.columnconfigure(0, weight=1)
        rows_shell.rowconfigure(0, weight=1)

        self.rows_canvas = tk.Canvas(
            rows_shell,
            highlightthickness=0,
            background=COLOR_SURFACE,
        )
        self.rows_canvas.grid(row=0, column=0, sticky="nsew")
        self.rows_scrollbar = ttk.Scrollbar(
            rows_shell,
            orient="vertical",
            command=self.rows_canvas.yview,
            style="Modern.Vertical.TScrollbar",
        )
        self.rows_scrollbar.grid(row=0, column=1, sticky="ns")
        self.rows_canvas.configure(yscrollcommand=self.rows_scrollbar.set)
        self.header.grid_configure(padx=(16, 16 + self.rows_scrollbar.winfo_reqwidth()))

        self.rows_container = tk.Frame(self.rows_canvas, bg=COLOR_SURFACE)
        self.rows_window = self.rows_canvas.create_window((0, 0), window=self.rows_container, anchor="nw")
        self.rows_container.columnconfigure(0, weight=1)
        self.rows_container.bind("<Configure>", self._on_rows_container_configure)
        self.rows_canvas.bind("<Configure>", self._on_rows_canvas_configure)
        self.rows_canvas.bind("<MouseWheel>", self._on_rows_mousewheel)
        self.rows_container.bind("<MouseWheel>", self._on_rows_mousewheel)

        self._apply_column_width()

    def _on_rows_mousewheel(self, event: tk.Event) -> str:
        if event.delta:
            self.rows_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _on_rows_container_configure(self, _event: tk.Event) -> None:
        self.rows_canvas.configure(scrollregion=self.rows_canvas.bbox("all"))
        self._redraw_all_gantt()

    def _on_rows_canvas_configure(self, event: tk.Event) -> None:
        self.rows_canvas.itemconfigure(self.rows_window, width=event.width)
        self._redraw_all_gantt()

    def _apply_column_width(self) -> None:
        self.header.columnconfigure(0, minsize=VISIBILITY_COLUMN_WIDTH)
        self.header.columnconfigure(1, minsize=self.task_column_width + 8)
        self.header.columnconfigure(2, minsize=self.progress_column_width)
        self.header.columnconfigure(3, minsize=self.delay_column_width)
        self.header.columnconfigure(4, minsize=self.complete_column_width + 8)
        for widgets in self.row_widgets:
            row = widgets.container
            row.columnconfigure(0, minsize=VISIBILITY_COLUMN_WIDTH)
            row.columnconfigure(1, minsize=self.task_column_width)
            row.columnconfigure(2, minsize=self.progress_column_width)
            row.columnconfigure(3, minsize=self.delay_column_width)
            row.columnconfigure(4, minsize=self.complete_column_width)
            widgets.task_frame.configure(width=self.task_column_width, height=self.row_content_height)
            widgets.task_frame.grid_propagate(False)

    def _measure_complete_button_width(self) -> int:
        probe = ttk.Button(
            self.root,
            text=f"✓ {TEXT_COMPLETE}",
            width=COMPLETE_BUTTON_WIDTH,
            style="Success.TButton",
        )
        width = probe.winfo_reqwidth()
        probe.destroy()
        return width

    def _update_initial_task_width(self) -> None:
        all_entries = list(iter_all_entries(self.schedule))
        if not all_entries:
            return
        longest = max(
            (self.task_font.measure(entry["task"]) + (32 if entry["kind"] == "child" else 0) for entry in all_entries),
            default=0,
        )
        self.task_column_width = max(self.task_column_width, longest + 44)
        self._apply_column_width()

    def _ensure_task_width(self, text: str, kind: str) -> None:
        required = self.task_font.measure(text) + 44 + (32 if kind == "child" else 0)
        if required > self.task_column_width:
            self.task_column_width = min(required, max(220, self.root.winfo_width() - 580))
            self._apply_column_width()

    def _update_progress_column_width(self) -> None:
        measured_widths = [self.task_font.measure(LABEL_PROGRESS)]
        measured_widths.extend(
            self.task_font.measure(progress_text(entry))
            for entry in iter_all_entries(self.schedule)
        )
        required = max(measured_widths, default=0) + PROGRESS_COLUMN_PADDING
        self.progress_column_width = max(
            PROGRESS_COLUMN_MIN_WIDTH,
            min(PROGRESS_COLUMN_MAX_WIDTH, required),
        )

    # ----- row handling -----
    def _clear_rows(self) -> None:
        for child in self.rows_container.winfo_children():
            child.destroy()
        self.row_widgets.clear()

    def _rebuild_rows(self) -> None:
        self._update_progress_column_width()
        self._clear_rows()
        display_items = self._display_items()
        for row_index, (entry, parent) in enumerate(display_items):
            self._add_row(row_index, entry, parent)
        if not display_items:
            self._show_empty_state()
        self._update_summary_label()
        self._refresh_selection()
        self._apply_column_width()
        self._refresh_delay_labels()
        self._redraw_all_gantt()
        self._redraw_scale()

    def _update_summary_label(self) -> None:
        if not hasattr(self, "summary_label"):
            return
        parent_count = len(self.entries)
        tasks = list(iter_all_entries(self.schedule))
        task_count = len(tasks)
        average_progress = (
            sum(progress_ratio(entry) for entry in tasks) / task_count
            if task_count
            else 0
        )
        self.summary_label.configure(
            text=f"{parent_count}グループ  ·  {task_count}タスク  ·  平均 {average_progress:.0%}"
        )

    def _show_empty_state(self) -> None:
        empty_frame = tk.Frame(self.rows_container, bg=COLOR_SURFACE, height=260)
        empty_frame.grid(row=0, column=0, sticky="nsew")
        empty_frame.grid_propagate(False)
        empty_frame.columnconfigure(0, weight=1)
        empty_frame.rowconfigure(0, weight=1)
        content = tk.Frame(empty_frame, bg=COLOR_SURFACE)
        content.grid(row=0, column=0)
        tk.Label(
            content,
            text="＋",
            bg=COLOR_PRIMARY_SOFT,
            fg=COLOR_PRIMARY,
            font=self.title_font,
            width=3,
            height=1,
        ).grid(row=0, column=0, pady=(0, 12))
        tk.Label(
            content,
            text="最初のスケジュールを追加しましょう",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=self.parent_font,
        ).grid(row=1, column=0)
        tk.Label(
            content,
            text="「親を追加」からプロジェクトや作業グループを作成できます。",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=self.subtitle_font,
        ).grid(row=2, column=0, pady=(6, 0))

    def _add_row(self, row_index: int, entry: dict, parent: dict) -> None:
        entry_id = entry["id"]
        is_child = entry["kind"] == "child"
        base_bg = COLOR_SURFACE_ALT if row_index % 2 else COLOR_SURFACE
        row = tk.Frame(
            self.rows_container,
            bg=base_bg,
            highlightthickness=0,
        )
        row.grid(row=row_index, column=0, sticky="ew")
        for column in range(7):
            row.columnconfigure(column, weight=1 if column == 6 else 0)
        row.bind("<Button-1>", lambda _event, item_id=entry_id: self._select(item_id))
        row.bind("<MouseWheel>", self._on_rows_mousewheel)

        selection_bar = tk.Frame(row, width=4, bg=base_bg)
        selection_bar.place(x=0, y=0, relheight=1)

        visibility_text = self._visibility_text(entry, parent)
        if visibility_text == VISIBLE_TEXT:
            visibility_color = COLOR_SUCCESS
            visibility_bg = COLOR_SUCCESS_SOFT
            visibility_symbol = "●"
        elif visibility_text == PARENT_HIDDEN_TEXT:
            visibility_color = COLOR_WARNING
            visibility_bg = COLOR_WARNING_SOFT
            visibility_symbol = "○"
        else:
            visibility_color = COLOR_TEXT_MUTED
            visibility_bg = COLOR_HEADER
            visibility_symbol = "○"

        vis_label = tk.Label(
            row,
            text=f"{visibility_symbol} {visibility_text}",
            width=8,
            cursor="hand2",
            anchor="w",
            bg=visibility_bg,
            fg=visibility_color,
            font=self.small_font,
            padx=4,
            pady=2,
        )
        vis_label.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=4)
        vis_label.bind("<Button-1>", lambda _event, item_id=entry_id: self._toggle_visibility(item_id))
        vis_label.bind("<MouseWheel>", self._on_rows_mousewheel)

        task_frame = tk.Frame(row, height=self.row_content_height, bg=base_bg)
        task_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 8), pady=4)
        task_frame.columnconfigure(1, weight=1)
        task_frame.grid_propagate(False)
        task_frame.bind("<Button-1>", lambda _event, item_id=entry_id: self._select(item_id))
        task_frame.bind("<MouseWheel>", self._on_rows_mousewheel)

        if is_child:
            children = parent.get("children", [])
            branch = "└─" if children and children[-1]["id"] == entry_id else "├─"
            tree_indicator = tk.Label(
                task_frame,
                text=branch,
                anchor="w",
                bg=base_bg,
                fg=COLOR_BORDER,
                font=self.task_font,
            )
            tree_indicator.grid(row=0, column=0, sticky="w", padx=(22, 6))
            tree_indicator.bind(
                "<Button-1>", lambda _event, item_id=entry_id: self._select(item_id)
            )
        else:
            has_children = bool(entry.get("children"))
            tree_indicator = tk.Label(
                task_frame,
                text=(
                    TEXT_EXPAND if entry.get("collapsed", False) else TEXT_COLLAPSE
                ) if has_children else "•",
                width=2,
                anchor="center",
                cursor="hand2" if has_children else "arrow",
                bg=base_bg,
                fg=COLOR_PRIMARY if has_children else COLOR_BORDER,
                font=self.header_font,
            )
            tree_indicator.grid(row=0, column=0, sticky="w", padx=(0, 4))
            if has_children:
                tree_indicator.bind(
                    "<Button-1>",
                    lambda _event, item_id=entry_id: self._toggle_collapsed(item_id),
                )
        tree_indicator.bind("<MouseWheel>", self._on_rows_mousewheel)

        task_label = tk.Label(
            task_frame,
            text=entry["task"],
            anchor="w",
            justify="left",
            font=self.task_font if is_child else self.parent_font,
            bg=base_bg,
            fg=COLOR_TEXT,
        )
        task_label.grid(row=0, column=1, sticky="nsew")
        task_label.bind("<Button-1>", lambda _event, item_id=entry_id: self._select(item_id))
        task_label.bind("<Double-1>", lambda _event, item_id=entry_id: self._on_edit(item_id))
        task_label.bind("<MouseWheel>", self._on_rows_mousewheel)

        progress_frame = tk.Frame(row, bg=base_bg, height=self.row_content_height)
        progress_frame.grid(row=0, column=2, sticky="nsew", padx=(0, 12), pady=4)
        progress_frame.columnconfigure(0, weight=1)
        progress_label = tk.Label(
            progress_frame,
            text=progress_text(entry),
            anchor="e",
            bg=base_bg,
            fg=COLOR_TEXT,
            font=self.small_font,
        )
        progress_label.grid(row=0, column=0, sticky="ew")
        progress_label.bind("<Button-1>", lambda _event, item_id=entry_id: self._select(item_id))
        progress_label.bind("<Double-1>", lambda _event, item_id=entry_id: self._on_edit(item_id))
        progress_label.bind("<MouseWheel>", self._on_rows_mousewheel)
        progress_canvas = tk.Canvas(
            progress_frame,
            width=1,
            height=7,
            bg=base_bg,
            highlightthickness=0,
        )
        progress_canvas.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        progress_canvas.bind(
            "<Configure>",
            lambda _event, item_id=entry_id: self._draw_progress_indicator(item_id),
        )
        progress_canvas.bind(
            "<Button-1>", lambda _event, item_id=entry_id: self._select(item_id)
        )
        progress_canvas.bind("<MouseWheel>", self._on_rows_mousewheel)

        delay_label = tk.Label(
            row,
            anchor="w",
            bg=base_bg,
            fg=COLOR_TEXT_MUTED,
            font=self.small_font,
        )
        delay_label.grid(row=0, column=3, sticky="ew", padx=(0, 8), pady=4)
        delay_label.bind("<Button-1>", lambda _event, item_id=entry_id: self._select(item_id))
        delay_label.bind("<MouseWheel>", self._on_rows_mousewheel)

        complete_button = ttk.Button(
            row,
            text=f"✓ {TEXT_COMPLETE}",
            width=COMPLETE_BUTTON_WIDTH,
            style="Success.TButton",
            cursor="hand2",
            command=lambda item_id=entry_id: self._on_complete(item_id),
        )
        complete_button.grid(row=0, column=4, sticky="w", padx=(0, 8), pady=4)
        complete_button.bind("<MouseWheel>", self._on_rows_mousewheel)

        tk.Frame(row, width=self.splitter_width, bg=COLOR_BORDER).grid(
            row=0, column=5, sticky="ns"
        )

        gantt_canvas = tk.Canvas(
            row,
            height=self.row_content_height,
            background=base_bg,
            highlightthickness=0,
        )
        gantt_canvas.grid(row=0, column=6, sticky="ew", padx=(0, 4), pady=4)
        gantt_canvas.bind("<Button-1>", lambda _event, item_id=entry_id: self._select(item_id))
        gantt_canvas.bind("<Configure>", lambda _event, item_id=entry_id: self._redraw_gantt_for(item_id))
        gantt_canvas.bind("<MouseWheel>", self._on_rows_mousewheel)

        self.row_widgets.append(
            RowWidgets(
                entry_id,
                row,
                selection_bar,
                vis_label,
                task_frame,
                tree_indicator,
                task_label,
                progress_frame,
                progress_label,
                progress_canvas,
                delay_label,
                complete_button,
                gantt_canvas,
                base_bg,
            )
        )
        self.root.after_idle(lambda item_id=entry_id: self._draw_progress_indicator(item_id))

    def _draw_progress_indicator(self, entry_id: str) -> None:
        widgets = next((item for item in self.row_widgets if item.entry_id == entry_id), None)
        location = self._find(entry_id)
        if widgets is None or location is None:
            return
        canvas = widgets.progress_canvas
        canvas.delete("all")
        width = canvas.winfo_width()
        if width <= 2:
            return
        ratio = progress_ratio(location.entry)
        create_rounded_rectangle(
            canvas,
            0,
            1,
            width,
            6,
            3,
            fill=COLOR_BORDER_SOFT,
            outline="",
        )
        fill = COLOR_PARENT_COMPLETE if location.entry["kind"] == "parent" else COLOR_CHILD_COMPLETE
        if ratio > 0:
            create_rounded_rectangle(
                canvas,
                0,
                1,
                width * ratio,
                6,
                3,
                fill=fill,
                outline="",
            )

    # ----- selection -----
    def _select(self, entry_id: str) -> None:
        if self._find(entry_id) is None:
            return
        self.selected_id = entry_id
        self._refresh_selection()

    def _refresh_selection(self) -> None:
        for widgets in self.row_widgets:
            is_selected = widgets.entry_id == self.selected_id
            bg = COLOR_PRIMARY_SOFT if is_selected else widgets.base_bg
            location = self._find(widgets.entry_id)
            visibility_bg = bg
            if not is_selected and location is not None:
                visibility_text = self._visibility_text(location.entry, location.parent)
                if visibility_text == VISIBLE_TEXT:
                    visibility_bg = COLOR_SUCCESS_SOFT
                elif visibility_text == PARENT_HIDDEN_TEXT:
                    visibility_bg = COLOR_WARNING_SOFT
                else:
                    visibility_bg = COLOR_HEADER
            widgets.container.configure(bg=bg)
            widgets.selection_bar.configure(bg=COLOR_PRIMARY if is_selected else bg)
            widgets.visibility_label.configure(bg=visibility_bg)
            widgets.task_frame.configure(bg=bg)
            widgets.tree_indicator.configure(bg=bg)
            widgets.task_label.configure(bg=bg)
            widgets.progress_frame.configure(bg=bg)
            widgets.progress_label.configure(bg=bg)
            widgets.progress_canvas.configure(bg=bg)
            widgets.delay_label.configure(bg=bg)
            widgets.gantt_canvas.configure(
                bg=COLOR_SELECTED_GANTT if is_selected else widgets.base_bg
            )
            self._draw_progress_indicator(widgets.entry_id)
            self._redraw_gantt_for(widgets.entry_id)

    # ----- button actions -----
    def _on_add_parent(self) -> None:
        self._open_entry_dialog(kind="parent")

    def _on_add_child(self) -> None:
        location = self._find(self.selected_id)
        if location is None:
            messagebox.showwarning(WARNING_SELECT_PARENT_TITLE, WARNING_SELECT_PARENT_MESSAGE)
            return
        self._open_entry_dialog(kind="child", parent_id=location.parent["id"])

    def _on_edit(self, entry_id: str) -> None:
        location = self._find(entry_id)
        if location is None:
            return
        self._open_entry_dialog(
            kind=location.entry["kind"],
            parent_id=location.entry.get("parent_id"),
            entry_id=entry_id,
        )

    def _on_delete(self) -> None:
        location = self._find(self.selected_id)
        if location is None:
            return
        entry = location.entry
        if entry["kind"] == "parent":
            message = CONFIRM_DELETE_PARENT_MESSAGE.format(
                task=entry["task"], count=len(entry.get("children", []))
            )
        else:
            message = CONFIRM_DELETE_MESSAGE.format(task=entry["task"])
        if not messagebox.askyesno(CONFIRM_DELETE_TITLE, message):
            return

        snapshot = self._snapshot_schedule()
        previous_selection = self.selected_id
        displayed_ids = [item["id"] for item, _parent in self._display_items()]
        old_position = displayed_ids.index(entry["id"]) if entry["id"] in displayed_ids else 0
        remove_entry(self.schedule, entry["id"])
        remaining_ids = [item["id"] for item, _parent in self._display_items()]
        self.selected_id = remaining_ids[min(old_position, len(remaining_ids) - 1)] if remaining_ids else None
        if not self._save_or_restore(snapshot):
            self.selected_id = previous_selection
        self._rebuild_rows()

    def _on_up(self) -> None:
        self._move_selected(-1)

    def _on_down(self) -> None:
        self._move_selected(1)

    def _move_selected(self, direction: int) -> None:
        if not self.selected_id:
            return
        snapshot = self._snapshot_schedule()
        if move_entry(self.schedule, self.selected_id, direction):
            self._save_or_restore(snapshot)
            self._rebuild_rows()

    def _on_complete(self, entry_id: str) -> None:
        location = self._find(entry_id)
        if location is None:
            return
        entry = location.entry
        targets = [entry]
        if entry["kind"] == "parent":
            targets.extend(entry.get("children", []))
            message = CONFIRM_COMPLETE_PARENT_MESSAGE.format(
                task=entry["task"], count=len(entry.get("children", []))
            )
        else:
            message = CONFIRM_COMPLETE_MESSAGE.format(task=entry["task"])
        if not messagebox.askyesno(CONFIRM_COMPLETE_TITLE, message):
            return

        snapshot = self._snapshot_schedule()
        previous_selection = self.selected_id
        remove_entry(self.schedule, entry_id)
        self.selected_id = location.parent["id"] if entry["kind"] == "child" else None
        if self.selected_id and self._find(self.selected_id) is None:
            self.selected_id = None
        if not self._save_or_restore(snapshot):
            self.selected_id = previous_selection
            self._rebuild_rows()
            return
        if not self._append_completion_logs(targets):
            self._restore_schedule(snapshot)
            self.selected_id = previous_selection
            self._save()
            self._rebuild_rows()
            return
        self._rebuild_rows()

    def _on_reload_incomplete_tasks(self) -> None:
        latest_records = self._load_latest_completion_states()
        if latest_records is None:
            return

        existing_ids = {entry["id"] for entry in iter_all_entries(self.schedule)}
        existing_legacy = {
            entry_key(entry["task"], entry["start"], entry["end"])
            for entry in iter_all_entries(self.schedule)
        }
        snapshot = self._snapshot_schedule()
        restored = False
        for key, record in latest_records.items():
            if record[LOG_FIELD_COMPLETED] is True or key in existing_legacy:
                continue
            record_id = str(record.get(LOG_FIELD_ID, "")).strip()
            if record_id and record_id in existing_ids:
                continue

            kind_text = record.get(LOG_FIELD_KIND)
            requested_kind = "child" if kind_text in (TEXT_CHILD, "child") else "parent"
            parent_id = str(record.get(LOG_FIELD_PARENT_ID, "") or "") or None
            parent_location = self._find(parent_id)
            if requested_kind == "child" and (parent_location is None or parent_location.entry["kind"] != "parent"):
                requested_kind = "parent"
                parent_id = None

            entry = new_entry(
                task=record["task"],
                start=record["start"],
                end=record["end"],
                kind=requested_kind,
                parent_id=parent_id,
                visible=bool(record.get(LOG_FIELD_VISIBLE, True)),
                progress_mode=str(record.get(LOG_FIELD_PROGRESS_MODE, "percent")),
                progress_value=record.get(LOG_FIELD_PROGRESS_VALUE, 0),
                progress_total=record.get(LOG_FIELD_PROGRESS_TOTAL, 100),
                entry_id=record_id or None,
            )
            if requested_kind == "child":
                parent_location.entry.setdefault("children", []).append(entry)
            else:
                self.entries.append(entry)
            existing_ids.add(entry["id"])
            existing_legacy.add(entry_key(entry["task"], entry["start"], entry["end"]))
            self._ensure_task_width(entry["task"], entry["kind"])
            restored = True

        if restored:
            self._save_or_restore(snapshot)
            self._rebuild_rows()

    def _toggle_visibility(self, entry_id: str) -> None:
        location = self._find(entry_id)
        if location is None:
            return
        snapshot = self._snapshot_schedule()
        location.entry["visible"] = not location.entry.get("visible", True)
        self._save_or_restore(snapshot)
        self._rebuild_rows()

    def _toggle_collapsed(self, entry_id: str) -> None:
        location = self._find(entry_id)
        if location is None or location.entry["kind"] != "parent":
            return
        snapshot = self._snapshot_schedule()
        previous_selection = self.selected_id
        parent = location.entry
        collapsing = not parent.get("collapsed", False)
        parent["collapsed"] = collapsing
        selected = self._find(self.selected_id)
        if collapsing and selected is not None and selected.entry["kind"] == "child" and selected.parent["id"] == parent["id"]:
            self.selected_id = parent["id"]
        if not self._save_or_restore(snapshot):
            self.selected_id = previous_selection
        self._rebuild_rows()

    def _on_export_excel(self) -> None:
        if not self.entries:
            messagebox.showinfo(INFO_EXCEL_EXPORT_TITLE, "出力できるタスクがありません。")
            return
        output_path = filedialog.asksaveasfilename(
            title=TEXT_EXPORT_EXCEL,
            defaultextension=".xlsx",
            filetypes=(("Excel ブック", "*.xlsx"),),
            initialfile=f"ガントチャート_{self.current_jst_date:%Y%m%d}.xlsx",
        )
        if not output_path:
            return
        try:
            export_to_excel(self.entries, self.current_jst_date, output_path)
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_EXCEL_EXPORT}\n{exc}")
            return
        messagebox.showinfo(INFO_EXCEL_EXPORT_TITLE, INFO_EXCEL_EXPORT.format(path=output_path))

    # ----- dialog -----
    def _open_entry_dialog(
        self,
        kind: str,
        parent_id: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        location = self._find(entry_id)
        is_edit = location is not None
        dialog_title = DIALOG_EDIT_TITLE
        if not is_edit:
            dialog_title = DIALOG_ADD_PARENT_TITLE if kind == "parent" else DIALOG_ADD_CHILD_TITLE

        dlg = tk.Toplevel(self.root)
        dlg.title(dialog_title)
        dlg.configure(bg=COLOR_APP_BG)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.columnconfigure(0, weight=1)

        content = tk.Frame(
            dlg,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SOFT,
        )
        content.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        content.columnconfigure(0, weight=1)

        tk.Label(
            content,
            text=dialog_title,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=self.title_font,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 2))
        tk.Label(
            content,
            text="タスクの期間と進捗を入力してください。",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=self.subtitle_font,
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 18))

        task_var = tk.StringVar()
        start_var = tk.StringVar()
        end_var = tk.StringVar()
        progress_mode_var = tk.StringVar(value="percent")
        progress_value_var = tk.StringVar(value="0")
        progress_total_var = tk.StringVar(value="100")

        if is_edit:
            entry = location.entry
            task_var.set(entry["task"])
            start_var.set(format_date(entry["start"]))
            end_var.set(format_date(entry["end"]))
            progress_mode_var.set(entry.get("progress_mode", "percent"))
            progress_value_var.set(number_text(entry.get("progress_value", 0)))
            progress_total_var.set(number_text(entry.get("progress_total", 100)))
        else:
            today = self.current_jst_date
            start_var.set(format_date(today))
            end_var.set(format_date(today))

        form = tk.Frame(content, bg=COLOR_SURFACE)
        form.grid(row=2, column=0, sticky="ew", padx=24)
        form.columnconfigure(0, weight=1)

        tk.Label(
            form,
            text=LABEL_TASK_NAME,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=self.header_font,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        task_entry = ttk.Entry(
            form,
            textvariable=task_var,
            width=48,
            style="Modern.TEntry",
        )
        task_entry.grid(row=1, column=0, sticky="ew", pady=(0, 16))

        dates_frame = tk.Frame(form, bg=COLOR_SURFACE)
        dates_frame.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        dates_frame.columnconfigure(0, weight=1)
        dates_frame.columnconfigure(1, weight=1)
        tk.Label(
            dates_frame,
            text=LABEL_START_DATE,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=self.header_font,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 6))
        tk.Label(
            dates_frame,
            text=LABEL_END_DATE,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=self.header_font,
            anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))
        start_entry = ttk.Entry(
            dates_frame,
            textvariable=start_var,
            width=20,
            style="Modern.TEntry",
        )
        end_entry = ttk.Entry(
            dates_frame,
            textvariable=end_var,
            width=20,
            style="Modern.TEntry",
        )
        start_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        end_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0))

        tk.Label(
            form,
            text=LABEL_PROGRESS_MODE,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=self.header_font,
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", pady=(0, 6))
        mode_frame = tk.Frame(form, bg=COLOR_SURFACE)
        mode_frame.grid(row=4, column=0, sticky="w", pady=(0, 14))
        ttk.Radiobutton(
            mode_frame,
            text=TEXT_PERCENT_MODE,
            variable=progress_mode_var,
            value="percent",
            style="Modern.TRadiobutton",
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            mode_frame,
            text=TEXT_VALUE_MODE,
            variable=progress_mode_var,
            value="value",
            style="Modern.TRadiobutton",
        ).grid(row=0, column=1, sticky="w", padx=(18, 0))

        progress_frame = tk.Frame(form, bg=COLOR_SURFACE)
        progress_frame.grid(row=5, column=0, sticky="ew", pady=(0, 4))
        progress_frame.columnconfigure(0, weight=1)
        progress_frame.columnconfigure(1, weight=1)
        tk.Label(
            progress_frame,
            text=LABEL_PROGRESS_VALUE,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=self.header_font,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 6))
        tk.Label(
            progress_frame,
            text=LABEL_PROGRESS_TOTAL,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=self.header_font,
            anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))
        progress_value_entry = ttk.Entry(
            progress_frame,
            textvariable=progress_value_var,
            width=20,
            style="Modern.TEntry",
        )
        progress_total_entry = ttk.Entry(
            progress_frame,
            textvariable=progress_total_var,
            width=20,
            style="Modern.TEntry",
        )
        progress_value_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        progress_total_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0))

        def refresh_progress_mode() -> None:
            is_value_mode = progress_mode_var.get() == "value"
            progress_total_entry.configure(state="normal" if is_value_mode else "disabled")
            if not is_value_mode:
                progress_total_var.set("100")

        progress_trace_id = progress_mode_var.trace_add(
            "write", lambda *_args: refresh_progress_mode()
        )
        refresh_progress_mode()

        dialog_closed = False

        def close_dialog() -> None:
            nonlocal dialog_closed
            if dialog_closed:
                return
            dialog_closed = True
            try:
                progress_mode_var.trace_remove("write", progress_trace_id)
            except tk.TclError:
                pass
            if dlg.grab_current() == dlg:
                dlg.grab_release()
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", close_dialog)

        ttk.Separator(content, orient="horizontal").grid(
            row=3, column=0, sticky="ew", padx=24, pady=(20, 14)
        )
        button_box = tk.Frame(content, bg=COLOR_SURFACE)
        button_box.grid(row=4, column=0, sticky="e", padx=24, pady=(0, 22))

        def submit() -> None:
            task_text = task_var.get().strip()
            if not task_text:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_EMPTY_TASK)
                return
            try:
                start_value = parse_date(start_var.get())
                end_value = parse_date(end_var.get())
            except Exception:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_INVALID_DATE)
                return
            if end_value < start_value:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_END_BEFORE_START)
                return
            try:
                progress_value = float(progress_value_var.get().strip())
                progress_total = 100.0 if progress_mode_var.get() == "percent" else float(progress_total_var.get().strip())
            except ValueError:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_INVALID_PROGRESS)
                return
            if not math.isfinite(progress_value) or not math.isfinite(progress_total) or progress_value < 0:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_INVALID_PROGRESS)
                return
            if progress_mode_var.get() == "percent" and progress_value > 100:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_PERCENT_RANGE)
                return
            if progress_mode_var.get() == "value" and (progress_total <= 0 or progress_value > progress_total):
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_VALUE_RANGE)
                return

            clean_value: int | float = int(progress_value) if progress_value.is_integer() else progress_value
            clean_total: int | float = int(progress_total) if progress_total.is_integer() else progress_total
            snapshot = self._snapshot_schedule()
            previous_selection = self.selected_id
            if is_edit:
                current_location = self._find(entry_id)
                if current_location is None:
                    messagebox.showerror(ERROR_INPUT_TITLE, "編集対象が見つかりません。")
                    return
                target = current_location.entry
                target.update(
                    {
                        "task": task_text,
                        "start": start_value,
                        "end": end_value,
                        "progress_mode": progress_mode_var.get(),
                        "progress_value": clean_value,
                        "progress_total": clean_total,
                    }
                )
                self.selected_id = target["id"]
            else:
                target = new_entry(
                    task=task_text,
                    start=start_value,
                    end=end_value,
                    kind=kind,
                    parent_id=parent_id,
                    progress_mode=progress_mode_var.get(),
                    progress_value=clean_value,
                    progress_total=clean_total,
                )
                if kind == "parent":
                    self.entries.append(target)
                else:
                    parent_location = self._find(parent_id)
                    if parent_location is None:
                        messagebox.showerror(ERROR_INPUT_TITLE, WARNING_SELECT_PARENT_MESSAGE)
                        return
                    parent_location.entry.setdefault("children", []).append(target)
                    parent_location.entry["collapsed"] = False
                self.selected_id = target["id"]

            self._ensure_task_width(task_text, kind)
            if not self._save_or_restore(snapshot):
                self.selected_id = previous_selection
                self._rebuild_rows()
                return
            self._rebuild_rows()
            close_dialog()

        ttk.Button(
            button_box,
            text=BUTTON_CANCEL,
            width=10,
            command=close_dialog,
            style="Secondary.TButton",
            cursor="hand2",
        ).grid(row=0, column=0)
        ttk.Button(
            button_box,
            text=BUTTON_OK,
            width=10,
            command=submit,
            style="Primary.TButton",
            cursor="hand2",
        ).grid(
            row=0, column=1, padx=(8, 0)
        )

        task_entry.focus_set()
        dlg.bind("<Return>", lambda _event: submit())
        dlg.bind("<Escape>", lambda _event: close_dialog())

        dlg.update_idletasks()
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + max((self.root.winfo_width() - dlg.winfo_width()) // 2, 0)
        y = self.root.winfo_rooty() + max((self.root.winfo_height() - dlg.winfo_height()) // 2, 0)
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
        min_width = 200
        max_width = max(min_width, self.root.winfo_width() - 650)
        self.task_column_width = int(max(min_width, min(new_width, max_width)))
        self._apply_column_width()
        self._redraw_all_gantt()
        self._redraw_scale()

    def _on_splitter_release(self, _event: tk.Event) -> None:
        self._drag_start_x = None
        self._drag_start_width = None

    # ----- gantt helpers -----
    def _visible_range(self) -> tuple[date | None, date | None]:
        visible_entries = [
            entry
            for entry, parent in self._display_items()
            if self._effective_visible(entry, parent)
        ]
        if not visible_entries:
            return None, None
        return (
            min(entry["start"] for entry in visible_entries),
            max(entry["end"] for entry in visible_entries),
        )

    def _refresh_delay_labels(self) -> None:
        for widgets in self.row_widgets:
            location = self._find(widgets.entry_id)
            if location is None:
                continue
            days = self._delay_days(location.entry)
            is_selected = widgets.entry_id == self.selected_id
            widgets.delay_label.configure(
                text=f"{days}日遅延" if days else "—",
                fg=COLOR_DANGER if days else COLOR_TEXT_MUTED,
                bg=(
                    COLOR_PRIMARY_SOFT
                    if is_selected
                    else COLOR_DANGER_SOFT if days else widgets.base_bg
                ),
                padx=4 if days else 0,
                pady=2 if days else 0,
            )

    def _redraw_all_gantt(self) -> None:
        for widgets in self.row_widgets:
            self._redraw_gantt_for(widgets.entry_id)

    def _redraw_gantt_for(self, entry_id: str) -> None:
        widgets = next((item for item in self.row_widgets if item.entry_id == entry_id), None)
        location = self._find(entry_id)
        if widgets is None or location is None:
            return
        canvas = widgets.gantt_canvas
        canvas.delete("all")

        entry = location.entry
        parent = location.parent
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 4 or height <= 4:
            return

        start_all, end_all = self._visible_range()
        if start_all is None or end_all is None:
            return
        vis_days = max(1, (end_all - start_all).days + 1)
        pad = 4
        usable_w = max(1, width - 2 * pad)

        def x_for(index_value: int | float) -> float:
            return pad + usable_w * (index_value / vis_days)

        if self._effective_visible(entry, parent):
            start_index = max(0, min(vis_days, (entry["start"] - start_all).days))
            span_days = (entry["end"] - entry["start"]).days + 1
            end_index = max(0, min(vis_days, start_index + span_days))
            x0 = x_for(start_index)
            x1 = x_for(end_index)
            if x1 <= x0:
                x1 = min(width - pad, x0 + 1)
            is_parent = entry["kind"] == "parent"
            y0, y1 = (9, height - 9) if is_parent else (12, height - 12)
            remaining_color = COLOR_PARENT_REMAINING if is_parent else COLOR_CHILD_REMAINING
            completed_color = COLOR_PARENT_COMPLETE if is_parent else COLOR_CHILD_COMPLETE
            create_rounded_rectangle(
                canvas,
                x0,
                y0,
                x1,
                y1,
                7,
                fill=remaining_color,
                outline=completed_color,
                width=1,
            )
            progress_x = x0 + (x1 - x0) * progress_ratio(entry)
            if progress_x > x0:
                create_rounded_rectangle(
                    canvas,
                    x0,
                    y0,
                    progress_x,
                    y1,
                    7,
                    fill=completed_color,
                    outline="",
                )
            bar_width = x1 - x0
            if bar_width >= 36:
                label = (
                    f"{span_days}日  •  {progress_text(entry)}"
                    if bar_width >= 90
                    else f"{progress_ratio(entry):.0%}"
                )
                label_color = "white" if progress_ratio(entry) >= 0.55 else COLOR_TEXT
                canvas.create_text(
                    (x0 + x1) / 2,
                    (y0 + y1) / 2,
                    text=label,
                    fill=label_color,
                    font=self.small_font,
                )

        if start_all <= self.current_jst_date <= end_all:
            if self.today_label_screen_x is not None:
                x_today = self.today_label_screen_x - canvas.winfo_rootx()
            else:
                today_index = (self.current_jst_date - start_all).days + 0.5
                x_today = x_for(today_index)
            canvas.create_line(max(0, min(width, x_today)), 0, max(0, min(width, x_today)), height, fill=TODAY_LINE_COLOR, width=2)

    def _redraw_scale(self) -> None:
        if not hasattr(self, "scale_canvas"):
            return
        canvas = self.scale_canvas
        canvas.delete("all")
        self.today_label_screen_x = None

        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 4 or height <= 4:
            canvas.after(40, self._redraw_scale)
            return
        start_all, end_all = self._visible_range()
        if start_all is None or end_all is None:
            return
        vis_days = max(1, (end_all - start_all).days + 1)
        pad = 4
        usable_w = max(1, width - 2 * pad)
        pixels_per_day = usable_w / vis_days

        def x_for(index_value: int | float) -> float:
            return pad + usable_w * (index_value / vis_days)

        y_year = 12
        y_month = height / 2
        y_day = height - 3

        total_years = end_all.year - start_all.year + 1
        pixels_per_year = usable_w / total_years
        year_step = max(1, math.ceil(56 / pixels_per_year))
        current_year = start_all.year
        while current_year <= end_all.year:
            group_end_year = min(end_all.year, current_year + year_step - 1)
            segment_start = max(start_all, date(current_year, 1, 1))
            segment_end = min(end_all, date(group_end_year, 12, 31))
            x0 = x_for((segment_start - start_all).days)
            x1 = x_for((segment_end - start_all).days + 1)
            if x1 - x0 > 40:
                year_label = (
                    str(current_year)
                    if group_end_year == current_year
                    else f"{current_year}–{group_end_year}"
                )
                canvas.create_text(
                    (x0 + x1) / 2,
                    y_year,
                    text=year_label,
                    anchor="n",
                    fill=COLOR_TEXT,
                    font=self.header_font,
                )
            current_year += year_step

        start_month_index = (start_all.year - 1) * 12 + start_all.month - 1
        end_month_index = (end_all.year - 1) * 12 + end_all.month - 1
        total_months = end_month_index - start_month_index + 1
        pixels_per_month = usable_w / total_months
        month_step = max(1, math.ceil(28 / pixels_per_month))
        month_index = start_month_index
        while month_index <= end_month_index:
            month_year, zero_based_month = divmod(month_index, 12)
            current_month = date(month_year + 1, zero_based_month + 1, 1)
            next_month_index = month_index + 1
            if next_month_index > (date.max.year * 12 - 1):
                next_month = None
            else:
                next_year, next_zero_based_month = divmod(next_month_index, 12)
                next_month = date(next_year + 1, next_zero_based_month + 1, 1)
            segment_start = max(start_all, current_month)
            segment_end = (
                end_all
                if next_month is None
                else min(end_all, next_month - timedelta(days=1))
            )
            x0 = x_for((segment_start - start_all).days)
            x1 = x_for((segment_end - start_all).days + 1)
            if month_step == 1 and x1 - x0 > 24:
                canvas.create_text(
                    (x0 + x1) / 2,
                    y_month,
                    text=str(current_month.month),
                    fill=COLOR_TEXT_MUTED,
                    font=self.small_font,
                )
            if pad <= x0 <= width - pad:
                canvas.create_line(x0, 0, x0, height - 1, fill=COLOR_BORDER_SOFT)
            month_index += month_step

        min_spacing = 24
        step = max(1, int((min_spacing / pixels_per_day) + 0.999))

        def draw_day_label(day_value: date) -> None:
            x = x_for((day_value - start_all).days)
            canvas.create_line(x, height - 18, x, height - 1, fill=COLOR_BORDER)
            label = canvas.create_text(
                x,
                y_day,
                text=str(day_value.day),
                anchor="s",
                fill=TODAY_LINE_COLOR if day_value == self.current_jst_date else COLOR_TEXT_MUTED,
                font=self.small_font,
            )
            if day_value == self.current_jst_date:
                bbox = canvas.bbox(label)
                if bbox:
                    self.today_label_screen_x = canvas.winfo_rootx() + ((bbox[0] + bbox[2]) / 2)
                    highlight = canvas.create_rectangle(
                        bbox[0] - 2,
                        bbox[1] - 1,
                        bbox[2] + 2,
                        bbox[3] + 1,
                        fill=TODAY_HIGHLIGHT_BG,
                        outline="",
                    )
                    canvas.tag_lower(highlight, label)

        day_cursor = start_all
        while day_cursor <= end_all:
            draw_day_label(day_cursor)
            if (end_all - day_cursor).days < step:
                break
            day_cursor += timedelta(days=step)

        if start_all <= self.current_jst_date <= end_all:
            cursor_offset = (self.current_jst_date - start_all).days % step
            if cursor_offset != 0:
                draw_day_label(self.current_jst_date)

        x_last = x_for(vis_days)
        canvas.create_line(x_last, height - 18, x_last, height - 1, fill=COLOR_BORDER)
        if end_all < date.max:
            final_day = end_all + timedelta(days=1)
            canvas.create_text(
                x_last,
                y_day,
                text=str(final_day.day),
                anchor="s",
                fill=COLOR_TEXT_MUTED,
                font=self.small_font,
            )
        canvas.create_line(pad, height - 1, width - pad, height - 1, fill=COLOR_BORDER)
        self._redraw_all_gantt()


def main() -> None:
    root = tk.Tk()
    ScheduleApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

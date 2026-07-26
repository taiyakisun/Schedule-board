import copy
import ctypes
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

from excel_export import export_to_excel
from date_widgets import DateInput, DateTimeInput
from schedule_model import (
    SCHEMA_VERSION,
    SCHEDULE_SORT_KEYS,
    SORT_NONE,
    TODO_SORT_KEYS,
    apply_schedule_sort,
    apply_todo_sort,
    capture_group_order,
    child_dates_within_parent,
    clamp_children_to_parent,
    delay_days,
    deserialize_schedule,
    effective_started_date,
    find_entry,
    find_todo,
    iter_all_todos,
    iter_all_entries,
    move_entry,
    reorder_entry,
    move_schedule_group_to_todos,
    move_todo,
    reorder_todo,
    move_todo_group_to_schedule,
    new_entry,
    new_todo_entry,
    progress_ratio,
    progress_text,
    parse_todo_deadline,
    remove_entry,
    remove_todo,
    restore_group_order,
    serialize_schedule,
    started_date_for_progress,
    todo_notification_due,
    todo_deadline_reached,
)


def application_directory() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts: str) -> str:
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, *parts)


DATA_FILE = os.path.join(application_directory(), "schedules.json")
COMPLETE_LOG_FILE = os.path.join(application_directory(), "completed_tasks.jsonl")

TITLE_APP = "Schedule-board"
CONFIRM_EXIT_TITLE = "終了確認"
CONFIRM_EXIT_MESSAGE = "Schedule-boardを終了しますか？"
LABEL_VISIBILITY = "表示"
LABEL_TASK = "タスク"
LABEL_PROGRESS = "進捗度"
LABEL_STARTED = "着手日"
LABEL_DELAY = "遅延日数"
LABEL_DEADLINE = "期限"
LABEL_NOTIFICATION = "通知"
TEXT_ADD_PARENT = "親を追加"
TEXT_ADD_CHILD = "子を追加"
TEXT_DELETE = "削除"
TEXT_UP = "上へ"
TEXT_DOWN = "下へ"
TEXT_COMPLETE = "完了"
TEXT_EXPORT_EXCEL = "Excel出力"
TEXT_RELOAD_INCOMPLETE = "未完了タスクの再読み込み"
TEXT_MOVE_TO_TODO = "TODOへ移動"
TEXT_MOVE_TO_SCHEDULE = "タスクへ移動"
TEXT_SETTINGS = "表示設定"
TEXT_SORT = "ソート"
TEXT_ADD_MENU = "追加"
TEXT_MORE = "その他"
VISIBLE_TEXT = "表示"
HIDDEN_TEXT = "非表示"
PARENT_HIDDEN_TEXT = "親非表示"
TEXT_COLLAPSE = "▼"
TEXT_EXPAND = "▶"
TEXT_PARENT = "親"
TEXT_CHILD = "子"
TEXT_PERCENT_MODE = "0～100%"
TEXT_VALUE_MODE = "指定数値"
ROW_CONTENT_MIN_HEIGHT = 30
ROW_CONTENT_DEFAULT_HEIGHT = 40
DRAG_HANDLE_TEXT = "↕"
DRAG_START_THRESHOLD = 5

SCHEDULE_SORT_OPTIONS = (
    (SORT_NONE, "ソートなし", "なし"),
    ("task_asc", "タスク名：昇順", "タスク名 ↑"),
    ("task_desc", "タスク名：降順", "タスク名 ↓"),
    ("progress_asc", "進捗度：昇順", "進捗度 ↑"),
    ("progress_desc", "進捗度：降順", "進捗度 ↓"),
    ("started_asc", "着手日：昇順", "着手日 ↑"),
    ("started_desc", "着手日：降順", "着手日 ↓"),
    ("delay_asc", "遅延日数：昇順", "遅延日数 ↑"),
    ("delay_desc", "遅延日数：降順", "遅延日数 ↓"),
    ("start_asc", "開始日：昇順", "開始日 ↑"),
    ("start_desc", "開始日：降順", "開始日 ↓"),
)
TODO_SORT_OPTIONS = (
    (SORT_NONE, "ソートなし", "なし"),
    ("task_asc", "タスク名：昇順", "タスク名 ↑"),
    ("task_desc", "タスク名：降順", "タスク名 ↓"),
    ("deadline_asc", "期限：昇順", "期限 ↑"),
    ("deadline_desc", "期限：降順", "期限 ↓"),
)
SCHEDULE_SORT_LABELS = {
    sort_key: short_label
    for sort_key, _menu_label, short_label in SCHEDULE_SORT_OPTIONS
}
TODO_SORT_LABELS = {
    sort_key: short_label for sort_key, _menu_label, short_label in TODO_SORT_OPTIONS
}


def scale_header_row_positions(
    height: int,
    year_line_height: int,
    detail_line_height: int,
) -> tuple[int, int, int]:
    """年・月の上端と日付の下端を、互いに重ならない3段として返す。"""
    top_padding = 1
    bottom_padding = 1
    content_height = year_line_height + (detail_line_height * 2)
    free_height = max(0, height - top_padding - bottom_padding - content_height)
    gap = free_height // 2
    year_top = top_padding
    month_top = year_top + year_line_height + gap
    day_bottom = height - bottom_padding
    return year_top, month_top, day_bottom
VISIBILITY_COLUMN_WIDTH = 82
PROGRESS_COLUMN_MIN_WIDTH = 78
PROGRESS_COLUMN_MAX_WIDTH = 220
PROGRESS_COLUMN_PADDING = 16
STARTED_COLUMN_WIDTH = 62

DIALOG_ADD_PARENT_TITLE = "親スケジュール追加"
DIALOG_ADD_CHILD_TITLE = "子スケジュール追加"
DIALOG_EDIT_TITLE = "スケジュール編集"
LABEL_TASK_NAME = "タスク名"
LABEL_START_DATE = "開始日 (YYYY-MM-DD)"
LABEL_END_DATE = "終了日 (YYYY-MM-DD)"
LABEL_STARTED_DATE = "着手日（未着手は空欄）"
LABEL_STARTED_DATE_DERIVED = "着手日（子タスクの最古着手日から自動算出）"
LABEL_PROGRESS_MODE = "進捗の単位"
LABEL_PROGRESS_VALUE = "現在の進捗"
LABEL_PROGRESS_TOTAL = "分母"
BUTTON_OK = "OK"
BUTTON_CANCEL = "キャンセル"

ERROR_INPUT_TITLE = "入力エラー"
ERROR_CHILD_OUTSIDE_PARENT = "子スケジュールの開始日と終了日は、親スケジュールの期間内で指定してください。"
ERROR_EMPTY_TASK = "タスク名を入力してください。"
ERROR_INVALID_DATE = "日付はYYYY-MM-DD形式で入力してください。"
ERROR_INVALID_DEADLINE = "期限は有効な日付と時刻（時・分）で入力してください。"
ERROR_INVALID_PROGRESS = "進捗は0以上の数値で入力してください。"
ERROR_PERCENT_RANGE = "パーセントの進捗は0～100で入力してください。"
ERROR_VALUE_RANGE = "指定数値の分母は0より大きく、進捗は分母以下で入力してください。"
ERROR_LOAD = "データの読み込みに失敗しました。"
ERROR_SAVE = "データの保存に失敗しました。"
ERROR_SAVE_AFTER_LOAD = "読み込みに失敗したデータを保護するため、保存を中止しました。アプリを終了し、schedules.jsonを確認してください。"
ERROR_COMPLETE_LOG_WRITE = "完了ログの書き込みに失敗しました。"
ERROR_COMPLETE_LOG_READ = "完了ログの読み込みに失敗しました。"
ERROR_EXCEL_EXPORT = "Excelファイルの出力に失敗しました。"
ERROR_COMPLETION_RECOVERY = "中断された完了処理の復旧に失敗しました。アプリを終了し、データファイルを確認してください。"
INFO_EXCEL_EXPORT_TITLE = "Excel出力"
INFO_EXCEL_EXPORT = "Excelファイルを出力しました。\n{path}"
INFO_DATA_RECOVERED_TITLE = "データを復旧しました"
INFO_DATA_RECOVERED = "保存ファイルに問題があったため、直前の正常なデータから復旧しました。"
WARNING_SELECT_PARENT_TITLE = "親の選択が必要です"
WARNING_SELECT_PARENT_MESSAGE = "子を追加する親、またはその親に属する子を選択してください。"
WARNING_SELECT_TODO_PARENT_MESSAGE = "子TODOを追加する親TODO、またはその子を選択してください。"

CONFIRM_DELETE_TITLE = "削除確認"
CONFIRM_DELETE_MESSAGE = "「{task}」を削除しますか？"
CONFIRM_DELETE_PARENT_MESSAGE = "「{task}」と配下の子タスク{count}件をすべて削除しますか？"
CONFIRM_COMPLETE_TITLE = "完了確認"
CONFIRM_COMPLETE_MESSAGE = "「{task}」を完了にしますか？"
CONFIRM_COMPLETE_PARENT_MESSAGE = "「{task}」と配下の子タスク{count}件をすべて完了にしますか？"
CONFIRM_COMPLETE_TODO_MESSAGE = "「{task}」を完了にしますか？"
CONFIRM_COMPLETE_TODO_PARENT_MESSAGE = "「{task}」と配下の子TODO{count}件をすべて完了にしますか？"

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
LOG_FIELD_STARTED = "着手日"
LOG_FIELD_ORIGIN = "記録元"
LOG_FIELD_DEADLINE = "期限"
LOG_ORIGIN_TODO = "TODO"

JST = timezone(timedelta(hours=9))
JST_MONITOR_MS = 30_000
TODO_MONITOR_MS = 60_000
TODO_NOTIFICATION_INTERVAL = timedelta(hours=1)

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


def configure_application_icon(root: tk.Tk) -> None:
    try:
        icon_image = tk.PhotoImage(file=resource_path("assets", "sch_gantt_icon.png"))
        root.iconphoto(False, icon_image)
        root.iconphoto(True, icon_image)
        root._sch_gantt_icon_image = icon_image
    except (OSError, tk.TclError):
        pass

    if os.name == "nt":
        try:
            icon_path = resource_path("assets", "sch_gantt_icon.ico")
            root.iconbitmap(icon_path)
            root.iconbitmap(default=icon_path)
        except (OSError, tk.TclError):
            pass


def today_in_jst() -> date:
    return datetime.now(JST).date()


def parse_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def format_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def current_jst_timestamp() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def show_windows_notification(root: tk.Tk, title: str, message: str) -> bool:
    """Display a Windows notification-area balloon without extra packages."""

    if sys.platform != "win32":
        return False
    try:
        from ctypes import wintypes

        class Guid(ctypes.Structure):
            _fields_ = (
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8),
            )

        class NotifyIconData(ctypes.Structure):
            _fields_ = (
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HANDLE),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uTimeoutOrVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", Guid),
                ("hBalloonIcon", wintypes.HANDLE),
            )

        shell_notify = ctypes.windll.shell32.Shell_NotifyIconW
        shell_notify.restype = wintypes.BOOL
        user32 = ctypes.windll.user32
        user32.SendMessageW.restype = ctypes.c_ssize_t
        hwnd = int(root.winfo_id())
        icon = user32.SendMessageW(hwnd, 0x007F, 0, 0)
        if not icon:
            user32.LoadIconW.restype = wintypes.HANDLE
            icon = user32.LoadIconW(None, ctypes.c_void_p(32516))

        data = NotifyIconData()
        data.cbSize = ctypes.sizeof(NotifyIconData)
        data.hWnd = hwnd
        data.uID = 0x5342
        data.uFlags = 0x00000002 | 0x00000004 | 0x00000010
        data.hIcon = icon
        data.szTip = "Schedule-board"
        data.szInfo = message[:255]
        data.szInfoTitle = title[:63]
        data.dwInfoFlags = 0x00000001
        if not shell_notify(0x00000000, ctypes.byref(data)):
            return False
        data.uTimeoutOrVersion = 4
        shell_notify(0x00000004, ctypes.byref(data))
        root.after(
            15_000,
            lambda icon_data=data: shell_notify(
                0x00000002, ctypes.byref(icon_data)
            ),
        )
    except (AttributeError, OSError, tk.TclError):
        return False
    return True


def entry_key(task: str, start: date, end: date) -> tuple[str, str, str, str]:
    return "legacy", task, format_date(start), format_date(end)


def number_text(value: float | int) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return str(int(numeric))
    return repr(numeric)


def _sync_parent_directory(path: str) -> None:
    if os.name == "nt":
        return
    directory = os.path.dirname(os.path.abspath(path)) or "."
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _write_synced(path: str, payload: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())


def atomic_write_text(
    path: str,
    text: str,
    *,
    keep_backup: bool = True,
    staging_path: str | None = None,
) -> None:
    temp_path = staging_path or f"{path}.tmp"
    backup_path = f"{path}.bak"
    backup_temp_path = f"{backup_path}.tmp"
    payload = text.encode("utf-8")

    _write_synced(temp_path, payload)
    try:
        if keep_backup and os.path.exists(path):
            with open(path, "rb") as source:
                previous_payload = source.read()
            _write_synced(backup_temp_path, previous_payload)
            os.replace(backup_temp_path, backup_path)
        os.replace(temp_path, path)
        _sync_parent_directory(path)
    finally:
        if os.path.exists(backup_temp_path):
            try:
                os.remove(backup_temp_path)
            except OSError:
                pass


def _schedule_text(schedule: dict) -> str:
    return json.dumps(
        serialize_schedule(schedule),
        ensure_ascii=False,
        indent=2,
    ) + "\n"


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
    drag_handle: tk.Label
    visibility_label: tk.Label
    task_frame: tk.Frame
    tree_indicator: tk.Label
    task_label: tk.Label
    progress_frame: tk.Frame
    progress_label: tk.Label
    progress_canvas: tk.Canvas
    started_label: tk.Label
    delay_label: tk.Label
    gantt_canvas: tk.Canvas
    base_bg: str


@dataclass
class TodoRowWidgets:
    entry_id: str
    container: tk.Frame
    selection_bar: tk.Frame
    drag_handle: tk.Label
    tree_indicator: tk.Label
    task_label: tk.Label
    deadline_label: tk.Label
    notify_button: ttk.Button
    base_bg: str


@dataclass
class RowDragState:
    mode: str
    entry_id: str
    start_root_x: int
    start_root_y: int
    active: bool = False
    target_valid: bool = False
    before_id: str | None = None
    placeholder: tk.Frame | None = None


class ScheduleApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(TITLE_APP)
        self.root.configure(bg=COLOR_APP_BG)
        self.root.minsize(1050, 560)
        initial_width = min(1360, max(1050, self.root.winfo_screenwidth() - 120))
        initial_height = min(760, max(560, self.root.winfo_screenheight() - 160))
        self.root.geometry(f"{initial_width}x{initial_height}")

        self.schedule: dict = {
            "version": SCHEMA_VERSION,
            "parents": [],
            "todos": [],
            "settings": {"row_height": ROW_CONTENT_DEFAULT_HEIGHT},
        }
        self.entries: list[dict] = self.schedule["parents"]
        self.todos: list[dict] = self.schedule["todos"]
        self.load_failed = False
        self.row_widgets: list[RowWidgets] = []
        self.todo_row_widgets: list[TodoRowWidgets] = []
        self.selected_id: str | None = None
        self.selected_todo_id: str | None = None
        self.active_mode = "schedule"
        self._row_drag: RowDragState | None = None
        self._after_ids: set[str] = set()

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
        self.row_content_height = ROW_CONTENT_DEFAULT_HEIGHT
        self.task_column_width = 320
        self.progress_column_width = PROGRESS_COLUMN_MIN_WIDTH
        self.delay_column_width = 76
        self.splitter_width = 6
        self._drag_start_x: int | None = None
        self._drag_start_width: int | None = None
        self.current_jst_date = today_in_jst()

        self._build_ui()
        self.root.bind("<Escape>", self._on_row_drag_escape, add="+")
        self.root.bind("<Destroy>", self._on_root_destroy, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_requested)
        self._load()
        self._ensure_schedule_defaults()
        self._refresh_sort_controls()
        self.row_content_height = self._normalized_row_height(
            self.schedule["settings"].get("row_height", ROW_CONTENT_DEFAULT_HEIGHT)
        )
        self._update_initial_task_width()
        self._rebuild_rows()
        self._rebuild_todo_rows()
        self._schedule_after(100, self._redraw_scale)
        self._schedule_after(100, self._redraw_all_gantt)
        self._schedule_after(JST_MONITOR_MS, self._monitor_jst_date)
        self._schedule_after(5_000, self._check_todo_notifications)

    def _normalized_row_height(self, value: object) -> int:
        try:
            requested = int(value)
        except (TypeError, ValueError):
            requested = ROW_CONTENT_DEFAULT_HEIGHT
        font_minimum = max(
            self.task_font.metrics("linespace") + 6,
            self.parent_font.metrics("linespace") + 6,
        )
        return max(ROW_CONTENT_MIN_HEIGHT, font_minimum, min(72, requested))

    def _ensure_schedule_defaults(self) -> None:
        self.schedule.setdefault("todos", [])
        settings = self.schedule.get("settings")
        if not isinstance(settings, dict):
            settings = {}
            self.schedule["settings"] = settings
        settings.setdefault("row_height", ROW_CONTENT_DEFAULT_HEIGHT)
        if settings.get("schedule_sort") not in SCHEDULE_SORT_KEYS:
            settings["schedule_sort"] = SORT_NONE
        if settings.get("todo_sort") not in TODO_SORT_KEYS:
            settings["todo_sort"] = SORT_NONE
        settings.setdefault("schedule_original_order", None)
        settings.setdefault("todo_original_order", None)
        self.entries = self.schedule["parents"]
        self.todos = self.schedule["todos"]
        if (
            settings["schedule_sort"] != SORT_NONE
            and not isinstance(settings["schedule_original_order"], dict)
        ):
            settings["schedule_original_order"] = capture_group_order(self.entries)
        if (
            settings["todo_sort"] != SORT_NONE
            and not isinstance(settings["todo_original_order"], dict)
        ):
            settings["todo_original_order"] = capture_group_order(self.todos)

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
            "Primary.TMenubutton",
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
            "Primary.TMenubutton",
            background=[("pressed", COLOR_PRIMARY_HOVER), ("active", COLOR_PRIMARY_HOVER)],
            bordercolor=[("focus", COLOR_TEXT), ("pressed", COLOR_PRIMARY_HOVER)],
        )
        self.style.configure(
            "Secondary.TMenubutton",
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
            "Secondary.TMenubutton",
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

    def _schedule_after(self, delay_ms: int, callback) -> str:
        after_id = ""

        def run_callback() -> None:
            self._after_ids.discard(after_id)
            callback()

        after_id = self.root.after(delay_ms, run_callback)
        self._after_ids.add(after_id)
        return after_id

    def _schedule_after_idle(self, callback) -> str:
        after_id = ""

        def run_callback() -> None:
            self._after_ids.discard(after_id)
            callback()

        after_id = self.root.after_idle(run_callback)
        self._after_ids.add(after_id)
        return after_id

    def _on_root_destroy(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        for after_id in tuple(self._after_ids):
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        self._after_ids.clear()

    def _on_close_requested(self) -> None:
        if messagebox.askyesno(
            CONFIRM_EXIT_TITLE,
            CONFIRM_EXIT_MESSAGE,
            parent=self.root,
        ):
            self.root.destroy()

    def _monitor_jst_date(self) -> None:
        latest = today_in_jst()
        if latest != self.current_jst_date:
            self.current_jst_date = latest
            if hasattr(self, "today_label"):
                self.today_label.configure(text=latest.strftime("%Y年%m月%d日"))
            self._refresh_delay_labels()
            self._rebuild_todo_rows()
            self._redraw_scale()
            self._redraw_all_gantt()
        self._schedule_after(JST_MONITOR_MS, self._monitor_jst_date)

    def _check_todo_notifications(self) -> None:
        now = datetime.now(JST)
        due_todos = [
            todo
            for todo in iter_all_todos(self.schedule)
            if todo_notification_due(todo, now, TODO_NOTIFICATION_INTERVAL)
        ]
        if due_todos:
            preview = " / ".join(todo.get("task", "") for todo in due_todos[:3])
            if len(due_todos) > 3:
                preview += f" ほか{len(due_todos) - 3}件"
            if show_windows_notification(
                self.root,
                f"期限が来たTODOが{len(due_todos)}件あります",
                preview,
            ):
                snapshot = self._snapshot_schedule()
                for todo in due_todos:
                    todo["last_notified_at"] = now.isoformat(timespec="seconds")
                self._save_or_restore(snapshot)
        self._refresh_todo_deadline_labels(now)
        self._schedule_after(TODO_MONITOR_MS, self._check_todo_notifications)

    # ----- persistence -----
    def _load(self) -> None:
        if not self._recover_pending_completion():
            self.load_failed = True
            return

        candidates = (DATA_FILE, f"{DATA_FILE}.bak", f"{DATA_FILE}.tmp")
        existing_candidates = [path for path in candidates if os.path.exists(path)]
        if not existing_candidates:
            self.load_failed = False
            return

        errors = []
        for path in existing_candidates:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                schedule = deserialize_schedule(raw)
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")
                continue

            if path != DATA_FILE:
                try:
                    atomic_write_text(
                        DATA_FILE,
                        _schedule_text(schedule),
                        keep_backup=False,
                        staging_path=(
                            f"{DATA_FILE}.recovery.tmp"
                            if path == f"{DATA_FILE}.tmp"
                            else None
                        ),
                    )
                except Exception as exc:
                    errors.append(f"復旧保存: {exc}")
                    messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_LOAD}\n" + "\n".join(errors))
                    self.load_failed = True
                    return
                messagebox.showwarning(INFO_DATA_RECOVERED_TITLE, INFO_DATA_RECOVERED)
            self.schedule = schedule
            self.entries = self.schedule["parents"]
            self.load_failed = False
            return

        messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_LOAD}\n" + "\n".join(errors))
        self.load_failed = True

    def _save(self) -> bool:
        if getattr(self, "load_failed", False):
            messagebox.showerror(ERROR_INPUT_TITLE, ERROR_SAVE_AFTER_LOAD)
            return False
        try:
            atomic_write_text(DATA_FILE, _schedule_text(self.schedule))
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_SAVE}\n{exc}")
            return False
        return True

    def _snapshot_schedule(self) -> dict:
        return copy.deepcopy(self.schedule)

    def _restore_schedule(self, snapshot: dict) -> None:
        self.schedule = snapshot
        self._ensure_schedule_defaults()

    def _save_or_restore(self, snapshot: dict) -> bool:
        if self._save():
            return True
        self._restore_schedule(snapshot)
        return False

    def _completion_record(self, entry: dict) -> dict:
        started = effective_started_date(entry)
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
            LOG_FIELD_STARTED: format_date(started) if started else None,
        }

    def _todo_completion_record(self, todo: dict) -> dict:
        deadline = parse_todo_deadline(todo["deadline"])
        deadline_date = deadline.date()
        source = todo.get("source") if isinstance(todo.get("source"), dict) else {}
        try:
            source_start = parse_date(str(source.get("start", deadline_date.isoformat())))
            source_end = parse_date(str(source.get("end", source_start.isoformat())))
            duration = max(0, (source_end - source_start).days)
        except ValueError:
            duration = 0
        end_ordinal = min(date.max.toordinal(), deadline_date.toordinal() + duration)
        return {
            LOG_FIELD_TASK: todo["task"],
            LOG_FIELD_START: format_date(deadline_date),
            LOG_FIELD_END: format_date(date.fromordinal(end_ordinal)),
            LOG_FIELD_COMPLETED_AT: current_jst_timestamp(),
            LOG_FIELD_COMPLETED: True,
            LOG_FIELD_ID: todo["id"],
            LOG_FIELD_KIND: TEXT_PARENT if todo["kind"] == "parent" else TEXT_CHILD,
            LOG_FIELD_PARENT_ID: todo.get("parent_id"),
            LOG_FIELD_VISIBLE: bool(source.get("visible", True)),
            LOG_FIELD_PROGRESS_MODE: source.get("progress_mode", "percent"),
            LOG_FIELD_PROGRESS_VALUE: source.get("progress_value", 0),
            LOG_FIELD_PROGRESS_TOTAL: source.get("progress_total", 100),
            LOG_FIELD_STARTED: source.get("started"),
            LOG_FIELD_ORIGIN: LOG_ORIGIN_TODO,
            LOG_FIELD_DEADLINE: deadline.isoformat(timespec="minutes"),
        }

    def _completion_journal_path(self) -> str:
        return f"{COMPLETE_LOG_FILE}.pending"

    def _parse_completion_records(self, path: str) -> tuple[list[dict], bool]:
        with open(path, "rb") as fh:
            payload = fh.read()
        truncated_tail = False
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            last_line_start = payload.rfind(b"\n") + 1
            is_torn_tail = (
                not payload.endswith((b"\n", b"\r"))
                and exc.start >= last_line_start
            )
            if not is_torn_tail:
                raise
            text = payload[:last_line_start].decode("utf-8")
            truncated_tail = True
        lines = text.splitlines()
        records = []
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                is_torn_tail = index == len(lines) - 1 and not text.endswith(("\n", "\r"))
                if is_torn_tail:
                    truncated_tail = True
                    break
                raise ValueError(f"{index + 1}行目: JSONの解析に失敗しました。 {exc}") from exc
            if not isinstance(raw, dict):
                raise ValueError(f"{index + 1}行目: JSONオブジェクトを記載してください。")
            records.append(raw)
        return records, truncated_tail

    def _read_completion_records(self) -> tuple[list[dict], bool]:
        candidates = (
            COMPLETE_LOG_FILE,
            f"{COMPLETE_LOG_FILE}.bak",
            f"{COMPLETE_LOG_FILE}.tmp",
        )
        existing_candidates = [path for path in candidates if os.path.exists(path)]
        if not existing_candidates:
            return [], False

        errors = []
        for path in existing_candidates:
            try:
                records, truncated_tail = self._parse_completion_records(path)
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")
                continue
            if path != COMPLETE_LOG_FILE:
                clean_text = "".join(
                    json.dumps(record, ensure_ascii=False) + "\n"
                    for record in records
                )
                atomic_write_text(
                    COMPLETE_LOG_FILE,
                    clean_text,
                    keep_backup=False,
                    staging_path=(
                        f"{COMPLETE_LOG_FILE}.recovery.tmp"
                        if path == f"{COMPLETE_LOG_FILE}.tmp"
                        else None
                    ),
                )
            return records, truncated_tail

        raise ValueError("\n".join(errors))

    def _merge_completion_records(self, records: list[dict]) -> None:
        existing, _truncated_tail = self._read_completion_records()
        known = {
            json.dumps(record, ensure_ascii=False, sort_keys=True)
            for record in existing
        }
        for record in records:
            key = json.dumps(record, ensure_ascii=False, sort_keys=True)
            if key not in known:
                existing.append(record)
                known.add(key)
        text = "".join(
            json.dumps(record, ensure_ascii=False) + "\n"
            for record in existing
        )
        atomic_write_text(COMPLETE_LOG_FILE, text)

    def _finish_completion_transaction(self, journal: dict) -> None:
        if journal.get("version") != 1:
            raise ValueError("完了処理ジャーナルのバージョンが不正です。")
        records = journal.get("records")
        if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
            raise ValueError("完了処理ジャーナルのログが不正です。")
        schedule = deserialize_schedule(journal.get("schedule"))
        self._merge_completion_records(records)
        atomic_write_text(DATA_FILE, _schedule_text(schedule))
        journal_path = self._completion_journal_path()
        if os.path.exists(journal_path):
            os.remove(journal_path)
            _sync_parent_directory(journal_path)

    def _recover_pending_completion(self) -> bool:
        journal_path = self._completion_journal_path()
        if not os.path.exists(journal_path):
            return True
        try:
            with open(journal_path, "r", encoding="utf-8") as fh:
                journal = json.load(fh)
            if not isinstance(journal, dict):
                raise ValueError("完了処理ジャーナルが不正です。")
            self._finish_completion_transaction(journal)
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_COMPLETION_RECOVERY}\n{exc}")
            return False
        return True

    def _append_completion_logs(self, entries: list[dict]) -> bool:
        records = [self._completion_record(entry) for entry in entries]
        try:
            self._merge_completion_records(records)
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_COMPLETE_LOG_WRITE}\n{exc}")
            return False
        return True

    def _load_latest_completion_states(self) -> dict[tuple, dict] | None:
        latest_records: dict[tuple, dict] = {}
        try:
            records, truncated_tail = self._read_completion_records()
            if truncated_tail:
                clean_text = "".join(
                    json.dumps(record, ensure_ascii=False) + "\n"
                    for record in records
                )
                atomic_write_text(COMPLETE_LOG_FILE, clean_text)
            for line_no, raw in enumerate(records, start=1):
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
                    raise ValueError(
                        f"{line_no}行目: 必須キーが不足しています。 {', '.join(missing)}"
                    )
                if raw.get(LOG_FIELD_ORIGIN) == LOG_ORIGIN_TODO:
                    continue

                task = str(raw[LOG_FIELD_TASK])
                try:
                    start = parse_date(str(raw[LOG_FIELD_START]))
                    end = parse_date(str(raw[LOG_FIELD_END]))
                except Exception as exc:
                    raise ValueError(
                        f"{line_no}行目: 開始日または終了日が不正です。"
                    ) from exc

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

    def _started_date(self, entry: dict) -> date | None:
        return effective_started_date(entry)

    def _refresh_sort_controls(self) -> None:
        settings = self.schedule["settings"]
        if hasattr(self, "schedule_sort_button"):
            schedule_key = settings.get("schedule_sort", SORT_NONE)
            self.schedule_sort_button.configure(
                text=f"ソート: {SCHEDULE_SORT_LABELS.get(schedule_key, 'なし')}"
            )
        if hasattr(self, "todo_sort_button"):
            todo_key = settings.get("todo_sort", SORT_NONE)
            self.todo_sort_button.configure(
                text=f"ソート: {TODO_SORT_LABELS.get(todo_key, 'なし')}"
            )

    def _set_sort(self, mode: str, sort_key: str) -> None:
        if mode == "schedule":
            valid_keys = SCHEDULE_SORT_KEYS
            groups = self.entries
            sort_field = "schedule_sort"
            order_field = "schedule_original_order"
        elif mode == "todo":
            valid_keys = TODO_SORT_KEYS
            groups = self.todos
            sort_field = "todo_sort"
            order_field = "todo_original_order"
        else:
            return
        if sort_key not in valid_keys:
            return

        settings = self.schedule["settings"]
        current_sort = settings.get(sort_field, SORT_NONE)
        if sort_key == SORT_NONE and current_sort == SORT_NONE:
            self._refresh_sort_controls()
            return

        snapshot = self._snapshot_schedule()
        if sort_key == SORT_NONE:
            restore_group_order(groups, settings.get(order_field))
            settings[sort_field] = SORT_NONE
            settings[order_field] = None
        else:
            if current_sort == SORT_NONE:
                settings[order_field] = capture_group_order(groups)
            settings[sort_field] = sort_key
            if mode == "schedule":
                apply_schedule_sort(self.schedule, sort_key, self.current_jst_date)
            else:
                apply_todo_sort(self.schedule, sort_key)

        self._save_or_restore(snapshot)
        self._refresh_sort_controls()
        if mode == "schedule":
            self._rebuild_rows()
        else:
            self._rebuild_todo_rows()

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
        topbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 8))
        topbar.columnconfigure(0, weight=1)
        tk.Frame(topbar, width=4, bg=COLOR_PRIMARY).place(x=0, y=0, relheight=1)

        self.tabs_frame = tk.Frame(
            topbar,
            bg=COLOR_HEADER,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SOFT,
        )
        self.tabs_frame.grid(row=0, column=0, sticky="w", padx=20, pady=(10, 0))

        def create_tab(column: int, text: str, mode: str) -> tuple[tk.Frame, tk.Label, tk.Frame]:
            frame = tk.Frame(self.tabs_frame, bg=COLOR_HEADER, cursor="hand2")
            frame.grid(row=0, column=column, sticky="nsew")
            label = tk.Label(
                frame,
                text=text,
                bg=COLOR_HEADER,
                fg=COLOR_TEXT_MUTED,
                font=self.header_font,
                padx=24,
                pady=10,
                cursor="hand2",
                takefocus=True,
            )
            label.grid(row=0, column=0, sticky="nsew")
            indicator = tk.Frame(frame, height=3, bg=COLOR_HEADER)
            indicator.grid(row=1, column=0, sticky="ew")

            def activate(_event: tk.Event | None = None) -> str | None:
                self._switch_mode(mode)
                return "break" if _event is not None else None

            for widget in (frame, label, indicator):
                widget.bind("<Button-1>", activate)
            label.bind("<Return>", activate)
            label.bind("<space>", activate)
            return frame, label, indicator

        (
            self.schedule_tab_frame,
            self.schedule_tab_button,
            self.schedule_tab_indicator,
        ) = create_tab(0, "タスク＆ガント", "schedule")
        (
            self.todo_tab_frame,
            self.todo_tab_button,
            self.todo_tab_indicator,
        ) = create_tab(1, "TODOリスト", "todo")

        overview_frame = tk.Frame(topbar, bg=COLOR_SURFACE)
        overview_frame.grid(row=0, column=1, sticky="e", padx=20, pady=(8, 4))
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
        self.today_label.grid(row=0, column=1, sticky="e", padx=(12, 0))

        ttk.Separator(topbar, orient="horizontal").grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=(8, 0)
        )

        def create_menu_button(
            parent: tk.Frame,
            text: str,
            items: tuple[tuple[str, object | None], ...],
            style: str,
        ) -> ttk.Menubutton:
            menu = tk.Menu(parent, tearoff=False)
            for item_text, command in items:
                if command is None:
                    menu.add_separator()
                else:
                    menu.add_command(label=item_text, command=command)
            button = ttk.Menubutton(
                parent,
                text=text,
                menu=menu,
                style=style,
                cursor="hand2",
            )
            button.menu = menu
            return button

        def create_sort_button(
            parent: tk.Frame,
            mode: str,
            options: tuple[tuple[str, str, str], ...],
        ) -> ttk.Menubutton:
            menu = tk.Menu(parent, tearoff=False)
            for sort_key, menu_label, _short_label in options:
                menu.add_command(
                    label=menu_label,
                    command=lambda selected=sort_key: self._set_sort(mode, selected),
                )
            button = ttk.Menubutton(
                parent,
                text="ソート: なし",
                menu=menu,
                style="Secondary.TMenubutton",
                cursor="hand2",
            )
            button.menu = menu
            return button

        self.schedule_toolbar = tk.Frame(topbar, bg=COLOR_SURFACE)
        self.schedule_toolbar.grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(10, 10)
        )
        self.toolbar_buttons: dict[str, tk.Widget] = {}
        schedule_add = create_menu_button(
            self.schedule_toolbar,
            "＋ 追加",
            (
                ("親タスクを追加", self._on_add_parent),
                ("子タスクを追加", self._on_add_child),
            ),
            "Primary.TMenubutton",
        )
        schedule_move = ttk.Button(
            self.schedule_toolbar,
            text="TODOへ移動",
            command=self._on_move_to_todo,
            style="Secondary.TButton",
            cursor="hand2",
        )
        schedule_delete = ttk.Button(
            self.schedule_toolbar,
            text="削除",
            command=self._on_delete,
            style="Danger.TButton",
            cursor="hand2",
        )
        schedule_up = ttk.Button(
            self.schedule_toolbar,
            text="↑ 上へ",
            command=self._on_up,
            style="Secondary.TButton",
            cursor="hand2",
        )
        schedule_down = ttk.Button(
            self.schedule_toolbar,
            text="↓ 下へ",
            command=self._on_down,
            style="Secondary.TButton",
            cursor="hand2",
        )
        schedule_complete = ttk.Button(
            self.schedule_toolbar,
            text=f"✓ {TEXT_COMPLETE}",
            command=self._on_complete_selected,
            style="Success.TButton",
            cursor="hand2",
        )
        schedule_more = create_menu_button(
            self.schedule_toolbar,
            "その他",
            (
                ("Excel出力", self._on_export_excel),
                ("未完了タスクを再読込", self._on_reload_incomplete_tasks),
                ("", None),
                ("表示設定", self._open_settings_dialog),
            ),
            "Secondary.TMenubutton",
        )
        self.schedule_sort_button = create_sort_button(
            self.schedule_toolbar,
            "schedule",
            SCHEDULE_SORT_OPTIONS,
        )
        schedule_controls = (
            (TEXT_ADD_MENU, schedule_add),
            (TEXT_DELETE, schedule_delete),
            (TEXT_UP, schedule_up),
            (TEXT_DOWN, schedule_down),
            (TEXT_COMPLETE, schedule_complete),
            (TEXT_SORT, self.schedule_sort_button),
            (TEXT_MORE, schedule_more),
        )
        for column, (key, control) in enumerate(schedule_controls):
            control.grid(
                row=0,
                column=column,
                sticky="w",
                padx=(0, 14 if column == 0 else 7),
            )
            self.toolbar_buttons[key] = control
        spacer_column = len(schedule_controls)
        self.schedule_toolbar.columnconfigure(spacer_column, weight=1)
        schedule_move.grid(
            row=0,
            column=spacer_column + 1,
            sticky="e",
            padx=(14, 0),
        )
        self.toolbar_buttons[TEXT_MOVE_TO_TODO] = schedule_move

        self.todo_toolbar = tk.Frame(topbar, bg=COLOR_SURFACE)
        todo_add = create_menu_button(
            self.todo_toolbar,
            "＋ 追加",
            (("親TODOを追加", self._on_add_todo), ("子TODOを追加", self._on_add_child_todo)),
            "Primary.TMenubutton",
        )
        todo_move = ttk.Button(
            self.todo_toolbar,
            text="タスクへ移動",
            command=self._on_move_to_schedule,
            style="Secondary.TButton",
            cursor="hand2",
        )
        todo_delete = ttk.Button(
            self.todo_toolbar,
            text="削除",
            command=self._on_delete_todo,
            style="Danger.TButton",
            cursor="hand2",
        )
        todo_up = ttk.Button(
            self.todo_toolbar,
            text="↑ 上へ",
            command=lambda: self._move_selected_todo(-1),
            style="Secondary.TButton",
            cursor="hand2",
        )
        todo_down = ttk.Button(
            self.todo_toolbar,
            text="↓ 下へ",
            command=lambda: self._move_selected_todo(1),
            style="Secondary.TButton",
            cursor="hand2",
        )
        todo_complete = ttk.Button(
            self.todo_toolbar,
            text=f"✓ {TEXT_COMPLETE}",
            command=self._on_complete_selected_todo,
            style="Success.TButton",
            cursor="hand2",
        )
        todo_settings = ttk.Button(
            self.todo_toolbar,
            text="表示設定",
            command=self._open_settings_dialog,
            style="Secondary.TButton",
            cursor="hand2",
        )
        self.todo_sort_button = create_sort_button(
            self.todo_toolbar,
            "todo",
            TODO_SORT_OPTIONS,
        )
        self.todo_toolbar_buttons: dict[str, tk.Widget] = {}
        todo_controls = (
            (TEXT_ADD_MENU, todo_add),
            (TEXT_DELETE, todo_delete),
            (TEXT_UP, todo_up),
            (TEXT_DOWN, todo_down),
            (TEXT_COMPLETE, todo_complete),
            (TEXT_SORT, self.todo_sort_button),
            (TEXT_SETTINGS, todo_settings),
        )
        for column, (key, control) in enumerate(todo_controls):
            control.grid(
                row=0,
                column=column,
                sticky="w",
                padx=(0, 14 if column == 0 else 7),
            )
            self.todo_toolbar_buttons[key] = control
        spacer_column = len(todo_controls)
        self.todo_toolbar.columnconfigure(spacer_column, weight=1)
        todo_move.grid(
            row=0,
            column=spacer_column + 1,
            sticky="e",
            padx=(14, 0),
        )
        self.todo_toolbar_buttons[TEXT_MOVE_TO_SCHEDULE] = todo_move

        def adjust_toolbar_spacing(
            event: tk.Event,
            controls: tuple[tuple[str, tk.Widget], ...],
        ) -> None:
            compact = event.width < 1100
            first_gap = 6 if compact else 14
            control_gap = 1 if compact else 7
            for column, (_key, control) in enumerate(controls):
                control.grid_configure(
                    padx=(0, first_gap if column == 0 else control_gap)
                )

        self.schedule_toolbar.bind(
            "<Configure>",
            lambda event: adjust_toolbar_spacing(event, schedule_controls),
        )
        self.todo_toolbar.bind(
            "<Configure>",
            lambda event: adjust_toolbar_spacing(event, todo_controls),
        )

        self.schedule_row_menu = tk.Menu(self.root, tearoff=False)
        self.schedule_row_menu.add_command(
            label=TEXT_MOVE_TO_TODO,
            command=self._on_move_to_todo,
        )
        self.todo_row_menu = tk.Menu(self.root, tearoff=False)
        self.todo_row_menu.add_command(
            label=TEXT_MOVE_TO_SCHEDULE,
            command=self._on_move_to_schedule,
        )

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
            (3, LABEL_STARTED, None, (0, 8)),
            (4, LABEL_DELAY, None, (0, 8)),
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
                rowspan=2,
                sticky="nsew",
                padx=padding,
                pady=(10, 6),
            )
            self.header_labels[text] = label
        self.task_header_label = self.header_labels[LABEL_TASK]

        scale_header_height = max(
            50,
            self.header_font.metrics("linespace")
            + (self.small_font.metrics("linespace") * 2)
            + 10,
        )
        self.scale_canvas = tk.Canvas(
            self.header,
            height=scale_header_height,
            highlightthickness=0,
            background=COLOR_HEADER,
        )
        self.scale_canvas.grid(row=0, column=6, rowspan=2, sticky="ew", padx=(0, 4))
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

        self.rows_shell = tk.Frame(
            self.root,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SOFT,
        )
        self.rows_shell.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 10))
        self.rows_shell.columnconfigure(0, weight=1)
        self.rows_shell.rowconfigure(0, weight=1)

        self.rows_canvas = tk.Canvas(
            self.rows_shell,
            highlightthickness=0,
            background=COLOR_SURFACE,
        )
        self.rows_canvas.grid(row=0, column=0, sticky="nsew")
        self.rows_scrollbar = ttk.Scrollbar(
            self.rows_shell,
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

        self._build_todo_view()
        self._switch_mode("schedule")
        self._apply_column_width()

    def _build_todo_view(self) -> None:
        self.todo_header = tk.Frame(
            self.root,
            bg=COLOR_HEADER,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SOFT,
        )
        self.todo_header.grid(row=1, column=0, sticky="ew", padx=16)
        self.todo_header.columnconfigure(0, weight=1)
        self.todo_header.columnconfigure(1, minsize=150)
        self.todo_header.columnconfigure(2, minsize=110)
        for column, text in enumerate((LABEL_TASK, LABEL_DEADLINE, LABEL_NOTIFICATION)):
            tk.Label(
                self.todo_header,
                text=text,
                anchor="w",
                bg=COLOR_HEADER,
                fg=COLOR_TEXT_MUTED,
                font=self.header_font,
            ).grid(row=0, column=column, sticky="ew", padx=(16, 8), pady=10)

        self.todo_rows_shell = tk.Frame(
            self.root,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SOFT,
        )
        self.todo_rows_shell.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 10))
        self.todo_rows_shell.columnconfigure(0, weight=1)
        self.todo_rows_shell.rowconfigure(0, weight=1)
        self.todo_rows_canvas = tk.Canvas(
            self.todo_rows_shell,
            highlightthickness=0,
            background=COLOR_SURFACE,
        )
        self.todo_rows_canvas.grid(row=0, column=0, sticky="nsew")
        self.todo_rows_scrollbar = ttk.Scrollbar(
            self.todo_rows_shell,
            orient="vertical",
            command=self.todo_rows_canvas.yview,
            style="Modern.Vertical.TScrollbar",
        )
        self.todo_rows_scrollbar.grid(row=0, column=1, sticky="ns")
        self.todo_rows_canvas.configure(yscrollcommand=self.todo_rows_scrollbar.set)
        self.todo_rows_container = tk.Frame(self.todo_rows_canvas, bg=COLOR_SURFACE)
        self.todo_rows_window = self.todo_rows_canvas.create_window(
            (0, 0), window=self.todo_rows_container, anchor="nw"
        )
        self.todo_rows_container.columnconfigure(0, weight=1)
        self.todo_rows_container.bind(
            "<Configure>",
            lambda _event: self._update_canvas_scrollregion(self.todo_rows_canvas),
        )
        self.todo_rows_canvas.bind(
            "<Configure>",
            self._on_todo_rows_canvas_configure,
        )
        self.todo_rows_canvas.bind("<MouseWheel>", self._on_todo_mousewheel)
        self.todo_rows_container.bind("<MouseWheel>", self._on_todo_mousewheel)
        self.todo_header.grid_remove()
        self.todo_rows_shell.grid_remove()

    def _switch_mode(self, mode: str) -> None:
        if mode not in ("schedule", "todo"):
            return
        self._cancel_row_drag()
        self.active_mode = mode
        schedule_active = mode == "schedule"
        for is_active, frame, label, indicator in (
            (
                schedule_active,
                self.schedule_tab_frame,
                self.schedule_tab_button,
                self.schedule_tab_indicator,
            ),
            (
                not schedule_active,
                self.todo_tab_frame,
                self.todo_tab_button,
                self.todo_tab_indicator,
            ),
        ):
            background = COLOR_SURFACE if is_active else COLOR_HEADER
            frame.configure(bg=background)
            label.configure(
                bg=background,
                fg=COLOR_PRIMARY if is_active else COLOR_TEXT_MUTED,
            )
            indicator.configure(bg=COLOR_PRIMARY if is_active else background)
        if schedule_active:
            self.todo_toolbar.grid_remove()
            self.todo_header.grid_remove()
            self.todo_rows_shell.grid_remove()
            self.schedule_toolbar.grid()
            self.header.grid()
            self.rows_shell.grid()
        else:
            self.schedule_toolbar.grid_remove()
            self.header.grid_remove()
            self.rows_shell.grid_remove()
            self.todo_toolbar.grid(
                row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(10, 10)
            )
            self.todo_header.grid()
            self.todo_rows_shell.grid()
        self._update_summary_label()

    def _on_todo_mousewheel(self, event: tk.Event) -> str:
        if event.delta:
            if self._canvas_content_fits(self.todo_rows_canvas):
                self.todo_rows_canvas.yview_moveto(0.0)
            else:
                self.todo_rows_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _on_rows_mousewheel(self, event: tk.Event) -> str:
        if event.delta:
            if self._canvas_content_fits(self.rows_canvas):
                self.rows_canvas.yview_moveto(0.0)
            else:
                self.rows_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _bind_row_context_menu(
        self,
        widget: tk.Widget,
        mode: str,
        entry_id: str,
    ) -> None:
        widget.bind(
            "<Button-3>",
            lambda event, item_mode=mode, item_id=entry_id: self._show_row_context_menu(
                item_mode,
                item_id,
                event,
            ),
        )

    def _show_row_context_menu(
        self,
        mode: str,
        entry_id: str,
        event: tk.Event,
    ) -> str:
        if mode == "schedule":
            if self._find(entry_id) is None:
                return "break"
            self._select(entry_id)
            menu = self.schedule_row_menu
        elif mode == "todo":
            if find_todo(self.schedule, entry_id) is None:
                return "break"
            self._select_todo(entry_id)
            menu = self.todo_row_menu
        else:
            return "break"
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    # ----- drag and drop ordering -----
    def _bind_row_drag_handle(
        self,
        handle: tk.Label,
        mode: str,
        entry_id: str,
    ) -> None:
        handle.bind(
            "<ButtonPress-1>",
            lambda event, item_mode=mode, item_id=entry_id: self._on_row_drag_press(
                item_mode, item_id, event
            ),
        )
        handle.bind(
            "<B1-Motion>",
            lambda event, item_mode=mode, item_id=entry_id: self._on_row_drag_motion(
                item_mode, item_id, event
            ),
        )
        handle.bind(
            "<ButtonRelease-1>",
            lambda event, item_mode=mode, item_id=entry_id: self._on_row_drag_release(
                item_mode, item_id, event
            ),
        )
        handle.bind(
            "<MouseWheel>",
            self._on_rows_mousewheel if mode == "schedule" else self._on_todo_mousewheel,
        )

    def _drag_widgets(self, mode: str) -> list[RowWidgets | TodoRowWidgets]:
        return self.row_widgets if mode == "schedule" else self.todo_row_widgets

    def _drag_container(self, mode: str) -> tk.Frame:
        return self.rows_container if mode == "schedule" else self.todo_rows_container

    def _drag_canvas(self, mode: str) -> tk.Canvas:
        return self.rows_canvas if mode == "schedule" else self.todo_rows_canvas

    def _drag_location(self, mode: str, entry_id: str):
        finder = find_entry if mode == "schedule" else find_todo
        return finder(self.schedule, entry_id)

    def _drag_block_widgets(
        self,
        mode: str,
        entry_id: str,
    ) -> list[RowWidgets | TodoRowWidgets]:
        location = self._drag_location(mode, entry_id)
        if location is None:
            return []
        block_ids = [entry_id]
        if location.is_parent and not location.entry.get("collapsed", False):
            block_ids.extend(child["id"] for child in location.entry.get("children", []))
        widget_by_id = {widgets.entry_id: widgets for widgets in self._drag_widgets(mode)}
        return [widget_by_id[item_id] for item_id in block_ids if item_id in widget_by_id]

    def _drag_sibling_ids(self, mode: str, entry_id: str) -> list[str]:
        location = self._drag_location(mode, entry_id)
        if location is None:
            return []
        root_key = "parents" if mode == "schedule" else "todos"
        siblings = (
            self.schedule.get(root_key, [])
            if location.is_parent
            else location.parent.get("children", [])
        )
        return [str(item["id"]) for item in siblings]

    def _drag_allowed_vertical_range(
        self,
        mode: str,
        entry_id: str,
    ) -> tuple[int, int] | None:
        location = self._drag_location(mode, entry_id)
        if location is None:
            return None
        container = self._drag_container(mode)
        if location.is_parent:
            return (
                container.winfo_rooty(),
                container.winfo_rooty() + container.winfo_height(),
            )

        parent_block = self._drag_block_widgets(mode, location.parent["id"])
        if not parent_block:
            return None
        top = parent_block[0].container.winfo_rooty() + parent_block[0].container.winfo_height()
        root_key = "parents" if mode == "schedule" else "todos"
        parents = self.schedule.get(root_key, [])
        next_parent = (
            parents[location.parent_index + 1]
            if location.parent_index + 1 < len(parents)
            else None
        )
        if next_parent is not None:
            next_block = self._drag_block_widgets(mode, next_parent["id"])
            bottom = next_block[0].container.winfo_rooty() if next_block else top
        else:
            bottom = container.winfo_rooty() + container.winfo_height()
        return top, bottom

    def _drag_destination(
        self,
        mode: str,
        entry_id: str,
        pointer_root_y: int,
    ) -> tuple[bool, str | None]:
        remaining_ids = [
            item_id
            for item_id in self._drag_sibling_ids(mode, entry_id)
            if item_id != entry_id
        ]
        allowed = self._drag_allowed_vertical_range(mode, entry_id)
        if not remaining_ids or allowed is None:
            return False, None
        if not allowed[0] <= pointer_root_y <= allowed[1]:
            return False, None

        for item_id in remaining_ids:
            block = self._drag_block_widgets(mode, item_id)
            if not block:
                continue
            top = block[0].container.winfo_rooty()
            bottom_widget = block[-1].container
            bottom = bottom_widget.winfo_rooty() + bottom_widget.winfo_height()
            if pointer_root_y < (top + bottom) / 2:
                return True, item_id
        return True, None

    def _restore_drag_layout(self, mode: str) -> None:
        state = self._row_drag
        if state is not None and state.placeholder is not None:
            if state.placeholder.winfo_exists():
                state.placeholder.destroy()
            state.placeholder = None
        for row_index, widgets in enumerate(self._drag_widgets(mode)):
            if widgets.container.winfo_exists():
                widgets.container.grid(row=row_index, column=0, sticky="ew")

    def _show_drag_preview(
        self,
        mode: str,
        entry_id: str,
        before_id: str | None,
    ) -> None:
        state = self._row_drag
        if state is None:
            return
        self._restore_drag_layout(mode)
        source_block = self._drag_block_widgets(mode, entry_id)
        if not source_block:
            return
        source_frames = [widgets.container for widgets in source_block]
        remaining_frames = [
            widgets.container
            for widgets in self._drag_widgets(mode)
            if widgets.container not in source_frames
        ]
        if before_id is not None:
            target_block = self._drag_block_widgets(mode, before_id)
            if not target_block or target_block[0].container not in remaining_frames:
                return
            insert_index = remaining_frames.index(target_block[0].container)
        else:
            remaining_siblings = [
                item_id
                for item_id in self._drag_sibling_ids(mode, entry_id)
                if item_id != entry_id
            ]
            if not remaining_siblings:
                return
            target_block = self._drag_block_widgets(mode, remaining_siblings[-1])
            if not target_block or target_block[-1].container not in remaining_frames:
                return
            insert_index = remaining_frames.index(target_block[-1].container) + 1

        for frame in source_frames:
            frame.grid_remove()
        for index, frame in enumerate(remaining_frames):
            frame.grid(row=index if index < insert_index else index + 1, column=0, sticky="ew")

        preview_height = max(
            self.row_content_height,
            sum(max(self.row_content_height, frame.winfo_height()) for frame in source_frames),
        )
        placeholder = tk.Frame(
            self._drag_container(mode),
            height=preview_height,
            bg=COLOR_PRIMARY_SOFT,
            highlightthickness=1,
            highlightbackground=COLOR_PRIMARY,
        )
        placeholder.grid(row=insert_index, column=0, sticky="ew")
        placeholder.grid_propagate(False)
        placeholder.columnconfigure(0, weight=1)
        placeholder.rowconfigure(0, weight=1)
        tk.Label(
            placeholder,
            text="ここに移動",
            bg=COLOR_PRIMARY_SOFT,
            fg=COLOR_PRIMARY,
            font=self.small_font,
        ).grid(row=0, column=0)
        state.placeholder = placeholder
        state.target_valid = True
        state.before_id = before_id
        self.root.update_idletasks()

    def _cancel_row_drag(self) -> None:
        state = self._row_drag
        if state is None:
            return
        self._restore_drag_layout(state.mode)
        self._row_drag = None
        self.root.configure(cursor="")

    def _on_row_drag_escape(self, _event: tk.Event | None = None) -> str | None:
        if self._row_drag is None:
            return None
        self._cancel_row_drag()
        return "break"

    def _on_row_drag_press(
        self,
        mode: str,
        entry_id: str,
        event: tk.Event,
    ) -> str:
        self._cancel_row_drag()
        if self._drag_location(mode, entry_id) is None:
            return "break"
        if mode == "schedule":
            self._select(entry_id)
        else:
            self._select_todo(entry_id)
        self._row_drag = RowDragState(
            mode,
            entry_id,
            event.x_root,
            event.y_root,
        )
        return "break"

    def _auto_scroll_row_drag(self, mode: str, pointer_root_y: int) -> None:
        canvas = self._drag_canvas(mode)
        scroll_region = canvas.bbox("all")
        if scroll_region is None:
            return
        content_height = scroll_region[3] - scroll_region[1]
        if content_height <= canvas.winfo_height():
            canvas.yview_moveto(0.0)
            return
        top = canvas.winfo_rooty()
        bottom = top + canvas.winfo_height()
        first, last = canvas.yview()
        if pointer_root_y < top + 28 and first > 0.0:
            canvas.yview_scroll(-1, "units")
        elif pointer_root_y > bottom - 28 and last < 1.0:
            canvas.yview_scroll(1, "units")

    def _on_row_drag_motion(
        self,
        mode: str,
        entry_id: str,
        event: tk.Event,
    ) -> str:
        state = self._row_drag
        if state is None or state.mode != mode or state.entry_id != entry_id:
            return "break"
        distance = max(
            abs(event.x_root - state.start_root_x),
            abs(event.y_root - state.start_root_y),
        )
        if not state.active and distance < DRAG_START_THRESHOLD:
            return "break"
        state.active = True
        self.root.configure(cursor="fleur")
        self._auto_scroll_row_drag(mode, event.y_root)
        self.root.update_idletasks()

        if state.placeholder is not None and state.placeholder.winfo_exists():
            preview_top = state.placeholder.winfo_rooty()
            preview_bottom = preview_top + state.placeholder.winfo_height()
            if preview_top <= event.y_root <= preview_bottom:
                return "break"

        valid, before_id = self._drag_destination(mode, entry_id, event.y_root)
        if not valid:
            self._restore_drag_layout(mode)
            state.target_valid = False
            state.before_id = None
            return "break"
        if state.target_valid and state.before_id == before_id and state.placeholder is not None:
            return "break"
        self._show_drag_preview(mode, entry_id, before_id)
        return "break"

    def _commit_row_reorder(
        self,
        mode: str,
        entry_id: str,
        before_id: str | None,
    ) -> bool:
        snapshot = self._snapshot_schedule()
        reorder = reorder_entry if mode == "schedule" else reorder_todo
        if not reorder(self.schedule, entry_id, before_id):
            return False
        saved = self._save_or_restore(snapshot)
        if mode == "schedule":
            self._rebuild_rows()
        else:
            self._rebuild_todo_rows()
        return saved

    def _on_row_drag_release(
        self,
        mode: str,
        entry_id: str,
        _event: tk.Event,
    ) -> str:
        state = self._row_drag
        if state is None or state.mode != mode or state.entry_id != entry_id:
            return "break"
        should_commit = state.active and state.target_valid
        before_id = state.before_id
        self._restore_drag_layout(mode)
        self._row_drag = None
        self.root.configure(cursor="")
        if should_commit:
            self._commit_row_reorder(mode, entry_id, before_id)
        return "break"

    def _on_rows_container_configure(self, _event: tk.Event) -> None:
        self._update_canvas_scrollregion(self.rows_canvas)
        self._redraw_all_gantt()

    def _on_rows_canvas_configure(self, event: tk.Event) -> None:
        self.rows_canvas.itemconfigure(self.rows_window, width=event.width)
        self._update_canvas_scrollregion(self.rows_canvas)
        self._redraw_all_gantt()

    def _on_todo_rows_canvas_configure(self, event: tk.Event) -> None:
        self.todo_rows_canvas.itemconfigure(self.todo_rows_window, width=event.width)
        self._update_canvas_scrollregion(self.todo_rows_canvas)

    @staticmethod
    def _canvas_content_fits(canvas: tk.Canvas) -> bool:
        bounds = canvas.bbox("all")
        if bounds is None:
            return True
        return bounds[3] - bounds[1] <= canvas.winfo_height()

    def _update_canvas_scrollregion(self, canvas: tk.Canvas) -> None:
        bounds = canvas.bbox("all")
        canvas.configure(scrollregion=bounds or (0, 0, 0, 0))
        if self._canvas_content_fits(canvas):
            canvas.yview_moveto(0.0)

    def _apply_column_width(self) -> None:
        self.header.columnconfigure(0, minsize=VISIBILITY_COLUMN_WIDTH)
        self.header.columnconfigure(1, minsize=self.task_column_width + 8)
        self.header.columnconfigure(2, minsize=self.progress_column_width)
        self.header.columnconfigure(3, minsize=STARTED_COLUMN_WIDTH)
        self.header.columnconfigure(4, minsize=self.delay_column_width)
        for widgets in self.row_widgets:
            row = widgets.container
            row.columnconfigure(0, minsize=VISIBILITY_COLUMN_WIDTH)
            row.columnconfigure(1, minsize=self.task_column_width)
            row.columnconfigure(2, minsize=self.progress_column_width)
            row.columnconfigure(3, minsize=STARTED_COLUMN_WIDTH)
            row.columnconfigure(4, minsize=self.delay_column_width)
            widgets.task_frame.configure(width=self.task_column_width, height=self.row_content_height)
            widgets.task_frame.grid_propagate(False)

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
        if self._row_drag is not None and self._row_drag.mode == "schedule":
            self._cancel_row_drag()
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
        self._schedule_after_idle(
            lambda: self._update_canvas_scrollregion(self.rows_canvas)
        )

    def _update_summary_label(self) -> None:
        if not hasattr(self, "summary_label"):
            return
        if getattr(self, "active_mode", "schedule") == "todo":
            todo_count = len(list(iter_all_todos(self.schedule)))
            now = datetime.now(JST)
            due_count = sum(
                1
                for todo in iter_all_todos(self.schedule)
                if todo_deadline_reached(todo, now)
            )
            self.summary_label.configure(
                text=f"{todo_count}件のTODO  ·  期限到来 {due_count}件"
            )
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

    def _display_todo_items(self) -> list[tuple[dict, dict]]:
        rows: list[tuple[dict, dict]] = []
        for parent in self.schedule.get("todos", []):
            rows.append((parent, parent))
            if not parent.get("collapsed", False):
                rows.extend((child, parent) for child in parent.get("children", []))
        return rows

    def _clear_todo_rows(self) -> None:
        if not hasattr(self, "todo_rows_container"):
            return
        if self._row_drag is not None and self._row_drag.mode == "todo":
            self._cancel_row_drag()
        for child in self.todo_rows_container.winfo_children():
            child.destroy()
        self.todo_row_widgets.clear()

    def _rebuild_todo_rows(self) -> None:
        if not hasattr(self, "todo_rows_container"):
            return
        self._clear_todo_rows()
        items = self._display_todo_items()
        for row_index, (todo, parent) in enumerate(items):
            self._add_todo_row(row_index, todo, parent)
        if not items:
            empty = tk.Label(
                self.todo_rows_container,
                text="TODOはありません。「TODO追加」またはタスク画面の「TODOへ移動」から追加できます。",
                bg=COLOR_SURFACE,
                fg=COLOR_TEXT_MUTED,
                font=self.subtitle_font,
                pady=60,
            )
            empty.grid(row=0, column=0, sticky="ew")
        self._refresh_todo_selection()
        self._update_summary_label()
        self._schedule_after_idle(
            lambda: self._update_canvas_scrollregion(self.todo_rows_canvas)
        )

    def _add_todo_row(self, row_index: int, todo: dict, parent: dict) -> None:
        entry_id = todo["id"]
        is_child = todo.get("kind") == "child"
        base_bg = COLOR_SURFACE_ALT if row_index % 2 else COLOR_SURFACE
        row = tk.Frame(self.todo_rows_container, bg=base_bg, height=self.row_content_height)
        row.grid(row=row_index, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, minsize=150)
        row.columnconfigure(2, minsize=110)
        row.grid_propagate(False)
        row.bind("<Button-1>", lambda _event, item_id=entry_id: self._select_todo(item_id))
        row.bind("<MouseWheel>", self._on_todo_mousewheel)
        selection_bar = tk.Frame(row, width=4, bg=base_bg)
        selection_bar.place(x=0, y=0, relheight=1)

        task_frame = tk.Frame(row, bg=base_bg)
        task_frame.grid(row=0, column=0, sticky="nsew", padx=(12, 8), pady=2)
        task_frame.columnconfigure(2, weight=1)
        drag_handle = tk.Label(
            task_frame,
            text=DRAG_HANDLE_TEXT,
            width=2,
            anchor="center",
            bg=base_bg,
            fg=COLOR_TEXT_MUTED,
            font=self.header_font,
            cursor="fleur",
        )
        drag_handle.grid(row=0, column=0, padx=(0, 2))
        self._bind_row_drag_handle(drag_handle, "todo", entry_id)
        if is_child:
            children = parent.get("children", [])
            indicator_text = "└─" if children and children[-1]["id"] == entry_id else "├─"
        else:
            indicator_text = (
                TEXT_EXPAND if todo.get("collapsed", False) else TEXT_COLLAPSE
            ) if todo.get("children") else "•"
        indicator = tk.Label(
            task_frame,
            text=indicator_text,
            width=3,
            anchor="center",
            bg=base_bg,
            fg=COLOR_PRIMARY if todo.get("children") else COLOR_BORDER,
            font=self.header_font,
            cursor="hand2" if todo.get("children") else "arrow",
        )
        indicator.grid(row=0, column=1, padx=(18 if is_child else 0, 4))
        if todo.get("children"):
            indicator.bind(
                "<Button-1>",
                lambda _event, item_id=entry_id: self._toggle_todo_collapsed(item_id),
            )
        task_label = tk.Label(
            task_frame,
            text=todo.get("task", ""),
            anchor="w",
            bg=base_bg,
            fg=COLOR_TEXT,
            font=self.task_font if is_child else self.parent_font,
        )
        task_label.grid(row=0, column=2, sticky="nsew")
        task_label.bind("<Button-1>", lambda _event, item_id=entry_id: self._select_todo(item_id))
        task_label.bind("<Double-1>", lambda _event, item_id=entry_id: self._on_edit_todo(item_id))

        deadline = todo.get("deadline")
        deadline_reached = todo_deadline_reached(todo, datetime.now(JST))
        deadline_label = tk.Label(
            row,
            text=deadline.strftime("%Y-%m-%d %H:%M") if isinstance(deadline, datetime) else "",
            anchor="w",
            bg=base_bg,
            fg=COLOR_DANGER if deadline_reached else COLOR_TEXT,
            font=self.small_font,
        )
        deadline_label.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        deadline_label.bind("<Button-1>", lambda _event, item_id=entry_id: self._select_todo(item_id))
        deadline_label.bind("<Double-1>", lambda _event, item_id=entry_id: self._on_edit_todo(item_id))
        notify_button = ttk.Button(
            row,
            text="ON" if todo.get("notify", False) else "OFF",
            width=7,
            style="Success.TButton" if todo.get("notify", False) else "Secondary.TButton",
            command=lambda item_id=entry_id: self._toggle_todo_notification(item_id),
        )
        notify_button.grid(row=0, column=2, sticky="w", padx=(8, 12), pady=2)
        for widget in (
            row,
            selection_bar,
            task_frame,
            drag_handle,
            indicator,
            task_label,
            deadline_label,
            notify_button,
        ):
            self._bind_row_context_menu(widget, "todo", entry_id)
        self.todo_row_widgets.append(
            TodoRowWidgets(
                entry_id,
                row,
                selection_bar,
                drag_handle,
                indicator,
                task_label,
                deadline_label,
                notify_button,
                base_bg,
            )
        )

    def _select_todo(self, entry_id: str) -> None:
        if find_todo(self.schedule, entry_id) is None:
            return
        self.selected_todo_id = entry_id
        self._refresh_todo_selection()

    def _refresh_todo_deadline_labels(self, now: datetime | None = None) -> None:
        current = now or datetime.now(JST)
        for widgets in self.todo_row_widgets:
            location = find_todo(self.schedule, widgets.entry_id)
            if location is None:
                continue
            deadline = parse_todo_deadline(location.entry["deadline"])
            widgets.deadline_label.configure(
                text=deadline.strftime("%Y-%m-%d %H:%M"),
                fg=(
                    COLOR_DANGER
                    if todo_deadline_reached(location.entry, current)
                    else COLOR_TEXT
                ),
            )
        self._update_summary_label()

    def _refresh_todo_selection(self) -> None:
        for widgets in self.todo_row_widgets:
            selected = widgets.entry_id == self.selected_todo_id
            bg = COLOR_PRIMARY_SOFT if selected else widgets.base_bg
            widgets.container.configure(bg=bg)
            widgets.selection_bar.configure(bg=COLOR_PRIMARY if selected else bg)
            widgets.drag_handle.configure(bg=bg)
            widgets.tree_indicator.configure(bg=bg)
            widgets.task_label.configure(bg=bg)
            widgets.deadline_label.configure(bg=bg)

    def _toggle_todo_collapsed(self, entry_id: str) -> None:
        location = find_todo(self.schedule, entry_id)
        if location is None or not location.is_parent:
            return
        snapshot = self._snapshot_schedule()
        location.entry["collapsed"] = not location.entry.get("collapsed", False)
        self._save_or_restore(snapshot)
        self._rebuild_todo_rows()

    def _toggle_todo_notification(self, entry_id: str) -> None:
        location = find_todo(self.schedule, entry_id)
        if location is None:
            return
        snapshot = self._snapshot_schedule()
        location.entry["notify"] = not location.entry.get("notify", False)
        location.entry["last_notified_at"] = None
        self._save_or_restore(snapshot)
        self._rebuild_todo_rows()

    def _add_row(self, row_index: int, entry: dict, parent: dict) -> None:
        entry_id = entry["id"]
        is_child = entry["kind"] == "child"
        base_bg = COLOR_SURFACE_ALT if row_index % 2 else COLOR_SURFACE
        row = tk.Frame(
            self.rows_container,
            bg=base_bg,
            height=self.row_content_height,
            highlightthickness=0,
        )
        row.grid(row=row_index, column=0, sticky="ew")
        row.grid_propagate(False)
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
        vis_label.grid(row=0, column=0, sticky="w", padx=(12, 8))
        vis_label.bind("<Button-1>", lambda _event, item_id=entry_id: self._toggle_visibility(item_id))
        vis_label.bind("<MouseWheel>", self._on_rows_mousewheel)

        task_frame = tk.Frame(row, height=self.row_content_height, bg=base_bg)
        task_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        task_frame.columnconfigure(2, weight=1)
        task_frame.grid_propagate(False)
        task_frame.bind("<Button-1>", lambda _event, item_id=entry_id: self._select(item_id))
        task_frame.bind("<MouseWheel>", self._on_rows_mousewheel)

        drag_handle = tk.Label(
            task_frame,
            text=DRAG_HANDLE_TEXT,
            width=2,
            anchor="center",
            bg=base_bg,
            fg=COLOR_TEXT_MUTED,
            font=self.header_font,
            cursor="fleur",
        )
        drag_handle.grid(row=0, column=0, padx=(2, 2))
        self._bind_row_drag_handle(drag_handle, "schedule", entry_id)

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
            tree_indicator.grid(row=0, column=1, sticky="w", padx=(22, 6))
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
            tree_indicator.grid(row=0, column=1, sticky="w", padx=(0, 4))
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
        task_label.grid(row=0, column=2, sticky="nsew")
        task_label.bind("<Button-1>", lambda _event, item_id=entry_id: self._select(item_id))
        task_label.bind("<Double-1>", lambda _event, item_id=entry_id: self._on_edit(item_id))
        task_label.bind("<MouseWheel>", self._on_rows_mousewheel)

        progress_frame = tk.Frame(row, bg=base_bg, height=self.row_content_height)
        progress_frame.grid(row=0, column=2, sticky="nsew", padx=(0, 12))
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

        started = self._started_date(entry)
        started_label = tk.Label(
            row,
            text=started.strftime("%m/%d") if isinstance(started, date) else "—",
            anchor="w",
            bg=base_bg,
            fg=COLOR_TEXT if started else COLOR_TEXT_MUTED,
            font=self.small_font,
        )
        started_label.grid(row=0, column=3, sticky="ew", padx=(0, 8))
        started_label.bind("<Button-1>", lambda _event, item_id=entry_id: self._select(item_id))
        started_label.bind("<Double-1>", lambda _event, item_id=entry_id: self._on_edit(item_id))
        started_label.bind("<MouseWheel>", self._on_rows_mousewheel)

        delay_label = tk.Label(
            row,
            anchor="w",
            bg=base_bg,
            fg=COLOR_TEXT_MUTED,
            font=self.small_font,
        )
        delay_label.grid(row=0, column=4, sticky="ew", padx=(0, 8))
        delay_label.bind("<Button-1>", lambda _event, item_id=entry_id: self._select(item_id))
        delay_label.bind("<MouseWheel>", self._on_rows_mousewheel)

        tk.Frame(row, width=self.splitter_width, bg=COLOR_BORDER).grid(
            row=0, column=5, sticky="ns"
        )

        gantt_canvas = tk.Canvas(
            row,
            height=self.row_content_height,
            background=base_bg,
            highlightthickness=0,
        )
        gantt_canvas.grid(row=0, column=6, sticky="ew", padx=(0, 4))
        gantt_canvas.bind("<Button-1>", lambda _event, item_id=entry_id: self._select(item_id))
        gantt_canvas.bind("<Configure>", lambda _event, item_id=entry_id: self._redraw_gantt_for(item_id))
        gantt_canvas.bind("<MouseWheel>", self._on_rows_mousewheel)

        for widget in (
            row,
            selection_bar,
            vis_label,
            task_frame,
            drag_handle,
            tree_indicator,
            task_label,
            progress_frame,
            progress_label,
            progress_canvas,
            started_label,
            delay_label,
            gantt_canvas,
        ):
            self._bind_row_context_menu(widget, "schedule", entry_id)

        self.row_widgets.append(
            RowWidgets(
                entry_id,
                row,
                selection_bar,
                drag_handle,
                vis_label,
                task_frame,
                tree_indicator,
                task_label,
                progress_frame,
                progress_label,
                progress_canvas,
                started_label,
                delay_label,
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
            widgets.drag_handle.configure(bg=bg)
            widgets.tree_indicator.configure(bg=bg)
            widgets.task_label.configure(bg=bg)
            widgets.progress_frame.configure(bg=bg)
            widgets.progress_label.configure(bg=bg)
            widgets.progress_canvas.configure(bg=bg)
            widgets.started_label.configure(bg=bg)
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

    def _on_move_to_todo(self) -> None:
        location = self._find(self.selected_id)
        if location is None:
            return
        group = location.parent
        snapshot = self._snapshot_schedule()
        moved = move_schedule_group_to_todos(self.schedule, group["id"])
        if moved is None:
            return
        previous_selection = self.selected_id
        self.selected_id = None
        self.selected_todo_id = moved["id"]
        if not self._save_or_restore(snapshot):
            self.selected_id = previous_selection
            self.selected_todo_id = None
        self._rebuild_rows()
        self._rebuild_todo_rows()

    def _on_move_to_schedule(self) -> None:
        location = find_todo(self.schedule, self.selected_todo_id or "")
        if location is None:
            return
        group = location.parent
        snapshot = self._snapshot_schedule()
        try:
            moved = move_todo_group_to_schedule(self.schedule, group["id"])
        except ValueError as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, str(exc))
            return
        if moved is None:
            return
        previous_selection = self.selected_todo_id
        self.selected_todo_id = None
        self.selected_id = moved["id"]
        if not self._save_or_restore(snapshot):
            self.selected_todo_id = previous_selection
            self.selected_id = None
        self._rebuild_todo_rows()
        self._rebuild_rows()

    def _on_add_todo(self) -> None:
        self._open_todo_dialog("parent")

    def _on_add_child_todo(self) -> None:
        location = find_todo(self.schedule, self.selected_todo_id or "")
        if location is None:
            messagebox.showwarning(
                WARNING_SELECT_PARENT_TITLE,
                WARNING_SELECT_TODO_PARENT_MESSAGE,
            )
            return
        self._open_todo_dialog("child", parent_id=location.parent["id"])

    def _on_edit_todo(self, entry_id: str) -> None:
        location = find_todo(self.schedule, entry_id)
        if location is None:
            return
        self._open_todo_dialog(
            location.entry.get("kind", "parent"),
            parent_id=location.entry.get("parent_id"),
            entry_id=entry_id,
        )

    def _on_delete_todo(self) -> None:
        location = find_todo(self.schedule, self.selected_todo_id or "")
        if location is None:
            return
        entry = location.entry
        message = (
            f"「{entry['task']}」と配下の子TODO {len(entry.get('children', []))}件を削除しますか？"
            if location.is_parent
            else f"「{entry['task']}」を削除しますか？"
        )
        if not messagebox.askyesno(CONFIRM_DELETE_TITLE, message):
            return
        snapshot = self._snapshot_schedule()
        previous_selection = self.selected_todo_id
        remove_todo(self.schedule, entry["id"])
        self.selected_todo_id = None
        if not self._save_or_restore(snapshot):
            self.selected_todo_id = previous_selection
        self._rebuild_todo_rows()

    def _move_selected_todo(self, direction: int) -> None:
        if not self.selected_todo_id:
            return
        snapshot = self._snapshot_schedule()
        if move_todo(self.schedule, self.selected_todo_id, direction):
            self._save_or_restore(snapshot)
            self._rebuild_todo_rows()

    def _on_complete_selected_todo(self) -> None:
        if self.selected_todo_id:
            self._on_complete_todo(self.selected_todo_id)

    def _on_complete_todo(self, entry_id: str) -> None:
        location = find_todo(self.schedule, entry_id)
        if location is None:
            return
        entry = location.entry
        targets = [entry]
        if location.is_parent:
            children = entry.get("children", [])
            targets.extend(children)
            message = CONFIRM_COMPLETE_TODO_PARENT_MESSAGE.format(
                task=entry["task"], count=len(children)
            )
        else:
            message = CONFIRM_COMPLETE_TODO_MESSAGE.format(task=entry["task"])
        if not messagebox.askyesno(CONFIRM_COMPLETE_TITLE, message):
            return

        snapshot = self._snapshot_schedule()
        previous_selection = self.selected_todo_id
        records = [self._todo_completion_record(target) for target in targets]
        remove_todo(self.schedule, entry_id)
        self.selected_todo_id = location.parent["id"] if not location.is_parent else None
        if self.selected_todo_id and find_todo(self.schedule, self.selected_todo_id) is None:
            self.selected_todo_id = None

        journal = {
            "version": 1,
            "records": records,
            "schedule": serialize_schedule(self.schedule),
        }
        journal_path = self._completion_journal_path()
        try:
            atomic_write_text(
                journal_path,
                json.dumps(journal, ensure_ascii=False, indent=2) + "\n",
                keep_backup=False,
            )
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_COMPLETE_LOG_WRITE}\n{exc}")
            self._restore_schedule(snapshot)
            self.selected_todo_id = previous_selection
            self._rebuild_todo_rows()
            return

        try:
            self._finish_completion_transaction(journal)
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_COMPLETION_RECOVERY}\n{exc}")
            self._restore_schedule(snapshot)
            self.selected_todo_id = previous_selection
            self.load_failed = True
            self._rebuild_todo_rows()
            return
        self._rebuild_todo_rows()

    def _on_complete_selected(self) -> None:
        if self.selected_id:
            self._on_complete(self.selected_id)

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
        records = [self._completion_record(target) for target in targets]
        remove_entry(self.schedule, entry_id)
        self.selected_id = location.parent["id"] if entry["kind"] == "child" else None
        if self.selected_id and self._find(self.selected_id) is None:
            self.selected_id = None

        journal = {
            "version": 1,
            "records": records,
            "schedule": serialize_schedule(self.schedule),
        }
        journal_path = self._completion_journal_path()
        try:
            atomic_write_text(
                journal_path,
                json.dumps(journal, ensure_ascii=False, indent=2) + "\n",
                keep_backup=False,
            )
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_COMPLETE_LOG_WRITE}\n{exc}")
            self._restore_schedule(snapshot)
            self.selected_id = previous_selection
            self._rebuild_rows()
            return

        try:
            self._finish_completion_transaction(journal)
        except Exception as exc:
            messagebox.showerror(ERROR_INPUT_TITLE, f"{ERROR_COMPLETION_RECOVERY}\n{exc}")
            self._restore_schedule(snapshot)
            self.selected_id = previous_selection
            self.load_failed = True
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
                started=record.get(LOG_FIELD_STARTED),
                entry_id=record_id or None,
            )
            if requested_kind == "child":
                parent_location.entry.setdefault("children", []).append(entry)
                clamp_children_to_parent(parent_location.entry)
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
    def _center_dialog_on_root(self, dlg: tk.Toplevel) -> None:
        dlg.update_idletasks()
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")

    def _open_todo_dialog(
        self,
        kind: str,
        parent_id: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        location = find_todo(self.schedule, entry_id or "")
        is_edit = location is not None
        title = "TODO編集" if is_edit else ("子TODO追加" if kind == "child" else "TODO追加")
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.configure(bg=COLOR_APP_BG)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        content = tk.Frame(
            dlg,
            bg=COLOR_SURFACE,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER_SOFT,
        )
        content.grid(row=0, column=0, padx=16, pady=16)
        content.columnconfigure(0, weight=1)
        tk.Label(
            content,
            text=title,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=self.title_font,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 16))
        task_var = tk.StringVar(value=location.entry.get("task", "") if is_edit else "")
        notify_var = tk.BooleanVar(
            value=location.entry.get("notify", False) if is_edit else True
        )
        tk.Label(
            content,
            text=LABEL_TASK_NAME,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=self.header_font,
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 6))
        task_entry = ttk.Entry(content, textvariable=task_var, width=48, style="Modern.TEntry")
        task_entry.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 14))
        tk.Label(
            content,
            text=LABEL_DEADLINE,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=self.header_font,
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 6))
        initial_deadline = location.entry.get("deadline") if is_edit else self.current_jst_date
        deadline_input = DateTimeInput(
            content,
            value=initial_deadline,
            background=COLOR_SURFACE,
        )
        deadline_input.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 12))
        ttk.Checkbutton(
            content,
            text="期限到来後、1時間ごとにWindows通知する",
            variable=notify_var,
        ).grid(row=5, column=0, sticky="w", padx=24)
        footer = tk.Frame(content, bg=COLOR_SURFACE)
        footer.grid(row=6, column=0, sticky="ew", padx=24, pady=(20, 20))
        footer.columnconfigure(0, weight=1)

        def close_dialog() -> None:
            if dlg.grab_current() == dlg:
                dlg.grab_release()
            dlg.destroy()

        def submit() -> None:
            task_text = task_var.get().strip()
            if not task_text:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_EMPTY_TASK)
                return
            try:
                deadline = deadline_input.get_datetime()
            except ValueError:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_INVALID_DEADLINE)
                return
            snapshot = self._snapshot_schedule()
            previous_selection = self.selected_todo_id
            if is_edit:
                current = find_todo(self.schedule, entry_id or "")
                if current is None:
                    return
                current.entry.update(
                    {
                        "task": task_text,
                        "deadline": deadline,
                        "notify": notify_var.get(),
                        "last_notified_at": None,
                    }
                )
                target = current.entry
            else:
                target = new_todo_entry(
                    kind,
                    task_text,
                    deadline,
                    parent_id=parent_id,
                    notify=notify_var.get(),
                )
                if kind == "parent":
                    self.todos.append(target)
                else:
                    parent = find_todo(self.schedule, parent_id or "")
                    if parent is None:
                        messagebox.showerror(ERROR_INPUT_TITLE, WARNING_SELECT_TODO_PARENT_MESSAGE)
                        return
                    parent.entry.setdefault("children", []).append(target)
                    parent.entry["collapsed"] = False
            self.selected_todo_id = target["id"]
            if not self._save_or_restore(snapshot):
                self.selected_todo_id = previous_selection
                self._rebuild_todo_rows()
                return
            self._rebuild_todo_rows()
            close_dialog()

        ttk.Button(
            footer,
            text=BUTTON_OK,
            command=submit,
            style="Primary.TButton",
        ).grid(row=0, column=1)
        ttk.Button(
            footer,
            text=BUTTON_CANCEL,
            command=close_dialog,
            style="Secondary.TButton",
        ).grid(row=0, column=2, padx=(8, 0))
        dlg.protocol("WM_DELETE_WINDOW", close_dialog)
        dlg.bind("<Escape>", lambda _event: close_dialog())
        dlg.bind("<Return>", lambda _event: submit())
        task_entry.focus_set()
        self._center_dialog_on_root(dlg)

    def _open_settings_dialog(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("表示設定")
        dlg.configure(bg=COLOR_APP_BG)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        frame = tk.Frame(dlg, bg=COLOR_SURFACE, padx=24, pady=20)
        frame.grid(row=0, column=0)
        tk.Label(
            frame,
            text="スケジュール行の高さ",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=self.header_font,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        height_var = tk.IntVar(value=self.row_content_height)
        tk.Scale(
            frame,
            from_=ROW_CONTENT_MIN_HEIGHT,
            to=72,
            orient="horizontal",
            variable=height_var,
            length=260,
            resolution=1,
            bg=COLOR_SURFACE,
            highlightthickness=0,
        ).grid(row=1, column=0, columnspan=2)
        tk.Label(
            frame,
            text="30px（コンパクト）～72px（広め）",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=self.small_font,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 16))

        def close_dialog() -> None:
            if dlg.grab_current() == dlg:
                dlg.grab_release()
            dlg.destroy()

        def apply_setting() -> None:
            snapshot = self._snapshot_schedule()
            self.row_content_height = self._normalized_row_height(height_var.get())
            self.schedule.setdefault("settings", {})["row_height"] = self.row_content_height
            if not self._save_or_restore(snapshot):
                self.row_content_height = self._normalized_row_height(
                    self.schedule.get("settings", {}).get(
                        "row_height", ROW_CONTENT_DEFAULT_HEIGHT
                    )
                )
                return
            self._rebuild_rows()
            self._rebuild_todo_rows()
            close_dialog()

        ttk.Button(
            frame,
            text=BUTTON_CANCEL,
            command=close_dialog,
            style="Secondary.TButton",
        ).grid(row=3, column=0, sticky="e")
        ttk.Button(
            frame,
            text="適用",
            command=apply_setting,
            style="Primary.TButton",
        ).grid(row=3, column=1, sticky="e", padx=(8, 0))
        dlg.protocol("WM_DELETE_WINDOW", close_dialog)
        dlg.bind("<Escape>", lambda _event: close_dialog())

    def _open_entry_dialog(
        self,
        kind: str,
        parent_id: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        location = self._find(entry_id)
        is_edit = location is not None
        started_is_derived = bool(
            is_edit
            and location.is_parent
            and location.entry.get("children")
        )
        stored_started = location.entry.get("started") if started_is_derived else None
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
        tk.Frame(content, height=3, bg=COLOR_PRIMARY).place(x=0, y=0, relwidth=1)

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
        progress_mode_var = tk.StringVar(value="percent")
        progress_value_var = tk.StringVar(value="0")
        progress_total_var = tk.StringVar(value="100")

        if is_edit:
            entry = location.entry
            task_var.set(entry["task"])
            initial_start = entry["start"]
            initial_end = entry["end"]
            initial_started = (
                effective_started_date(entry)
                if started_is_derived
                else entry.get("started")
            )
            progress_mode_var.set(entry.get("progress_mode", "percent"))
            progress_value_var.set(number_text(entry.get("progress_value", 0)))
            progress_total_var.set(number_text(entry.get("progress_total", 100)))
        else:
            today = self.current_jst_date
            initial_start = today
            initial_end = today
            initial_started = None

        form = tk.Frame(content, bg=COLOR_SURFACE)
        form.grid(row=2, column=0, sticky="ew", padx=24)
        form.columnconfigure(0, weight=1)

        tk.Label(
            form,
            text=LABEL_TASK_NAME,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
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
            fg=COLOR_TEXT_MUTED,
            font=self.header_font,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 6))
        tk.Label(
            dates_frame,
            text=LABEL_END_DATE,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=self.header_font,
            anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))
        start_input = DateInput(
            dates_frame,
            value=initial_start,
            background=COLOR_SURFACE,
        )
        end_input = DateInput(
            dates_frame,
            value=initial_end,
            background=COLOR_SURFACE,
        )
        last_changed_date = "start"

        def start_date_changed(value: date) -> None:
            nonlocal last_changed_date
            last_changed_date = "start"
            try:
                end_value = end_input.get_date()
            except ValueError:
                return
            if value > end_value:
                end_input.set_date(value, notify=False)

        def end_date_changed(value: date) -> None:
            nonlocal last_changed_date
            last_changed_date = "end"
            try:
                start_value = start_input.get_date()
            except ValueError:
                return
            if value < start_value:
                start_input.set_date(value, notify=False)

        def mark_start_changed(_event: tk.Event) -> None:
            nonlocal last_changed_date
            last_changed_date = "start"

        def mark_end_changed(_event: tk.Event) -> None:
            nonlocal last_changed_date
            last_changed_date = "end"

        start_input.set_on_change(start_date_changed)
        end_input.set_on_change(end_date_changed)
        for entry in start_input.entries:
            entry.bind("<KeyPress>", mark_start_changed, add="+")
        for entry in end_input.entries:
            entry.bind("<KeyPress>", mark_end_changed, add="+")
        start_input.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        end_input.grid(row=1, column=1, sticky="ew", padx=(8, 0))
        tk.Label(
            dates_frame,
            text=(
                LABEL_STARTED_DATE_DERIVED
                if started_is_derived
                else LABEL_STARTED_DATE
            ),
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=self.header_font,
            anchor="w",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 6))
        started_input = DateInput(
            dates_frame,
            value=initial_started,
            allow_empty=True,
            background=COLOR_SURFACE,
        )
        started_input.grid(row=3, column=0, columnspan=2, sticky="ew")
        started_input.set_enabled(not started_is_derived)

        tk.Label(
            form,
            text=LABEL_PROGRESS_MODE,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
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
            fg=COLOR_TEXT_MUTED,
            font=self.header_font,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 6))
        tk.Label(
            progress_frame,
            text=LABEL_PROGRESS_TOTAL,
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
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
        footer = tk.Frame(content, bg=COLOR_SURFACE)
        footer.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 22))
        footer.columnconfigure(0, weight=1)
        tk.Label(
            footer,
            text="Enterで保存  ·  Escで閉じる",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT_MUTED,
            font=self.small_font,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        button_box = tk.Frame(footer, bg=COLOR_SURFACE)
        button_box.grid(row=0, column=1, sticky="e")

        def submit() -> None:
            task_text = task_var.get().strip()
            if not task_text:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_EMPTY_TASK)
                return
            try:
                start_value = start_input.get_date()
                end_value = end_input.get_date()
                started_value = (
                    stored_started
                    if started_is_derived
                    else started_input.get_date(required=False)
                )
            except ValueError:
                messagebox.showerror(ERROR_INPUT_TITLE, ERROR_INVALID_DATE)
                return
            if end_value < start_value:
                if last_changed_date == "end":
                    start_value = end_value
                    start_input.set_date(start_value, notify=False)
                else:
                    end_value = start_value
                    end_input.set_date(end_value, notify=False)

            parent_location = None
            if kind == "child":
                parent_location = self._find(parent_id)
                if parent_location is None or not parent_location.is_parent:
                    messagebox.showerror(ERROR_INPUT_TITLE, WARNING_SELECT_PARENT_MESSAGE)
                    return
                if not child_dates_within_parent(
                    parent_location.entry,
                    start_value,
                    end_value,
                ):
                    messagebox.showerror(
                        ERROR_INPUT_TITLE,
                        ERROR_CHILD_OUTSIDE_PARENT,
                    )
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
            if not started_is_derived:
                started_value = started_date_for_progress(
                    started_value,
                    clean_value,
                    self.current_jst_date,
                )
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
                        "started": started_value,
                    }
                )
                if current_location.is_parent:
                    clamp_children_to_parent(target)
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
                    started=started_value,
                )
                if kind == "parent":
                    self.entries.append(target)
                else:
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
            text=BUTTON_OK,
            width=10,
            command=submit,
            style="Primary.TButton",
            cursor="hand2",
        ).grid(row=0, column=0)
        ttk.Button(
            button_box,
            text=BUTTON_CANCEL,
            width=10,
            command=close_dialog,
            style="Secondary.TButton",
            cursor="hand2",
        ).grid(
            row=0, column=1, padx=(8, 0)
        )

        task_entry.focus_set()
        dlg.bind("<Return>", lambda _event: submit())
        dlg.bind("<Escape>", lambda _event: close_dialog())
        self._center_dialog_on_root(dlg)

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
        pixels_per_day = usable_w / vis_days

        def x_for(index_value: int | float) -> float:
            return pad + usable_w * (index_value / vis_days)

        if pixels_per_day >= 2:
            days_to_weekend = (5 - start_all.weekday()) % 7
            weekend = (
                start_all + timedelta(days=days_to_weekend)
                if days_to_weekend <= (date.max - start_all).days
                else None
            )
            weekend_color = (
                COLOR_SELECTED_WEEKEND
                if widgets.entry_id == self.selected_id
                else COLOR_WEEKEND
            )
            while weekend is not None and weekend <= end_all:
                weekend_end = (
                    weekend
                    if weekend == date.max
                    else min(end_all, weekend + timedelta(days=1))
                )
                canvas.create_rectangle(
                    x_for((weekend - start_all).days),
                    0,
                    x_for((weekend_end - start_all).days + 1),
                    height,
                    fill=weekend_color,
                    outline="",
                )
                if (date.max - weekend).days < 7:
                    break
                weekend += timedelta(days=7)

        x_today = None
        if start_all <= self.current_jst_date <= end_all:
            today_index = (self.current_jst_date - start_all).days
            x_today = x_for(today_index)
            canvas.create_rectangle(
                max(0, x_today - max(3, pixels_per_day / 2)),
                0,
                min(width, x_today + max(3, pixels_per_day / 2)),
                height,
                fill=TODAY_HIGHLIGHT_BG,
                outline="",
            )

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
                outline=(
                    COLOR_PRIMARY
                    if widgets.entry_id == self.selected_id
                    else completed_color
                ),
                width=2 if widgets.entry_id == self.selected_id else 1,
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

        if x_today is not None:
            canvas.create_line(max(0, min(width, x_today)), 0, max(0, min(width, x_today)), height, fill=TODAY_LINE_COLOR, width=2)

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
        vis_days = max(1, (end_all - start_all).days + 1)
        pad = 4
        usable_w = max(1, width - 2 * pad)
        pixels_per_day = usable_w / vis_days

        def x_for(index_value: int | float) -> float:
            return pad + usable_w * (index_value / vis_days)

        if pixels_per_day >= 3:
            days_to_weekend = (5 - start_all.weekday()) % 7
            weekend = (
                start_all + timedelta(days=days_to_weekend)
                if days_to_weekend <= (date.max - start_all).days
                else None
            )
            while weekend is not None and weekend <= end_all:
                weekend_end = (
                    weekend
                    if weekend == date.max
                    else min(end_all, weekend + timedelta(days=1))
                )
                canvas.create_rectangle(
                    x_for((weekend - start_all).days),
                    0,
                    x_for((weekend_end - start_all).days + 1),
                    height,
                    fill=COLOR_WEEKEND,
                    outline="",
                )
                if (date.max - weekend).days < 7:
                    break
                weekend += timedelta(days=7)

        y_year, y_month, y_day = scale_header_row_positions(
            height,
            self.header_font.metrics("linespace"),
            self.small_font.metrics("linespace"),
        )

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
                    text=f"{current_month.month}月",
                    anchor="n",
                    fill=COLOR_TEXT_MUTED,
                    font=self.small_font,
                )
            if pad <= x0 <= width - pad:
                canvas.create_line(x0, 0, x0, height - 1, fill=COLOR_GRID)
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
                fill="white" if day_value == self.current_jst_date else COLOR_TEXT_MUTED,
                font=self.small_font,
            )
            if day_value == self.current_jst_date:
                bbox = canvas.bbox(label)
                if bbox:
                    highlight = create_rounded_rectangle(
                        canvas,
                        bbox[0] - 2,
                        bbox[1] - 1,
                        bbox[2] + 2,
                        bbox[3] + 1,
                        4,
                        fill=TODAY_LINE_COLOR,
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
    configure_application_icon(root)
    ScheduleApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

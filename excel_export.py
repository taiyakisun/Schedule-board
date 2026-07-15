"""ガントチャートを依存ライブラリなしでXLSXへ出力する。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
import math
import os
from pathlib import Path
import tempfile
from typing import Any
import unicodedata
import xml.etree.ElementTree as ET
import zipfile


SHEET_NAME = "ガントチャート"
FIXED_COLUMN_COUNT = 6
MAX_EXCEL_COLUMNS = 16_384
MAX_EXCEL_ROWS = 1_048_576
TASK_COLUMN_WIDTH = 40

STYLE_DEFAULT = 0
STYLE_HEADER = 1
STYLE_HEADER_DATE = 2
STYLE_HEADER_TODAY = 3
STYLE_BODY_TEXT = 4
STYLE_PARENT_TEXT = 5
STYLE_BODY_DATE = 6
STYLE_PARENT_DATE = 7
STYLE_BODY_PERCENT = 8
STYLE_PARENT_PERCENT = 9
STYLE_BODY_NUMBER = 10
STYLE_PARENT_NUMBER = 11
STYLE_DELAY = 12
STYLE_PARENT_DELAY = 13
STYLE_GANTT_PROGRESS = 14
STYLE_GANTT_REMAINING = 15
STYLE_BODY_CENTER = 16
STYLE_PARENT_CENTER = 17
STYLE_PARENT_TREE_TEXT = 18
STYLE_CHILD_TREE_TEXT = 19

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
CORE_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
EXTENDED_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"

HEADERS = (
    "タスク",
    "開始日",
    "終了日",
    "進捗",
    "進捗率",
    "遅延日数",
)


@dataclass(frozen=True)
class _Progress:
    mode: str
    current: float
    total: float

    @property
    def rate(self) -> float:
        return self.current / self.total

    @property
    def label(self) -> str:
        if self.mode == "percent":
            return f"{_format_number(self.current)}%"
        return f"{_format_number(self.current)} / {_format_number(self.total)}"


@dataclass(frozen=True)
class _ExportRow:
    kind: str
    tree_title: str
    start: date
    end: date
    effective_visible: bool
    progress: _Progress
    delay_days: int
    hidden: bool = False
    collapsed: bool = False

    @property
    def is_parent(self) -> bool:
        return self.kind == "親"


def export_to_excel(
    parents: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    reference_date: date | datetime | str,
    output_path: str | os.PathLike[str],
) -> Path:
    """v2形式の親配列をXLSXへ書き出し、出力先を返す。"""
    today = _coerce_date(reference_date, "reference_date")
    rows = _normalize_rows(parents, today)
    dates = _date_columns(rows)
    if len(rows) + 1 > MAX_EXCEL_ROWS:
        raise ValueError("タスク数がExcelの最大行数を超えています。")
    if len(dates) + FIXED_COLUMN_COUNT > MAX_EXCEL_COLUMNS:
        raise ValueError("日付範囲がExcelの最大列数を超えています。")
    sheet_xml = _build_sheet_xml(rows, dates, today)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
        ) as handle:
            temporary_path = Path(handle.name)
        _write_package(temporary_path, sheet_xml, today)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return destination


def _normalize_rows(
    source: Sequence[Mapping[str, Any]] | Mapping[str, Any], today: date
) -> list[_ExportRow]:
    if isinstance(source, Mapping):
        source = source.get("parents", source.get("entries", []))
    if isinstance(source, (str, bytes)) or not isinstance(source, Sequence):
        raise TypeError("parentsは親タスクの配列で指定してください。")

    rows: list[_ExportRow] = []
    for parent_index, parent in enumerate(source):
        if not isinstance(parent, Mapping):
            raise TypeError(f"parents[{parent_index}]はオブジェクトで指定してください。")
        parent_title = _title(parent, f"parents[{parent_index}]")
        parent_start, parent_end = _schedule_dates(parent, f"parents[{parent_index}]")
        parent_visible = _coerce_bool(parent.get("visible", True))
        if "expanded" in parent:
            expanded = _coerce_bool(parent["expanded"])
        else:
            expanded = not _coerce_bool(parent.get("collapsed", False))
        children = parent.get("children", [])
        if isinstance(children, (str, bytes)) or not isinstance(children, Sequence):
            raise TypeError(f"parents[{parent_index}].childrenは配列で指定してください。")

        rows.append(
            _ExportRow(
                kind="親",
                tree_title=(
                    f"{'▾' if expanded else '▸'} {parent_title}"
                    if children
                    else f"• {parent_title}"
                ),
                start=parent_start,
                end=parent_end,
                effective_visible=parent_visible,
                progress=_progress(parent, f"parents[{parent_index}]"),
                delay_days=max(0, (today - parent_end).days),
                collapsed=bool(children) and not expanded,
            )
        )

        for child_index, child in enumerate(children):
            path = f"parents[{parent_index}].children[{child_index}]"
            if not isinstance(child, Mapping):
                raise TypeError(f"{path}はオブジェクトで指定してください。")
            child_title = _title(child, path)
            child_start, child_end = _schedule_dates(child, path)
            child_visible = _coerce_bool(child.get("visible", True))
            effective_visible = parent_visible and child_visible
            branch = "└─" if child_index == len(children) - 1 else "├─"
            rows.append(
                _ExportRow(
                    kind="子",
                    tree_title=f"{branch} {child_title}",
                    start=child_start,
                    end=child_end,
                    effective_visible=effective_visible,
                    progress=_progress(child, path),
                    delay_days=max(0, (today - child_end).days),
                    hidden=not expanded,
                )
            )
    return rows


def _title(entry: Mapping[str, Any], path: str) -> str:
    value = entry.get("task", entry.get("title", entry.get("name", "")))
    text = _sanitize_xml_text(str(value).strip())
    if not text:
        raise ValueError(f"{path}のタイトルが空です。")
    return text


def _schedule_dates(entry: Mapping[str, Any], path: str) -> tuple[date, date]:
    if "start" not in entry or "end" not in entry:
        raise ValueError(f"{path}にはstartとendが必要です。")
    start = _coerce_date(entry["start"], f"{path}.start")
    end = _coerce_date(entry["end"], f"{path}.end")
    if end < start:
        raise ValueError(f"{path}のendはstart以降にしてください。")
    return start, end


def _progress(entry: Mapping[str, Any], path: str) -> _Progress:
    progress_value = entry.get("progress")
    progress_map = progress_value if isinstance(progress_value, Mapping) else {}
    mode_value = entry.get(
        "progress_mode",
        entry.get("progress_type", progress_map.get("mode", progress_map.get("type"))),
    )
    current_value = entry.get(
        "progress_current",
        entry.get(
            "progress_value",
            progress_map.get("current", progress_map.get("value", progress_value if not progress_map else 0)),
        ),
    )
    total_value = entry.get(
        "progress_total",
        entry.get("progress_max", progress_map.get("total", progress_map.get("max"))),
    )

    if mode_value is None:
        mode = "custom" if total_value not in (None, 100, 100.0) else "percent"
    else:
        mode_text = str(mode_value).strip().lower()
        if mode_text in {"percent", "percentage", "%", "パーセント"}:
            mode = "percent"
        elif mode_text in {"custom", "value", "number", "numeric", "指定値", "数値"}:
            mode = "custom"
        else:
            raise ValueError(f"{path}.progress_modeが不正です。")

    current = _coerce_number(0 if current_value is None else current_value, f"{path}.progress_current")
    if mode == "percent":
        total = 100.0
    else:
        if total_value is None:
            raise ValueError(f"{path}.progress_totalを指定してください。")
        total = _coerce_number(total_value, f"{path}.progress_total")
    if total <= 0:
        raise ValueError(f"{path}.progress_totalは0より大きくしてください。")
    if current < 0 or current > total:
        raise ValueError(f"{path}.progress_currentは0からprogress_totalの範囲で指定してください。")
    return _Progress(mode=mode, current=current, total=total)


def _coerce_date(value: date | datetime | str, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"{field_name}はYYYY-MM-DD形式で指定してください。") from exc
    raise TypeError(f"{field_name}は日付またはYYYY-MM-DD文字列で指定してください。")


def _coerce_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field_name}は数値で指定してください。")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name}は数値で指定してください。") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name}は有限の数値で指定してください。")
    return number


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"false", "0", "no", "off", "非表示"}:
            return False
        if normalized in {"true", "1", "yes", "on", "表示"}:
            return True
    return bool(value)


def _format_number(value: float) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def _sanitize_xml_text(value: str) -> str:
    def is_valid(character: str) -> bool:
        code_point = ord(character)
        return (
            code_point in (0x09, 0x0A, 0x0D)
            or 0x20 <= code_point <= 0xD7FF
            or 0xE000 <= code_point <= 0xFFFD
            or 0x10000 <= code_point <= 0x10FFFF
        )

    return "".join(character if is_valid(character) else "\ufffd" for character in value)


def _date_columns(rows: Sequence[_ExportRow]) -> list[date]:
    if not rows:
        return []
    first = min(row.start for row in rows)
    last = max(row.end for row in rows)
    return [date.fromordinal(day) for day in range(first.toordinal(), last.toordinal() + 1)]


def _build_sheet_xml(rows: Sequence[_ExportRow], dates: Sequence[date], today: date) -> bytes:
    last_column = FIXED_COLUMN_COUNT + len(dates)
    last_row = len(rows) + 1
    last_reference = f"{_column_name(last_column)}{last_row}"
    root = ET.Element("worksheet", {"xmlns": MAIN_NS, "xmlns:r": REL_NS})

    sheet_pr = ET.SubElement(root, "sheetPr")
    ET.SubElement(sheet_pr, "outlinePr", {"summaryBelow": "0", "summaryRight": "1"})
    ET.SubElement(sheet_pr, "pageSetUpPr", {"fitToPage": "1"})
    ET.SubElement(root, "dimension", {"ref": f"A1:{last_reference}"})

    sheet_views = ET.SubElement(root, "sheetViews")
    sheet_view = ET.SubElement(
        sheet_views,
        "sheetView",
        {"workbookViewId": "0", "showGridLines": "0", "showOutlineSymbols": "1"},
    )
    ET.SubElement(
        sheet_view,
        "pane",
        {
            "xSplit": str(FIXED_COLUMN_COUNT),
            "ySplit": "1",
            "topLeftCell": f"{_column_name(FIXED_COLUMN_COUNT + 1)}2",
            "activePane": "bottomRight",
            "state": "frozen",
        },
    )
    ET.SubElement(
        sheet_view,
        "selection",
        {
            "pane": "bottomRight",
            "activeCell": f"{_column_name(FIXED_COLUMN_COUNT + 1)}2",
            "sqref": f"{_column_name(FIXED_COLUMN_COUNT + 1)}2",
        },
    )
    ET.SubElement(
        root,
        "sheetFormatPr",
        {
            "defaultRowHeight": "18",
            "outlineLevelRow": "1" if any(not row.is_parent for row in rows) else "0",
        },
    )

    columns = ET.SubElement(root, "cols")
    widths = (TASK_COLUMN_WIDTH, 12, 12, _progress_column_width(rows), 10, 10)
    for index, width in enumerate(widths, start=1):
        ET.SubElement(
            columns,
            "col",
            {"min": str(index), "max": str(index), "width": str(width), "customWidth": "1"},
        )
    if dates:
        ET.SubElement(
            columns,
            "col",
            {
                "min": str(FIXED_COLUMN_COUNT + 1),
                "max": str(last_column),
                "width": "4.2",
                "customWidth": "1",
            },
        )

    sheet_data = ET.SubElement(root, "sheetData")
    header_row = ET.SubElement(sheet_data, "row", {"r": "1", "ht": "30", "customHeight": "1"})
    for column_index, header in enumerate(HEADERS, start=1):
        _add_inline_cell(header_row, column_index, 1, header, STYLE_HEADER)
    for offset, day in enumerate(dates, start=FIXED_COLUMN_COUNT + 1):
        style = STYLE_HEADER_TODAY if day == today else STYLE_HEADER_DATE
        _add_number_cell(header_row, offset, 1, _excel_serial(day), style)

    first_date = dates[0] if dates else None
    for row_index, export_row in enumerate(rows, start=2):
        attributes = {
            "r": str(row_index),
            "ht": str(_tree_row_height(export_row.tree_title)),
            "customHeight": "1",
        }
        if not export_row.is_parent:
            attributes["outlineLevel"] = "1"
        if export_row.hidden:
            attributes["hidden"] = "1"
        if export_row.collapsed:
            attributes["collapsed"] = "1"
        row_element = ET.SubElement(sheet_data, "row", attributes)
        tree_style = (
            STYLE_PARENT_TREE_TEXT if export_row.is_parent else STYLE_CHILD_TREE_TEXT
        )
        center_style = STYLE_PARENT_CENTER if export_row.is_parent else STYLE_BODY_CENTER
        date_style = STYLE_PARENT_DATE if export_row.is_parent else STYLE_BODY_DATE
        percent_style = STYLE_PARENT_PERCENT if export_row.is_parent else STYLE_BODY_PERCENT
        number_style = STYLE_PARENT_NUMBER if export_row.is_parent else STYLE_BODY_NUMBER
        delay_style = (
            STYLE_PARENT_DELAY if export_row.is_parent else STYLE_DELAY
        ) if export_row.delay_days > 0 else number_style

        _add_inline_cell(row_element, 1, row_index, export_row.tree_title, tree_style)
        _add_number_cell(row_element, 2, row_index, _excel_serial(export_row.start), date_style)
        _add_number_cell(row_element, 3, row_index, _excel_serial(export_row.end), date_style)
        _add_inline_cell(row_element, 4, row_index, export_row.progress.label, center_style)
        _add_number_cell(row_element, 5, row_index, export_row.progress.rate, percent_style)
        _add_number_cell(row_element, 6, row_index, export_row.delay_days, delay_style)

        if first_date is None or not export_row.effective_visible:
            continue
        span_days = (export_row.end - export_row.start).days + 1
        completed_days = min(
            span_days,
            int(math.ceil((span_days * export_row.progress.rate) - 1e-12)),
        )
        start_offset = (export_row.start - first_date).days
        for day_offset in range(span_days):
            column_index = FIXED_COLUMN_COUNT + 1 + start_offset + day_offset
            style = STYLE_GANTT_PROGRESS if day_offset < completed_days else STYLE_GANTT_REMAINING
            _add_inline_cell(row_element, column_index, row_index, "", style)

    ET.SubElement(root, "autoFilter", {"ref": f"A1:{last_reference}"})
    ET.SubElement(
        root,
        "pageMargins",
        {"left": "0.25", "right": "0.25", "top": "0.5", "bottom": "0.5", "header": "0.2", "footer": "0.2"},
    )
    ET.SubElement(
        root,
        "pageSetup",
        {"orientation": "landscape", "fitToWidth": "1", "fitToHeight": "0", "paperSize": "9"},
    )
    return _xml_bytes(root)


def _add_inline_cell(
    row: ET.Element, column_index: int, row_index: int, value: str, style: int
) -> None:
    cell = ET.SubElement(
        row,
        "c",
        {"r": f"{_column_name(column_index)}{row_index}", "s": str(style), "t": "inlineStr"},
    )
    inline = ET.SubElement(cell, "is")
    text = ET.SubElement(inline, "t")
    text.text = value


def _progress_column_width(rows: Sequence[_ExportRow]) -> int:
    longest_label = max((len(row.progress.label) for row in rows), default=0)
    return min(12, max(8, longest_label + 2))


def _tree_row_height(title: str) -> int:
    display_units = sum(
        2 if unicodedata.east_asian_width(character) in {"W", "F", "A"} else 1
        for character in title
    )
    line_count = max(1, math.ceil(display_units / (TASK_COLUMN_WIDTH * 1.5)))
    return min(120, line_count * 20)


def _add_number_cell(
    row: ET.Element, column_index: int, row_index: int, value: int | float, style: int
) -> None:
    cell = ET.SubElement(
        row,
        "c",
        {"r": f"{_column_name(column_index)}{row_index}", "s": str(style)},
    )
    ET.SubElement(cell, "v").text = str(value)


def _excel_serial(value: date) -> int:
    return (value - date(1899, 12, 30)).days


def _column_name(index: int) -> str:
    if index < 1:
        raise ValueError("列番号は1以上で指定してください。")
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _build_styles_xml() -> bytes:
    root = ET.Element("styleSheet", {"xmlns": MAIN_NS})
    number_formats = ET.SubElement(root, "numFmts", {"count": "3"})
    ET.SubElement(number_formats, "numFmt", {"numFmtId": "164", "formatCode": "yyyy-mm-dd"})
    ET.SubElement(number_formats, "numFmt", {"numFmtId": "165", "formatCode": "m/d"})
    ET.SubElement(number_formats, "numFmt", {"numFmtId": "166", "formatCode": "0.0%"})

    fonts = ET.SubElement(root, "fonts", {"count": "4"})
    _add_font(fonts)
    _add_font(fonts, bold=True, color="FFFFFFFF")
    _add_font(fonts, bold=True, color="FF1F1F1F")
    _add_font(fonts, bold=True, color="FFC00000")

    fills = ET.SubElement(root, "fills", {"count": "8"})
    _add_fill(fills, pattern="none")
    _add_fill(fills, pattern="gray125")
    _add_fill(fills, color="FF1F4E78")
    _add_fill(fills, color="FFD9EAF7")
    _add_fill(fills, color="FF2E7D32")
    _add_fill(fills, color="FFA5D6A7")
    _add_fill(fills, color="FFFCE8E6")
    _add_fill(fills, color="FFC00000")

    borders = ET.SubElement(root, "borders", {"count": "2"})
    _add_border(borders, colored=False)
    _add_border(borders, colored=True)

    style_xfs = ET.SubElement(root, "cellStyleXfs", {"count": "1"})
    ET.SubElement(style_xfs, "xf", {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0"})
    cell_xfs = ET.SubElement(root, "cellXfs", {"count": "20"})
    _add_xf(cell_xfs)
    _add_xf(cell_xfs, font=1, fill=2, border=1, align="center", wrap=True)
    _add_xf(cell_xfs, num_fmt=165, font=1, fill=2, border=1, align="center")
    _add_xf(cell_xfs, num_fmt=165, font=1, fill=7, border=1, align="center")
    _add_xf(cell_xfs, border=1, align="left")
    _add_xf(cell_xfs, font=2, fill=3, border=1, align="left")
    _add_xf(cell_xfs, num_fmt=164, border=1, align="center")
    _add_xf(cell_xfs, num_fmt=164, font=2, fill=3, border=1, align="center")
    _add_xf(cell_xfs, num_fmt=166, border=1, align="right")
    _add_xf(cell_xfs, num_fmt=166, font=2, fill=3, border=1, align="right")
    _add_xf(cell_xfs, border=1, align="right")
    _add_xf(cell_xfs, font=2, fill=3, border=1, align="right")
    _add_xf(cell_xfs, font=3, fill=6, border=1, align="right")
    _add_xf(cell_xfs, font=3, fill=6, border=1, align="right")
    _add_xf(cell_xfs, fill=4, border=1, align="center")
    _add_xf(cell_xfs, fill=5, border=1, align="center")
    _add_xf(cell_xfs, border=1, align="center")
    _add_xf(cell_xfs, font=2, fill=3, border=1, align="center")
    _add_xf(cell_xfs, font=2, fill=3, border=1, align="left", wrap=True)
    _add_xf(cell_xfs, border=1, align="left", wrap=True, indent=1)

    cell_styles = ET.SubElement(root, "cellStyles", {"count": "1"})
    ET.SubElement(cell_styles, "cellStyle", {"name": "Normal", "xfId": "0", "builtinId": "0"})
    ET.SubElement(root, "dxfs", {"count": "0"})
    ET.SubElement(
        root,
        "tableStyles",
        {"count": "0", "defaultTableStyle": "TableStyleMedium2", "defaultPivotStyle": "PivotStyleLight16"},
    )
    return _xml_bytes(root)


def _add_font(parent: ET.Element, bold: bool = False, color: str | None = None) -> None:
    font = ET.SubElement(parent, "font")
    if bold:
        ET.SubElement(font, "b")
    ET.SubElement(font, "sz", {"val": "11"})
    ET.SubElement(font, "color", {"rgb": color} if color else {"theme": "1"})
    ET.SubElement(font, "name", {"val": "Calibri"})
    ET.SubElement(font, "family", {"val": "2"})
    ET.SubElement(font, "scheme", {"val": "minor"})


def _add_fill(parent: ET.Element, color: str | None = None, pattern: str = "solid") -> None:
    fill = ET.SubElement(parent, "fill")
    pattern_fill = ET.SubElement(fill, "patternFill", {"patternType": pattern})
    if color is not None:
        ET.SubElement(pattern_fill, "fgColor", {"rgb": color})
        ET.SubElement(pattern_fill, "bgColor", {"indexed": "64"})


def _add_border(parent: ET.Element, colored: bool) -> None:
    border = ET.SubElement(parent, "border")
    for side_name in ("left", "right", "top", "bottom"):
        attributes = {"style": "thin"} if colored else {}
        side = ET.SubElement(border, side_name, attributes)
        if colored:
            ET.SubElement(side, "color", {"rgb": "FFD9E2F3"})
    ET.SubElement(border, "diagonal")


def _add_xf(
    parent: ET.Element,
    num_fmt: int = 0,
    font: int = 0,
    fill: int = 0,
    border: int = 0,
    align: str | None = None,
    wrap: bool = False,
    indent: int = 0,
) -> None:
    attributes = {
        "numFmtId": str(num_fmt),
        "fontId": str(font),
        "fillId": str(fill),
        "borderId": str(border),
        "xfId": "0",
    }
    if num_fmt:
        attributes["applyNumberFormat"] = "1"
    if font:
        attributes["applyFont"] = "1"
    if fill:
        attributes["applyFill"] = "1"
    if border:
        attributes["applyBorder"] = "1"
    if align is not None or wrap or indent:
        attributes["applyAlignment"] = "1"
    xf = ET.SubElement(parent, "xf", attributes)
    if align is not None or wrap or indent:
        alignment = {"vertical": "center"}
        if align is not None:
            alignment["horizontal"] = align
        if wrap:
            alignment["wrapText"] = "1"
        if indent:
            alignment["indent"] = str(indent)
        ET.SubElement(xf, "alignment", alignment)


def _write_package(path: Path, sheet_xml: bytes, reference_date: date) -> None:
    parts = {
        "[Content_Types].xml": _content_types_xml(),
        "_rels/.rels": _root_relationships_xml(),
        "docProps/app.xml": _app_properties_xml(),
        "docProps/core.xml": _core_properties_xml(reference_date),
        "xl/workbook.xml": _workbook_xml(),
        "xl/_rels/workbook.xml.rels": _workbook_relationships_xml(),
        "xl/styles.xml": _build_styles_xml(),
        "xl/worksheets/sheet1.xml": sheet_xml,
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, content)


def _content_types_xml() -> bytes:
    root = ET.Element("Types", {"xmlns": CONTENT_TYPES_NS})
    ET.SubElement(root, "Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
    ET.SubElement(root, "Default", {"Extension": "xml", "ContentType": "application/xml"})
    overrides = (
        ("/xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
        ("/xl/worksheets/sheet1.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"),
        ("/xl/styles.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"),
        ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
        ("/docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml"),
    )
    for part_name, content_type in overrides:
        ET.SubElement(root, "Override", {"PartName": part_name, "ContentType": content_type})
    return _xml_bytes(root)


def _root_relationships_xml() -> bytes:
    root = ET.Element("Relationships", {"xmlns": PACKAGE_REL_NS})
    relationships = (
        ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", "xl/workbook.xml"),
        ("rId2", "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties", "docProps/core.xml"),
        ("rId3", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties", "docProps/app.xml"),
    )
    for relation_id, relation_type, target in relationships:
        ET.SubElement(root, "Relationship", {"Id": relation_id, "Type": relation_type, "Target": target})
    return _xml_bytes(root)


def _workbook_xml() -> bytes:
    root = ET.Element("workbook", {"xmlns": MAIN_NS, "xmlns:r": REL_NS})
    book_views = ET.SubElement(root, "bookViews")
    ET.SubElement(book_views, "workbookView", {"xWindow": "0", "yWindow": "0", "windowWidth": "24000", "windowHeight": "12000"})
    sheets = ET.SubElement(root, "sheets")
    ET.SubElement(sheets, "sheet", {"name": SHEET_NAME, "sheetId": "1", "r:id": "rId1"})
    ET.SubElement(root, "calcPr", {"calcId": "191029", "fullCalcOnLoad": "1"})
    return _xml_bytes(root)


def _workbook_relationships_xml() -> bytes:
    root = ET.Element("Relationships", {"xmlns": PACKAGE_REL_NS})
    ET.SubElement(
        root,
        "Relationship",
        {
            "Id": "rId1",
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
            "Target": "worksheets/sheet1.xml",
        },
    )
    ET.SubElement(
        root,
        "Relationship",
        {
            "Id": "rId2",
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
            "Target": "styles.xml",
        },
    )
    return _xml_bytes(root)


def _core_properties_xml(reference_date: date) -> bytes:
    root = ET.Element(
        "cp:coreProperties",
        {
            "xmlns:cp": CORE_NS,
            "xmlns:dc": DC_NS,
            "xmlns:dcterms": DCTERMS_NS,
            "xmlns:xsi": XSI_NS,
        },
    )
    ET.SubElement(root, "dc:creator").text = "sch_gantt"
    ET.SubElement(root, "cp:lastModifiedBy").text = "sch_gantt"
    timestamp = f"{reference_date.isoformat()}T00:00:00Z"
    ET.SubElement(root, "dcterms:created", {"xsi:type": "dcterms:W3CDTF"}).text = timestamp
    ET.SubElement(root, "dcterms:modified", {"xsi:type": "dcterms:W3CDTF"}).text = timestamp
    return _xml_bytes(root)


def _app_properties_xml() -> bytes:
    root = ET.Element("Properties", {"xmlns": EXTENDED_NS, "xmlns:vt": VT_NS})
    ET.SubElement(root, "Application").text = "sch_gantt"
    ET.SubElement(root, "AppVersion").text = "1.0"
    return _xml_bytes(root)


def _xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=True)


__all__ = ["export_to_excel"]

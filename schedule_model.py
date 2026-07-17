from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Iterator
from uuid import UUID, uuid4, uuid5


SCHEMA_VERSION = 2
KIND_PARENT = "parent"
KIND_CHILD = "child"
PROGRESS_PERCENT = "percent"
PROGRESS_VALUE = "value"

_ID_NAMESPACE = UUID("f14e52f8-e596-40f6-93e4-55f56962cf10")


@dataclass(frozen=True)
class EntryLocation:
    parent: dict
    entry: dict
    parent_index: int
    child_index: int | None

    @property
    def is_parent(self) -> bool:
        return self.child_index is None


def _parse_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value.strip())
    raise TypeError("date value must be a date, datetime, or ISO date string")


def _number(value: object, field_name: str) -> int | float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    if number.is_integer():
        return int(number)
    return number


def _normalize_progress(
    mode: object,
    value: object,
    total: object,
) -> tuple[str, int | float, int | float]:
    mode_text = str(mode or PROGRESS_PERCENT)
    if mode_text not in (PROGRESS_PERCENT, PROGRESS_VALUE):
        raise ValueError(f"unsupported progress mode: {mode_text}")

    value_number = _number(value, "progress_value")
    if mode_text == PROGRESS_PERCENT:
        total_number: int | float = 100
    else:
        total_number = _number(total, "progress_total")
        if total_number <= 0:
            raise ValueError("progress_total must be greater than zero")

    value_number = max(0, min(value_number, total_number))
    return mode_text, value_number, total_number


def new_entry(
    kind: str,
    task: str,
    start: date | datetime | str,
    end: date | datetime | str,
    *,
    parent_id: str | None = None,
    entry_id: str | None = None,
    visible: bool = True,
    progress_mode: str = PROGRESS_PERCENT,
    progress_value: int | float = 0,
    progress_total: int | float = 100,
    collapsed: bool = False,
) -> dict:
    """Create a normalized parent or child entry.

    A generated UUID is assigned once and is then preserved by serialization.
    Progress values are clamped to their valid range.
    """

    if kind not in (KIND_PARENT, KIND_CHILD):
        raise ValueError(f"unsupported entry kind: {kind}")
    if kind == KIND_CHILD and not parent_id:
        raise ValueError("a child entry requires parent_id")

    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if end_date < start_date:
        raise ValueError("end must be on or after start")

    mode, value, total = _normalize_progress(progress_mode, progress_value, progress_total)
    normalized = {
        "id": str(entry_id or uuid4()),
        "kind": kind,
        "parent_id": None if kind == KIND_PARENT else str(parent_id),
        "task": str(task),
        "start": start_date,
        "end": end_date,
        "visible": bool(visible),
        "progress_mode": mode,
        "progress_value": value,
        "progress_total": total,
    }
    if kind == KIND_PARENT:
        normalized["collapsed"] = bool(collapsed)
        normalized["children"] = []
    return normalized


def _stable_id(seed: str) -> str:
    return str(uuid5(_ID_NAMESPACE, seed))


def _unique_id(preferred: object, seed: str, used_ids: set[str]) -> str:
    candidate = str(preferred).strip() if preferred is not None else ""
    if candidate and candidate not in used_ids:
        used_ids.add(candidate)
        return candidate

    suffix = 0
    while True:
        candidate = _stable_id(seed if suffix == 0 else f"{seed}:{suffix}")
        if candidate not in used_ids:
            used_ids.add(candidate)
            return candidate
        suffix += 1


def _entry_seed(prefix: str, index: int, raw: dict) -> str:
    return ":".join(
        (
            prefix,
            str(index),
            str(raw.get("task", "")),
            str(raw.get("start", "")),
            str(raw.get("end", "")),
        )
    )


def _deserialize_v2(raw: dict) -> dict:
    parents_raw = raw.get("parents")
    if not isinstance(parents_raw, list):
        raise ValueError("version 2 schedule requires a parents list")

    used_ids: set[str] = set()
    parents: list[dict] = []
    for parent_index, raw_parent in enumerate(parents_raw):
        if not isinstance(raw_parent, dict):
            raise ValueError("each parent must be an object")
        parent_id = _unique_id(
            raw_parent.get("id"),
            _entry_seed("v2-parent", parent_index, raw_parent),
            used_ids,
        )
        parent = new_entry(
            KIND_PARENT,
            raw_parent.get("task", ""),
            raw_parent["start"],
            raw_parent["end"],
            entry_id=parent_id,
            visible=raw_parent.get("visible", True),
            progress_mode=raw_parent.get("progress_mode", PROGRESS_PERCENT),
            progress_value=raw_parent.get("progress_value", 0),
            progress_total=raw_parent.get("progress_total", 100),
            collapsed=raw_parent.get("collapsed", False),
        )

        children_raw = raw_parent.get("children", [])
        if not isinstance(children_raw, list):
            raise ValueError("parent children must be a list")
        for child_index, raw_child in enumerate(children_raw):
            if not isinstance(raw_child, dict):
                raise ValueError("each child must be an object")
            child_id = _unique_id(
                raw_child.get("id"),
                _entry_seed(f"v2-child:{parent_id}", child_index, raw_child),
                used_ids,
            )
            child = new_entry(
                KIND_CHILD,
                raw_child.get("task", ""),
                raw_child["start"],
                raw_child["end"],
                parent_id=parent_id,
                entry_id=child_id,
                visible=raw_child.get("visible", True),
                progress_mode=raw_child.get("progress_mode", PROGRESS_PERCENT),
                progress_value=raw_child.get("progress_value", 0),
                progress_total=raw_child.get("progress_total", 100),
            )
            parent["children"].append(child)
        parents.append(parent)
    return {"version": SCHEMA_VERSION, "parents": parents}


def _deserialize_legacy(raw: dict) -> dict:
    entries = raw.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("legacy schedule entries must be a list")

    used_ids: set[str] = set()
    parents: list[dict] = []
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            continue
        try:
            entry_id = _unique_id(None, _entry_seed("legacy-parent", index, item), used_ids)
            parent = new_entry(
                KIND_PARENT,
                item.get("task", ""),
                item["start"],
                item["end"],
                entry_id=entry_id,
                visible=item.get("visible", True),
            )
        except (KeyError, TypeError, ValueError):
            continue
        parents.append(parent)
    return {"version": SCHEMA_VERSION, "parents": parents}


def deserialize_schedule(raw: dict) -> dict:
    """Normalize a version 2 schedule or migrate a legacy entries document."""

    if not isinstance(raw, dict):
        raise ValueError("schedule data must be an object")
    if raw.get("version") == SCHEMA_VERSION or "parents" in raw:
        return _deserialize_v2(raw)
    if "entries" in raw or not raw:
        return _deserialize_legacy(raw)
    raise ValueError("unsupported schedule format")


def _serialize_common(entry: dict, kind: str, parent_id: str | None) -> dict:
    start = _parse_date(entry["start"])
    end = _parse_date(entry["end"])
    if end < start:
        raise ValueError("end must be on or after start")
    mode, value, total = _normalize_progress(
        entry.get("progress_mode", PROGRESS_PERCENT),
        entry.get("progress_value", 0),
        entry.get("progress_total", 100),
    )
    return {
        "id": str(entry["id"]),
        "kind": kind,
        "parent_id": parent_id,
        "task": str(entry.get("task", "")),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "visible": bool(entry.get("visible", True)),
        "progress_mode": mode,
        "progress_value": value,
        "progress_total": total,
    }


def serialize_schedule(schedule: dict) -> dict:
    """Return a JSON-compatible version 2 document without mutating the model."""

    parents_raw = schedule.get("parents", [])
    if not isinstance(parents_raw, list):
        raise ValueError("schedule parents must be a list")

    parents: list[dict] = []
    for parent in parents_raw:
        serialized_parent = _serialize_common(parent, KIND_PARENT, None)
        serialized_parent["collapsed"] = bool(parent.get("collapsed", False))
        serialized_parent["children"] = [
            _serialize_common(child, KIND_CHILD, serialized_parent["id"])
            for child in parent.get("children", [])
        ]
        parents.append(serialized_parent)
    return {"version": SCHEMA_VERSION, "parents": parents}


def iter_all_entries(schedule: dict) -> Iterator[dict]:
    for parent in schedule.get("parents", []):
        yield parent
        yield from parent.get("children", [])


def visible_rows(schedule: dict) -> Iterator[dict]:
    """Yield rows shown in the table; collapse hides children, not the parent."""

    for parent in schedule.get("parents", []):
        yield parent
        if not parent.get("collapsed", False):
            yield from parent.get("children", [])


def find_entry(schedule: dict, entry_id: str) -> EntryLocation | None:
    target_id = str(entry_id)
    for parent_index, parent in enumerate(schedule.get("parents", [])):
        if str(parent.get("id")) == target_id:
            return EntryLocation(parent, parent, parent_index, None)
        for child_index, child in enumerate(parent.get("children", [])):
            if str(child.get("id")) == target_id:
                return EntryLocation(parent, child, parent_index, child_index)
    return None


def effective_visible(schedule: dict, entry_or_id: dict | str) -> bool:
    entry_id = entry_or_id.get("id") if isinstance(entry_or_id, dict) else entry_or_id
    location = find_entry(schedule, str(entry_id))
    if location is None:
        return False
    if location.is_parent:
        return bool(location.entry.get("visible", True))
    return bool(location.parent.get("visible", True)) and bool(location.entry.get("visible", True))


def _safe_number(value: object, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def progress_ratio(entry: dict) -> float:
    children = entry.get("children", [])
    if isinstance(children, list) and children:
        return sum(progress_ratio(child) for child in children) / len(children)

    value = _safe_number(entry.get("progress_value", 0), 0.0)
    if entry.get("progress_mode", PROGRESS_PERCENT) == PROGRESS_VALUE:
        total = _safe_number(entry.get("progress_total", 0), 0.0)
    else:
        total = 100.0
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, value / total))


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def progress_text(entry: dict) -> str:
    ratio = progress_ratio(entry)
    children = entry.get("children", [])
    if isinstance(children, list) and children:
        return f"{ratio:.0%}"

    percent = _format_number(round(ratio * 100, 2))
    if entry.get("progress_mode", PROGRESS_PERCENT) != PROGRESS_VALUE:
        return f"{percent}%"

    total = max(0.0, _safe_number(entry.get("progress_total", 0), 0.0))
    value = _safe_number(entry.get("progress_value", 0), 0.0)
    value = max(0.0, min(value, total))
    return f"{_format_number(value)} / {_format_number(total)} ({percent}%)"


def delay_days(entry: dict, current_date: date | datetime | str) -> int:
    """Return delay after the planned end date using the caller's JST date."""

    return max(0, (_parse_date(current_date) - _parse_date(entry["end"])).days)


def _move_delta(direction: int | str) -> int:
    if direction in (-1, "up"):
        return -1
    if direction in (1, "down"):
        return 1
    raise ValueError("direction must be -1/'up' or 1/'down'")


def move_entry(schedule: dict, entry_id: str, direction: int | str) -> bool:
    """Move an entry in place within its own parent or the parent list."""

    location = find_entry(schedule, entry_id)
    if location is None:
        return False
    delta = _move_delta(direction)
    if location.is_parent:
        siblings = schedule.get("parents", [])
        source_index = location.parent_index
    else:
        siblings = location.parent.get("children", [])
        source_index = location.child_index
    if source_index is None:
        return False
    target_index = source_index + delta
    if not 0 <= target_index < len(siblings):
        return False
    siblings[source_index], siblings[target_index] = siblings[target_index], siblings[source_index]
    return True


def remove_entry(schedule: dict, entry_id: str) -> list[dict]:
    """Remove an entry in place and return all removed entries in display order."""

    location = find_entry(schedule, entry_id)
    if location is None:
        return []
    if location.is_parent:
        parent = schedule.get("parents", []).pop(location.parent_index)
        return [parent, *parent.get("children", [])]

    child = location.parent.get("children", []).pop(location.child_index)
    return [child]

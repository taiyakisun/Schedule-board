from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import copy
import math
from typing import Iterator
from uuid import UUID, uuid4, uuid5


SCHEMA_VERSION = 3
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


def _parse_optional_date(value: date | datetime | str | None) -> date | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _parse_date(value)


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
    started: date | datetime | str | None = None,
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
        "started": _parse_optional_date(started),
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


def _normalize_settings(raw: object) -> dict:
    settings = raw if isinstance(raw, dict) else {}
    try:
        row_height = int(settings.get("row_height", 40))
    except (TypeError, ValueError):
        row_height = 40
    return {"row_height": max(30, min(72, row_height))}


def _normalize_todo_source(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    source = copy.deepcopy(raw)
    if "start" in source:
        source["start"] = _parse_date(source["start"]).isoformat()
    if "end" in source:
        source["end"] = _parse_date(source["end"]).isoformat()
    started = _parse_optional_date(source.get("started"))
    source["started"] = started.isoformat() if started is not None else None
    return source


def new_todo_entry(
    kind: str,
    task: str,
    deadline: date | datetime | str,
    *,
    parent_id: str | None = None,
    entry_id: str | None = None,
    notify: bool = True,
    last_notified_at: str | None = None,
    collapsed: bool = False,
    source: dict | None = None,
) -> dict:
    if kind not in (KIND_PARENT, KIND_CHILD):
        raise ValueError(f"unsupported todo kind: {kind}")
    if kind == KIND_CHILD and not parent_id:
        raise ValueError("a child todo requires parent_id")
    normalized = {
        "id": str(entry_id or uuid4()),
        "kind": kind,
        "parent_id": None if kind == KIND_PARENT else str(parent_id),
        "task": str(task),
        "deadline": _parse_date(deadline),
        "notify": bool(notify),
        "last_notified_at": str(last_notified_at) if last_notified_at else None,
        "source": _normalize_todo_source(source),
    }
    if kind == KIND_PARENT:
        normalized["collapsed"] = bool(collapsed)
        normalized["children"] = []
    return normalized


def _deserialize_todos(raw: object, used_ids: set[str]) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError("schedule todos must be a list")
    todos: list[dict] = []
    for parent_index, raw_parent in enumerate(raw):
        if not isinstance(raw_parent, dict):
            raise ValueError("each todo parent must be an object")
        parent_id = _unique_id(
            raw_parent.get("id"),
            f"todo-parent:{parent_index}:{raw_parent.get('task', '')}:{raw_parent.get('deadline', '')}",
            used_ids,
        )
        parent = new_todo_entry(
            KIND_PARENT,
            raw_parent.get("task", ""),
            raw_parent["deadline"],
            entry_id=parent_id,
            notify=raw_parent.get("notify", True),
            last_notified_at=raw_parent.get("last_notified_at"),
            collapsed=raw_parent.get("collapsed", False),
            source=raw_parent.get("source"),
        )
        children_raw = raw_parent.get("children", [])
        if not isinstance(children_raw, list):
            raise ValueError("todo parent children must be a list")
        for child_index, raw_child in enumerate(children_raw):
            if not isinstance(raw_child, dict):
                raise ValueError("each todo child must be an object")
            child_id = _unique_id(
                raw_child.get("id"),
                f"todo-child:{parent_id}:{child_index}:{raw_child.get('task', '')}:{raw_child.get('deadline', '')}",
                used_ids,
            )
            parent["children"].append(
                new_todo_entry(
                    KIND_CHILD,
                    raw_child.get("task", ""),
                    raw_child["deadline"],
                    parent_id=parent_id,
                    entry_id=child_id,
                    notify=raw_child.get("notify", True),
                    last_notified_at=raw_child.get("last_notified_at"),
                    source=raw_child.get("source"),
                )
            )
        todos.append(parent)
    return todos


def _serialize_todo(todo: dict) -> dict:
    kind = todo.get("kind", KIND_PARENT)
    parent_id = None if kind == KIND_PARENT else str(todo.get("parent_id"))
    serialized = {
        "id": str(todo["id"]),
        "kind": kind,
        "parent_id": parent_id,
        "task": str(todo.get("task", "")),
        "deadline": _parse_date(todo["deadline"]).isoformat(),
        "notify": bool(todo.get("notify", True)),
        "last_notified_at": (
            str(todo.get("last_notified_at"))
            if todo.get("last_notified_at")
            else None
        ),
        "source": _normalize_todo_source(todo.get("source")),
    }
    if kind == KIND_PARENT:
        serialized["collapsed"] = bool(todo.get("collapsed", False))
        serialized["children"] = [
            _serialize_todo(child) for child in todo.get("children", [])
        ]
    return serialized


def _deserialize_v2(raw: dict) -> dict:
    parents_raw = raw.get("parents")
    if not isinstance(parents_raw, list):
        raise ValueError("schedule requires a parents list")

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
            started=raw_parent.get("started"),
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
                started=raw_child.get("started"),
            )
            parent["children"].append(child)
        parents.append(parent)
    schedule = {"version": SCHEMA_VERSION, "parents": parents}
    if "todos" in raw:
        schedule["todos"] = _deserialize_todos(raw.get("todos"), used_ids)
    if "settings" in raw:
        schedule["settings"] = _normalize_settings(raw.get("settings"))
    return schedule


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
    """Normalize a version 2/3 schedule or migrate a legacy entries document."""

    if not isinstance(raw, dict):
        raise ValueError("schedule data must be an object")
    version = raw.get("version")
    if version in (2, SCHEMA_VERSION) or (version is None and "parents" in raw):
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
    started = _parse_optional_date(entry.get("started"))
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
        "started": started.isoformat() if started is not None else None,
    }


def serialize_schedule(schedule: dict) -> dict:
    """Return a JSON-compatible version 3 document without mutating the model."""

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
    serialized = {"version": SCHEMA_VERSION, "parents": parents}
    if "todos" in schedule:
        serialized["todos"] = [_serialize_todo(parent) for parent in schedule.get("todos", [])]
    if "settings" in schedule:
        serialized["settings"] = _normalize_settings(schedule.get("settings"))
    return serialized


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


def started_date_for_progress(
    started: date | datetime | str | None,
    progress_value: object,
    current_date: date | datetime | str,
) -> date | None:
    """Set the first started date when a concrete non-zero progress is saved."""

    existing = _parse_optional_date(started)
    if existing is not None:
        return existing
    value = _number(progress_value, "progress_value")
    return _parse_date(current_date) if value > 0 else None


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


def iter_all_todos(schedule: dict) -> Iterator[dict]:
    for parent in schedule.get("todos", []):
        yield parent
        yield from parent.get("children", [])


def visible_todos(schedule: dict) -> Iterator[dict]:
    for parent in schedule.get("todos", []):
        yield parent
        if not parent.get("collapsed", False):
            yield from parent.get("children", [])


def find_todo(schedule: dict, entry_id: str) -> EntryLocation | None:
    target_id = str(entry_id)
    for parent_index, parent in enumerate(schedule.get("todos", [])):
        if str(parent.get("id")) == target_id:
            return EntryLocation(parent, parent, parent_index, None)
        for child_index, child in enumerate(parent.get("children", [])):
            if str(child.get("id")) == target_id:
                return EntryLocation(parent, child, parent_index, child_index)
    return None


def todo_notification_due(
    todo: dict,
    current_datetime: datetime,
    interval: timedelta = timedelta(hours=1),
) -> bool:
    if not todo.get("notify", True):
        return False
    if _parse_date(todo["deadline"]) > current_datetime.date():
        return False
    last_text = todo.get("last_notified_at")
    if not last_text:
        return True
    try:
        last = datetime.fromisoformat(str(last_text))
    except ValueError:
        return True
    if current_datetime.tzinfo is not None and last.tzinfo is None:
        last = last.replace(tzinfo=current_datetime.tzinfo)
    if current_datetime.tzinfo is None and last.tzinfo is not None:
        current_datetime = current_datetime.replace(tzinfo=last.tzinfo)
    return current_datetime - last >= interval


def move_todo(schedule: dict, entry_id: str, direction: int | str) -> bool:
    location = find_todo(schedule, entry_id)
    if location is None:
        return False
    delta = _move_delta(direction)
    if location.is_parent:
        siblings = schedule.get("todos", [])
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


def remove_todo(schedule: dict, entry_id: str) -> list[dict]:
    location = find_todo(schedule, entry_id)
    if location is None:
        return []
    if location.is_parent:
        parent = schedule.get("todos", []).pop(location.parent_index)
        return [parent, *parent.get("children", [])]
    child = location.parent.get("children", []).pop(location.child_index)
    return [child]


def _entry_source(entry: dict) -> dict:
    return _serialize_common(
        entry,
        entry.get("kind", KIND_PARENT),
        entry.get("parent_id"),
    )


def _entry_to_todo(entry: dict, kind: str, parent_id: str | None = None) -> dict:
    todo = new_todo_entry(
        kind,
        entry.get("task", ""),
        entry["start"],
        parent_id=parent_id,
        entry_id=entry.get("id"),
        notify=True,
        collapsed=entry.get("collapsed", False),
        source=_entry_source(entry),
    )
    if kind == KIND_PARENT:
        for child in entry.get("children", []):
            todo["children"].append(_entry_to_todo(child, KIND_CHILD, todo["id"]))
    return todo


def move_schedule_group_to_todos(schedule: dict, entry_id: str) -> dict | None:
    """Move the selected entry's entire parent group to TODOs."""

    location = find_entry(schedule, entry_id)
    if location is None:
        return None
    parent = schedule.get("parents", [])[location.parent_index]
    todo = _entry_to_todo(parent, KIND_PARENT)
    schedule.get("parents", []).pop(location.parent_index)
    schedule.setdefault("todos", []).append(todo)
    return todo


def _todo_to_entry(
    todo: dict,
    kind: str,
    parent_id: str | None = None,
) -> dict:
    source = todo.get("source") if isinstance(todo.get("source"), dict) else {}
    deadline = _parse_date(todo["deadline"])
    try:
        source_start = _parse_date(source.get("start", deadline))
        source_end = _parse_date(source.get("end", source_start))
        duration = max(0, (source_end - source_start).days)
    except (TypeError, ValueError):
        duration = 0
    if duration > (date.max - deadline).days:
        raise ValueError("期限を開始日にすると終了日が9999-12-31を超えます")
    entry = new_entry(
        kind,
        todo.get("task", ""),
        deadline,
        date.fromordinal(deadline.toordinal() + duration),
        parent_id=parent_id,
        entry_id=todo.get("id"),
        visible=source.get("visible", True),
        progress_mode=source.get("progress_mode", PROGRESS_PERCENT),
        progress_value=source.get("progress_value", 0),
        progress_total=source.get("progress_total", 100),
        started=source.get("started"),
        collapsed=todo.get("collapsed", False),
    )
    if kind == KIND_PARENT:
        for child_todo in todo.get("children", []):
            entry["children"].append(
                _todo_to_entry(child_todo, KIND_CHILD, entry["id"])
            )
    return entry


def move_todo_group_to_schedule(schedule: dict, entry_id: str) -> dict | None:
    """Move the selected TODO's entire parent group back to schedules."""

    location = find_todo(schedule, entry_id)
    if location is None:
        return None
    todo = schedule.get("todos", [])[location.parent_index]
    entry = _todo_to_entry(todo, KIND_PARENT)
    schedule.get("todos", []).pop(location.parent_index)
    schedule.setdefault("parents", []).append(entry)
    return entry

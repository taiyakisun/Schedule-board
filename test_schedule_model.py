import unittest
from datetime import date, datetime, timedelta, timezone

from schedule_model import (
    KIND_CHILD,
    KIND_PARENT,
    PROGRESS_PERCENT,
    PROGRESS_VALUE,
    delay_days,
    deserialize_schedule,
    effective_visible,
    find_entry,
    find_todo,
    iter_all_todos,
    iter_all_entries,
    move_entry,
    move_schedule_group_to_todos,
    move_todo_group_to_schedule,
    new_entry,
    new_todo_entry,
    progress_ratio,
    progress_text,
    remove_entry,
    serialize_schedule,
    started_date_for_progress,
    todo_notification_due,
    visible_rows,
)


class ScheduleModelTests(unittest.TestCase):
    def make_parent(self, entry_id: str, task: str = "Parent") -> dict:
        return new_entry(
            KIND_PARENT,
            task,
            "2026-07-01",
            "2026-07-10",
            entry_id=entry_id,
        )

    def make_child(self, entry_id: str, parent_id: str, task: str = "Child") -> dict:
        return new_entry(
            KIND_CHILD,
            task,
            "2026-07-02",
            "2026-07-05",
            parent_id=parent_id,
            entry_id=entry_id,
        )

    def test_legacy_entries_migrate_to_childless_parents_with_stable_ids(self) -> None:
        legacy = {
            "entries": [
                {
                    "task": "Legacy A",
                    "start": "2026-05-01",
                    "end": "2026-05-03",
                    "visible": False,
                },
                {
                    "task": "Legacy B",
                    "start": "2026-05-04",
                    "end": "2026-05-04",
                },
            ]
        }

        first = deserialize_schedule(legacy)
        second = deserialize_schedule(legacy)

        self.assertEqual(first["version"], 3)
        self.assertEqual([entry["id"] for entry in first["parents"]], [entry["id"] for entry in second["parents"]])
        self.assertEqual([entry["kind"] for entry in first["parents"]], [KIND_PARENT, KIND_PARENT])
        self.assertEqual([entry["parent_id"] for entry in first["parents"]], [None, None])
        self.assertEqual(first["parents"][0]["children"], [])
        self.assertFalse(first["parents"][0]["visible"])
        self.assertEqual(first["parents"][0]["progress_mode"], PROGRESS_PERCENT)
        self.assertEqual(first["parents"][0]["progress_value"], 0)
        self.assertEqual(first["parents"][0]["progress_total"], 100)

    def test_version_2_round_trip_preserves_nested_entries_and_repairs_parent_id(self) -> None:
        raw = {
            "version": 2,
            "parents": [
                {
                    "id": "parent-1",
                    "kind": KIND_PARENT,
                    "parent_id": None,
                    "task": "Release",
                    "start": "2026-07-01",
                    "end": "2026-07-31",
                    "visible": True,
                    "progress_mode": PROGRESS_PERCENT,
                    "progress_value": 25,
                    "progress_total": 100,
                    "collapsed": True,
                    "children": [
                        {
                            "id": "child-1",
                            "kind": KIND_CHILD,
                            "parent_id": "stale-parent-id",
                            "task": "Implementation",
                            "start": "2026-07-02",
                            "end": "2026-07-20",
                            "visible": False,
                            "progress_mode": PROGRESS_VALUE,
                            "progress_value": 176,
                            "progress_total": 352,
                        }
                    ],
                }
            ],
        }

        model = deserialize_schedule(raw)
        child = model["parents"][0]["children"][0]
        self.assertEqual(child["parent_id"], "parent-1")
        self.assertIsInstance(child["start"], date)

        serialized = serialize_schedule(model)
        self.assertEqual(serialized["parents"][0]["children"][0]["parent_id"], "parent-1")
        self.assertEqual(serialized["parents"][0]["children"][0]["start"], "2026-07-02")
        self.assertEqual(serialize_schedule(deserialize_schedule(serialized)), serialized)

    def test_missing_or_duplicate_version_2_ids_are_repaired_stably(self) -> None:
        raw = {
            "version": 2,
            "parents": [
                {
                    "id": "duplicate",
                    "task": "Parent A",
                    "start": "2026-07-01",
                    "end": "2026-07-02",
                    "children": [
                        {
                            "id": "duplicate",
                            "task": "Child A",
                            "start": "2026-07-01",
                            "end": "2026-07-01",
                        }
                    ],
                },
                {
                    "task": "Parent B",
                    "start": "2026-07-03",
                    "end": "2026-07-04",
                    "children": [],
                },
            ],
        }

        first = deserialize_schedule(raw)
        second = deserialize_schedule(raw)
        first_ids = [entry["id"] for entry in iter_all_entries(first)]
        second_ids = [entry["id"] for entry in iter_all_entries(second)]

        self.assertEqual(first_ids, second_ids)
        self.assertEqual(len(first_ids), len(set(first_ids)))
        self.assertEqual(first["parents"][0]["children"][0]["parent_id"], "duplicate")

    def test_all_entries_and_visible_rows_respect_collapse(self) -> None:
        parent = self.make_parent("parent-1")
        child_a = self.make_child("child-a", parent["id"], "A")
        child_b = self.make_child("child-b", parent["id"], "B")
        parent["children"] = [child_a, child_b]
        schedule = {"version": 2, "parents": [parent]}

        self.assertEqual([entry["id"] for entry in iter_all_entries(schedule)], ["parent-1", "child-a", "child-b"])
        self.assertEqual([entry["id"] for entry in visible_rows(schedule)], ["parent-1", "child-a", "child-b"])

        parent["collapsed"] = True
        self.assertEqual([entry["id"] for entry in iter_all_entries(schedule)], ["parent-1", "child-a", "child-b"])
        self.assertEqual([entry["id"] for entry in visible_rows(schedule)], ["parent-1"])

    def test_effective_visibility_combines_parent_and_child_flags(self) -> None:
        parent = self.make_parent("parent-1")
        child = self.make_child("child-1", parent["id"])
        parent["children"].append(child)
        schedule = {"version": 2, "parents": [parent]}

        self.assertTrue(effective_visible(schedule, parent))
        self.assertTrue(effective_visible(schedule, child))

        child["visible"] = False
        self.assertTrue(effective_visible(schedule, parent))
        self.assertFalse(effective_visible(schedule, child))

        child["visible"] = True
        parent["visible"] = False
        self.assertFalse(effective_visible(schedule, parent["id"]))
        self.assertFalse(effective_visible(schedule, child["id"]))
        self.assertTrue(child["visible"], "parent visibility must not overwrite the child's own option")
        self.assertFalse(effective_visible(schedule, "missing"))

    def test_find_entry_reports_parent_and_child_indexes(self) -> None:
        parent = self.make_parent("parent-1")
        parent["children"].append(self.make_child("child-1", parent["id"]))
        schedule = {"version": 2, "parents": [parent]}

        parent_location = find_entry(schedule, "parent-1")
        child_location = find_entry(schedule, "child-1")
        self.assertIsNotNone(parent_location)
        self.assertIsNotNone(child_location)
        self.assertTrue(parent_location.is_parent)
        self.assertEqual(parent_location.parent_index, 0)
        self.assertEqual(child_location.parent_index, 0)
        self.assertEqual(child_location.child_index, 0)

    def test_move_stays_in_the_same_hierarchy_level(self) -> None:
        parent_a = self.make_parent("parent-a", "A")
        child_a1 = self.make_child("child-a1", parent_a["id"], "A1")
        child_a2 = self.make_child("child-a2", parent_a["id"], "A2")
        parent_a["children"] = [child_a1, child_a2]
        parent_b = self.make_parent("parent-b", "B")
        child_b1 = self.make_child("child-b1", parent_b["id"], "B1")
        parent_b["children"] = [child_b1]
        schedule = {"version": 2, "parents": [parent_a, parent_b]}

        self.assertTrue(move_entry(schedule, "child-a1", "down"))
        self.assertEqual([child["id"] for child in parent_a["children"]], ["child-a2", "child-a1"])
        self.assertFalse(move_entry(schedule, "child-a1", "down"))
        self.assertEqual([child["id"] for child in parent_b["children"]], ["child-b1"])

        self.assertTrue(move_entry(schedule, "parent-b", "up"))
        self.assertEqual([parent["id"] for parent in schedule["parents"]], ["parent-b", "parent-a"])
        self.assertEqual([child["id"] for child in schedule["parents"][0]["children"]], ["child-b1"])
        self.assertFalse(move_entry(schedule, "parent-b", "up"))

    def test_remove_child_and_parent_cascade(self) -> None:
        parent_a = self.make_parent("parent-a")
        parent_a["children"] = [
            self.make_child("child-a1", parent_a["id"]),
            self.make_child("child-a2", parent_a["id"]),
        ]
        parent_b = self.make_parent("parent-b")
        parent_b["children"] = [self.make_child("child-b1", parent_b["id"])]
        schedule = {"version": 2, "parents": [parent_a, parent_b]}

        removed_child = remove_entry(schedule, "child-a1")
        self.assertEqual([entry["id"] for entry in removed_child], ["child-a1"])
        self.assertEqual([child["id"] for child in parent_a["children"]], ["child-a2"])

        removed_parent = remove_entry(schedule, "parent-b")
        self.assertEqual([entry["id"] for entry in removed_parent], ["parent-b", "child-b1"])
        self.assertEqual([parent["id"] for parent in schedule["parents"]], ["parent-a"])
        self.assertEqual(remove_entry(schedule, "missing"), [])

    def test_progress_boundaries_and_text(self) -> None:
        below = new_entry(KIND_PARENT, "Below", "2026-07-01", "2026-07-01", progress_value=-1)
        above = new_entry(KIND_PARENT, "Above", "2026-07-01", "2026-07-01", progress_value=120)
        numeric = new_entry(
            KIND_PARENT,
            "Numeric",
            "2026-07-01",
            "2026-07-01",
            progress_mode=PROGRESS_VALUE,
            progress_value=176,
            progress_total=352,
        )

        self.assertEqual(below["progress_value"], 0)
        self.assertEqual(progress_ratio(below), 0.0)
        self.assertEqual(progress_text(below), "0%")
        self.assertEqual(above["progress_value"], 100)
        self.assertEqual(progress_ratio(above), 1.0)
        self.assertEqual(progress_text(above), "100%")
        self.assertEqual(progress_ratio(numeric), 0.5)
        self.assertEqual(progress_text(numeric), "176 / 352 (50%)")

        numeric["progress_value"] = 999
        self.assertEqual(progress_ratio(numeric), 1.0)
        self.assertEqual(progress_text(numeric), "352 / 352 (100%)")
        with self.assertRaises(ValueError):
            new_entry(
                KIND_PARENT,
                "Invalid total",
                "2026-07-01",
                "2026-07-01",
                progress_mode=PROGRESS_VALUE,
                progress_total=0,
            )

    def test_parent_progress_uses_average_of_children_when_present(self) -> None:
        parent = new_entry(
            KIND_PARENT,
            "Parent",
            "2026-07-01",
            "2026-07-10",
            progress_mode=PROGRESS_VALUE,
            progress_value=9,
            progress_total=10,
        )
        parent["children"] = [
            new_entry(
                KIND_CHILD,
                "Complete",
                "2026-07-01",
                "2026-07-02",
                parent_id=parent["id"],
                progress_value=100,
            ),
            new_entry(
                KIND_CHILD,
                "Not started A",
                "2026-07-03",
                "2026-07-04",
                parent_id=parent["id"],
                progress_mode=PROGRESS_VALUE,
                progress_value=0,
                progress_total=4,
            ),
            new_entry(
                KIND_CHILD,
                "Not started B",
                "2026-07-05",
                "2026-07-06",
                parent_id=parent["id"],
                progress_value=0,
            ),
        ]

        self.assertAlmostEqual(progress_ratio(parent), 1 / 3)
        self.assertEqual(progress_text(parent), "33%")

        parent["children"].clear()
        self.assertEqual(progress_ratio(parent), 0.9)
        self.assertEqual(progress_text(parent), "9 / 10 (90%)")

    def test_started_date_round_trip_and_automatic_first_progress(self) -> None:
        parent = new_entry(
            KIND_PARENT,
            "Started",
            "2026-07-01",
            "2026-07-03",
            started="2026-07-02",
        )
        serialized = serialize_schedule({"version": 3, "parents": [parent]})
        self.assertEqual(serialized["parents"][0]["started"], "2026-07-02")
        restored = deserialize_schedule(serialized)["parents"][0]
        self.assertEqual(restored["started"], date(2026, 7, 2))
        self.assertIsNone(started_date_for_progress(None, 0, "2026-07-14"))
        self.assertEqual(
            started_date_for_progress(None, 1, "2026-07-14"),
            date(2026, 7, 14),
        )
        self.assertEqual(
            started_date_for_progress("2026-07-02", 50, "2026-07-14"),
            date(2026, 7, 2),
        )

    def test_parent_group_moves_to_todo_and_back_without_losing_hierarchy(self) -> None:
        parent = self.make_parent("parent-1")
        parent["started"] = date(2026, 7, 2)
        parent["collapsed"] = True
        child = self.make_child("child-1", "parent-1")
        child["progress_value"] = 40
        parent["children"].append(child)
        schedule = {
            "version": 3,
            "parents": [parent],
            "todos": [],
            "settings": {"row_height": 34},
        }

        todo = move_schedule_group_to_todos(schedule, "child-1")

        self.assertEqual(schedule["parents"], [])
        self.assertEqual(todo["id"], "parent-1")
        self.assertEqual(todo["children"][0]["id"], "child-1")
        self.assertTrue(todo["collapsed"])
        self.assertFalse(any(item["notify"] for item in iter_all_todos(schedule)))
        todo["deadline"] = date(2026, 7, 10)
        serialized = serialize_schedule(schedule)
        restored_schedule = deserialize_schedule(serialized)
        restored = move_todo_group_to_schedule(restored_schedule, "child-1")

        self.assertEqual(restored["start"], date(2026, 7, 10))
        self.assertEqual(restored["end"], date(2026, 7, 19))
        self.assertEqual(restored["started"], date(2026, 7, 2))
        self.assertTrue(restored["collapsed"])
        self.assertEqual(restored["children"][0]["progress_value"], 40)
        self.assertIsNone(find_todo(restored_schedule, "parent-1"))
        self.assertEqual(restored_schedule["settings"]["row_height"], 34)

    def test_manual_todo_returns_as_one_day_schedule(self) -> None:
        todo = new_todo_entry(
            KIND_PARENT,
            "Manual",
            "2026-08-01",
            entry_id="todo-1",
        )
        self.assertFalse(todo["notify"])
        schedule = {"version": 3, "parents": [], "todos": [todo]}
        restored = move_todo_group_to_schedule(schedule, "todo-1")
        self.assertEqual(restored["start"], date(2026, 8, 1))
        self.assertEqual(restored["end"], date(2026, 8, 1))
        self.assertEqual(restored["progress_value"], 0)
        self.assertIsNone(restored["started"])

    def test_explicit_todo_notification_on_survives_round_trip(self) -> None:
        todo = new_todo_entry(
            KIND_PARENT,
            "Notify",
            "2026-08-01",
            entry_id="todo-notify",
            notify=True,
        )
        serialized = serialize_schedule(
            {"version": 3, "parents": [], "todos": [todo]}
        )
        restored = deserialize_schedule(serialized)
        self.assertTrue(restored["todos"][0]["notify"])

    def test_rejects_unknown_future_schedule_version(self) -> None:
        with self.assertRaises(ValueError):
            deserialize_schedule({"version": 99, "parents": []})

    def test_todo_notification_due_respects_deadline_switch_and_hour_interval(self) -> None:
        now = datetime(2026, 7, 20, 10, 0, tzinfo=timezone(timedelta(hours=9)))
        todo = new_todo_entry(KIND_PARENT, "Due", "2026-07-20", notify=True)
        self.assertTrue(todo_notification_due(todo, now))
        todo["last_notified_at"] = "2026-07-20T09:01:00+09:00"
        self.assertFalse(todo_notification_due(todo, now))
        todo["last_notified_at"] = "2026-07-20T09:00:00+09:00"
        self.assertTrue(todo_notification_due(todo, now))
        todo["notify"] = False
        self.assertFalse(todo_notification_due(todo, now))
        todo["notify"] = True
        todo["deadline"] = date(2026, 7, 21)
        self.assertFalse(todo_notification_due(todo, now))

    def test_delay_boundaries_use_the_supplied_calendar_date(self) -> None:
        entry = self.make_parent("parent-1")

        self.assertEqual(delay_days(entry, date(2026, 7, 9)), 0)
        self.assertEqual(delay_days(entry, date(2026, 7, 10)), 0)
        self.assertEqual(delay_days(entry, date(2026, 7, 11)), 1)
        self.assertEqual(delay_days(entry, datetime(2026, 7, 15, 23, 59)), 5)
        self.assertEqual(delay_days(entry, "2026-07-20"), 10)


if __name__ == "__main__":
    unittest.main()

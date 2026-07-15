import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

import sch_gantt_main as app_module
from schedule_model import KIND_CHILD, KIND_PARENT, new_entry, progress_ratio, progress_text


class ScheduleAppLogicTests(unittest.TestCase):
    def make_app(self, parents: list[dict] | None = None) -> app_module.ScheduleApp:
        app = app_module.ScheduleApp.__new__(app_module.ScheduleApp)
        app.schedule = {"version": 2, "parents": parents or []}
        app.entries = app.schedule["parents"]
        app.selected_id = None
        app.current_jst_date = app_module.date(2026, 7, 15)
        app.row_widgets = []
        app._rebuild_rows = Mock()
        return app

    def make_hierarchy(self) -> tuple[dict, dict, dict]:
        parent = new_entry(
            KIND_PARENT,
            "Parent",
            "2026-07-01",
            "2026-07-31",
            entry_id="parent-1",
        )
        child_a = new_entry(
            KIND_CHILD,
            "Child A",
            "2026-07-02",
            "2026-07-10",
            parent_id=parent["id"],
            entry_id="child-a",
        )
        child_b = new_entry(
            KIND_CHILD,
            "Child B",
            "2026-07-11",
            "2026-07-20",
            parent_id=parent["id"],
            entry_id="child-b",
        )
        parent["children"] = [child_a, child_b]
        return parent, child_a, child_b

    def test_parent_delete_cancel_then_confirm_cascades(self) -> None:
        parent, child_a, child_b = self.make_hierarchy()
        app = self.make_app([parent])
        app.selected_id = parent["id"]

        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "schedules.json"
            with (
                patch.object(app_module, "DATA_FILE", str(data_file)),
                patch.object(app_module.messagebox, "askyesno", return_value=False) as ask,
            ):
                app._on_delete()

            self.assertEqual([entry["id"] for entry in app.entries], [parent["id"]])
            self.assertEqual([entry["id"] for entry in parent["children"]], [child_a["id"], child_b["id"]])
            self.assertFalse(data_file.exists())
            app._rebuild_rows.assert_not_called()
            self.assertIn("子タスク2件", ask.call_args.args[1])

            with (
                patch.object(app_module, "DATA_FILE", str(data_file)),
                patch.object(app_module.messagebox, "askyesno", return_value=True),
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                app._on_delete()

            self.assertEqual(app.entries, [])
            self.assertIsNone(app.selected_id)
            self.assertEqual(json.loads(data_file.read_text(encoding="utf-8")), {"version": 2, "parents": []})
            app._rebuild_rows.assert_called_once_with()
            showerror.assert_not_called()

    def test_excel_export_action_writes_compact_tree_columns(self) -> None:
        parent, child_a, child_b = self.make_hierarchy()
        app = self.make_app([parent])

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "gantt.xlsx"
            with (
                patch.object(app_module.filedialog, "asksaveasfilename", return_value=str(output)),
                patch.object(app_module.messagebox, "showinfo") as showinfo,
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                app._on_export_excel()

            with zipfile.ZipFile(output) as archive:
                sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("タスク", sheet_xml)
            self.assertNotIn("表示状態", sheet_xml)
            self.assertIn("▾ Parent", sheet_xml)
            self.assertIn("├─ Child A", sheet_xml)
            self.assertIn("└─ Child B", sheet_xml)
            self.assertEqual(sheet_xml.count("Parent"), 1)
            showinfo.assert_called_once()
            showerror.assert_not_called()

    def test_completing_parent_logs_parent_and_all_children_before_removal(self) -> None:
        parent, child_a, child_b = self.make_hierarchy()
        app = self.make_app([parent])

        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "schedules.json"
            log_file = Path(temp_dir) / "completed_tasks.jsonl"
            with (
                patch.object(app_module, "DATA_FILE", str(data_file)),
                patch.object(app_module, "COMPLETE_LOG_FILE", str(log_file)),
                patch.object(app_module.messagebox, "askyesno", return_value=True),
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                app._on_complete(parent["id"])

            records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(
                [record[app_module.LOG_FIELD_ID] for record in records],
                [parent["id"], child_a["id"], child_b["id"]],
            )
            self.assertTrue(all(record[app_module.LOG_FIELD_COMPLETED] is True for record in records))
            self.assertEqual(app.entries, [])
            self.assertEqual(json.loads(data_file.read_text(encoding="utf-8")), {"version": 2, "parents": []})
            app._rebuild_rows.assert_called_once_with()
            showerror.assert_not_called()

    def test_completing_child_logs_and_removes_only_that_child(self) -> None:
        parent, child_a, child_b = self.make_hierarchy()
        app = self.make_app([parent])

        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "schedules.json"
            log_file = Path(temp_dir) / "completed_tasks.jsonl"
            with (
                patch.object(app_module, "DATA_FILE", str(data_file)),
                patch.object(app_module, "COMPLETE_LOG_FILE", str(log_file)),
                patch.object(app_module.messagebox, "askyesno", return_value=True),
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                app._on_complete(child_a["id"])

            records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([record[app_module.LOG_FIELD_ID] for record in records], [child_a["id"]])
            self.assertEqual([entry["id"] for entry in app.entries], [parent["id"]])
            self.assertEqual([entry["id"] for entry in parent["children"]], [child_b["id"]])
            self.assertEqual(app.selected_id, parent["id"])
            saved = json.loads(data_file.read_text(encoding="utf-8"))
            self.assertEqual([entry["id"] for entry in saved["parents"][0]["children"]], [child_b["id"]])
            showerror.assert_not_called()

    def test_hiding_parent_preserves_child_option_but_makes_it_effectively_hidden(self) -> None:
        parent, child_a, _child_b = self.make_hierarchy()
        app = self.make_app([parent])
        app._save = Mock()

        self.assertTrue(child_a["visible"])
        self.assertTrue(app._effective_visible(child_a, parent))

        app._toggle_visibility(parent["id"])

        self.assertFalse(parent["visible"])
        self.assertTrue(child_a["visible"])
        self.assertFalse(app._effective_visible(child_a, parent))
        self.assertEqual(app._visibility_text(child_a, parent), app_module.PARENT_HIDDEN_TEXT)
        app._save.assert_called_once_with()
        app._rebuild_rows.assert_called_once_with()

    def test_loads_legacy_v1_and_saves_version_2(self) -> None:
        legacy = {
            "entries": [
                {
                    "task": "Legacy task",
                    "start": "2026-05-01",
                    "end": "2026-05-03",
                    "visible": False,
                }
            ]
        }
        app = self.make_app()

        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "schedules.json"
            data_file.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8", newline="\n")
            with (
                patch.object(app_module, "DATA_FILE", str(data_file)),
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                app._load()
                app._save()

            saved = json.loads(data_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["version"], 2)
            self.assertNotIn("entries", saved)
            self.assertEqual(len(saved["parents"]), 1)
            self.assertEqual(saved["parents"][0]["task"], "Legacy task")
            self.assertEqual(saved["parents"][0]["kind"], KIND_PARENT)
            self.assertEqual(saved["parents"][0]["children"], [])
            self.assertFalse(saved["parents"][0]["visible"])
            showerror.assert_not_called()

    def test_progress_100_active_entry_still_displays_delay_after_end(self) -> None:
        parent = new_entry(
            KIND_PARENT,
            "Finished progress but not completed",
            "2026-07-01",
            "2026-07-14",
            entry_id="parent-1",
            progress_value=100,
        )
        app = self.make_app([parent])
        delay_label = Mock()
        app.row_widgets = [SimpleNamespace(entry_id=parent["id"], delay_label=delay_label)]

        self.assertEqual(progress_ratio(parent), 1.0)
        self.assertEqual(app._delay_days(parent), 1)

        app._refresh_delay_labels()

        delay_label.configure.assert_called_once_with(text="1日", fg="#c62828")

    def test_delete_rolls_back_when_schedule_save_fails(self) -> None:
        parent, _child_a, _child_b = self.make_hierarchy()
        app = self.make_app([parent])
        app.selected_id = parent["id"]

        with tempfile.TemporaryDirectory() as temp_dir:
            unavailable = Path(temp_dir) / "missing" / "schedules.json"
            with (
                patch.object(app_module, "DATA_FILE", str(unavailable)),
                patch.object(app_module.messagebox, "askyesno", return_value=True),
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                app._on_delete()

        self.assertEqual([entry["id"] for entry in app.entries], [parent["id"]])
        self.assertEqual(app.selected_id, parent["id"])
        showerror.assert_called_once()

    def test_completion_rolls_back_schedule_when_log_write_fails(self) -> None:
        parent, child_a, child_b = self.make_hierarchy()
        app = self.make_app([parent])

        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "schedules.json"
            unavailable_log = Path(temp_dir) / "missing" / "completed_tasks.jsonl"
            with (
                patch.object(app_module, "DATA_FILE", str(data_file)),
                patch.object(app_module, "COMPLETE_LOG_FILE", str(unavailable_log)),
                patch.object(app_module.messagebox, "askyesno", return_value=True),
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                app._on_complete(parent["id"])

            saved = json.loads(data_file.read_text(encoding="utf-8"))

        self.assertEqual([entry["id"] for entry in app.entries], [parent["id"]])
        self.assertEqual(
            [entry["id"] for entry in app.entries[0]["children"]],
            [child_a["id"], child_b["id"]],
        )
        self.assertEqual(saved["parents"][0]["id"], parent["id"])
        showerror.assert_called_once()

    def test_failed_v2_load_blocks_overwrite_and_preserves_current_model(self) -> None:
        parent, _child_a, _child_b = self.make_hierarchy()
        app = self.make_app([parent])

        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "schedules.json"
            original = '{"version": 2, "parents": "broken"}'
            data_file.write_text(original, encoding="utf-8", newline="\n")
            with (
                patch.object(app_module, "DATA_FILE", str(data_file)),
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                app._load()
                saved = app._save()

            protected = data_file.read_text(encoding="utf-8")

        self.assertFalse(saved)
        self.assertTrue(app.load_failed)
        self.assertEqual([entry["id"] for entry in app.entries], [parent["id"]])
        self.assertEqual(protected, original)
        self.assertEqual(showerror.call_count, 2)

    def test_precision_and_maximum_date_scale_are_preserved(self) -> None:
        self.assertEqual(app_module.number_text(1.234567890123), "1.234567890123")
        app = self.make_app()
        app.scale_canvas = Mock()
        app.scale_canvas.winfo_width.return_value = 500
        app.scale_canvas.winfo_height.return_value = 54
        app.scale_canvas.create_text.return_value = 1
        app.scale_canvas.bbox.return_value = None
        app.today_label_screen_x = None
        app.current_jst_date = app_module.date(2026, 7, 15)
        app._visible_range = Mock(
            return_value=(app_module.date(9999, 12, 31), app_module.date(9999, 12, 31))
        )
        app._redraw_all_gantt = Mock()

        app._redraw_scale()

        app._redraw_all_gantt.assert_called_once_with()

    def test_task_frame_height_is_kept_when_size_propagation_is_disabled(self) -> None:
        app = self.make_app()
        app.header = Mock()
        app.task_column_width = 280
        app.progress_column_width = 150
        app.delay_column_width = 76
        app.complete_column_width = 66
        app.row_content_height = 30
        task_frame = Mock()
        row = Mock()
        app.row_widgets = [SimpleNamespace(container=row, task_frame=task_frame)]

        app._apply_column_width()

        task_frame.configure.assert_called_once_with(
            width=app.task_column_width,
            height=app.row_content_height,
        )
        task_frame.grid_propagate.assert_called_once_with(False)

    def test_progress_column_width_tracks_visible_text_length(self) -> None:
        short = new_entry(
            KIND_PARENT,
            "Short",
            "2026-07-01",
            "2026-07-02",
            progress_value=0,
        )
        app = self.make_app([short])
        app.task_font = Mock()
        app.task_font.measure.side_effect = lambda text: len(text) * 10

        app._update_progress_column_width()

        self.assertEqual(app.progress_column_width, app_module.PROGRESS_COLUMN_MIN_WIDTH)

        numeric = new_entry(
            KIND_CHILD,
            "Numeric",
            "2026-07-01",
            "2026-07-02",
            parent_id=short["id"],
            progress_mode="value",
            progress_value=176,
            progress_total=352,
        )
        short["children"].append(numeric)
        app._update_progress_column_width()

        expected = min(
            app_module.PROGRESS_COLUMN_MAX_WIDTH,
            len(progress_text(numeric)) * 10 + app_module.PROGRESS_COLUMN_PADDING,
        )
        self.assertEqual(app.progress_column_width, expected)


if __name__ == "__main__":
    unittest.main()

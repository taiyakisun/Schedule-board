import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch
import zipfile

import sch_gantt_main as app_module
from schedule_model import KIND_CHILD, KIND_PARENT, new_entry, progress_ratio, progress_text


class ApplicationResourceTests(unittest.TestCase):
    def test_windows_notification_is_safely_disabled_on_other_platforms(self) -> None:
        with patch.object(app_module.sys, "platform", "linux"):
            self.assertFalse(app_module.show_windows_notification(Mock(), "title", "message"))

    def test_windows_notification_uses_notification_area_api(self) -> None:
        shell_notify = Mock(return_value=True)
        user32 = SimpleNamespace(
            SendMessageW=Mock(return_value=123),
            LoadIconW=Mock(return_value=456),
        )
        native = SimpleNamespace(
            shell32=SimpleNamespace(Shell_NotifyIconW=shell_notify),
            user32=user32,
        )
        root = Mock()
        root.winfo_id.return_value = 99
        with (
            patch.object(app_module.sys, "platform", "win32"),
            patch.object(app_module.ctypes, "windll", native),
        ):
            self.assertTrue(
                app_module.show_windows_notification(root, "期限", "TODOがあります")
            )

        self.assertEqual(shell_notify.call_args_list[0].args[0], 0)
        self.assertEqual(shell_notify.call_args_list[1].args[0], 4)
        root.after.assert_called_once()
        root.after.call_args.args[1]()
        self.assertEqual(shell_notify.call_args_list[2].args[0], 2)

    def test_application_directory_uses_executable_when_frozen(self) -> None:
        executable = os.path.join("C:\\", "apps", "ScheduleBoard", "ScheduleBoard.exe")
        with (
            patch.object(app_module.sys, "frozen", True, create=True),
            patch.object(app_module.sys, "executable", executable),
        ):
            self.assertEqual(
                app_module.application_directory(),
                os.path.dirname(executable),
            )

    def test_resource_path_uses_pyinstaller_bundle_directory(self) -> None:
        bundle_dir = os.path.join("C:\\", "bundle")
        with patch.object(app_module.sys, "_MEIPASS", bundle_dir, create=True):
            self.assertEqual(
                app_module.resource_path("assets", "sch_gantt_icon.png"),
                os.path.join(bundle_dir, "assets", "sch_gantt_icon.png"),
            )

    def test_configure_application_icon_sets_png_and_windows_ico(self) -> None:
        root = Mock()
        icon_image = Mock()
        with (
            patch.object(app_module.tk, "PhotoImage", return_value=icon_image),
            patch.object(app_module, "resource_path", side_effect=lambda *parts: os.path.join(*parts)),
            patch.object(app_module.os, "name", "nt"),
        ):
            app_module.configure_application_icon(root)

        self.assertEqual(
            root.iconphoto.call_args_list,
            [
                call(False, icon_image),
                call(True, icon_image),
            ],
        )
        icon_path = os.path.join("assets", "sch_gantt_icon.ico")
        self.assertEqual(
            root.iconbitmap.call_args_list,
            [
                call(icon_path),
                call(default=icon_path),
            ],
        )
        self.assertIs(root._sch_gantt_icon_image, icon_image)


class ScheduleAppLogicTests(unittest.TestCase):
    def make_app(self, parents: list[dict] | None = None) -> app_module.ScheduleApp:
        app = app_module.ScheduleApp.__new__(app_module.ScheduleApp)
        app.schedule = {"version": 2, "parents": parents or []}
        app.entries = app.schedule["parents"]
        app.selected_id = None
        app.current_jst_date = app_module.date(2026, 7, 15)
        app.row_widgets = []
        app.header_font = Mock()
        app.small_font = Mock()
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
            self.assertEqual(json.loads(data_file.read_text(encoding="utf-8")), {"version": 3, "parents": []})
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
            self.assertEqual(json.loads(data_file.read_text(encoding="utf-8")), {"version": 3, "parents": []})
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

    def test_loads_legacy_v1_and_saves_version_3(self) -> None:
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
            self.assertEqual(saved["version"], 3)
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

        delay_label.configure.assert_called_once_with(
            text="1日遅延",
            fg=app_module.COLOR_DANGER,
            bg=app_module.COLOR_DANGER_SOFT,
            padx=4,
            pady=2,
        )

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

        self.assertEqual([entry["id"] for entry in app.entries], [parent["id"]])
        self.assertEqual(
            [entry["id"] for entry in app.entries[0]["children"]],
            [child_a["id"], child_b["id"]],
        )
        self.assertFalse(data_file.exists())
        showerror.assert_called_once()

    def test_atomic_save_keeps_previous_generation_as_backup(self) -> None:
        parent, _child_a, _child_b = self.make_hierarchy()
        app = self.make_app([parent])

        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "schedules.json"
            with (
                patch.object(app_module, "DATA_FILE", str(data_file)),
                patch.object(app_module.os, "fsync", wraps=app_module.os.fsync) as fsync,
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                self.assertTrue(app._save())
                parent["task"] = "Updated parent"
                self.assertTrue(app._save())

            backup = json.loads(Path(f"{data_file}.bak").read_text(encoding="utf-8"))
            current = json.loads(data_file.read_text(encoding="utf-8"))

        self.assertEqual(backup["parents"][0]["task"], "Parent")
        self.assertEqual(current["parents"][0]["task"], "Updated parent")
        self.assertGreaterEqual(fsync.call_count, 3)
        showerror.assert_not_called()

    def test_load_recovers_corrupt_primary_from_valid_backup(self) -> None:
        parent, _child_a, _child_b = self.make_hierarchy()
        app = self.make_app()

        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "schedules.json"
            data_file.write_text('{"version": 2, "parents": ', encoding="utf-8")
            Path(f"{data_file}.bak").write_text(
                json.dumps(
                    app_module.serialize_schedule({"version": 2, "parents": [parent]}),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with (
                patch.object(app_module, "DATA_FILE", str(data_file)),
                patch.object(app_module, "COMPLETE_LOG_FILE", str(Path(temp_dir) / "completed.jsonl")),
                patch.object(app_module.messagebox, "showwarning") as showwarning,
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                app._load()

            repaired = json.loads(data_file.read_text(encoding="utf-8"))

        self.assertFalse(app.load_failed)
        self.assertEqual(app.entries[0]["id"], parent["id"])
        self.assertEqual(repaired["parents"][0]["id"], parent["id"])
        showwarning.assert_called_once()
        showerror.assert_not_called()

    def test_failed_tmp_recovery_preserves_the_only_valid_copy(self) -> None:
        parent, _child_a, _child_b = self.make_hierarchy()
        app = self.make_app()

        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "schedules.json"
            temp_file = Path(f"{data_file}.tmp")
            temp_file.write_text(
                app_module._schedule_text({"version": 2, "parents": [parent]}),
                encoding="utf-8",
                newline="\n",
            )
            real_replace = app_module.os.replace

            def fail_primary_replace(source: str, destination: str) -> None:
                if str(destination) == str(data_file):
                    raise OSError("simulated replace failure")
                real_replace(source, destination)

            with (
                patch.object(app_module, "DATA_FILE", str(data_file)),
                patch.object(app_module, "COMPLETE_LOG_FILE", str(Path(temp_dir) / "completed.jsonl")),
                patch.object(app_module.os, "replace", side_effect=fail_primary_replace),
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                app._load()

            preserved = json.loads(temp_file.read_text(encoding="utf-8"))

        self.assertTrue(app.load_failed)
        self.assertEqual(preserved["parents"][0]["id"], parent["id"])
        showerror.assert_called_once()

    def test_pending_completion_journal_is_replayed_idempotently(self) -> None:
        parent, _child_a, _child_b = self.make_hierarchy()
        app = self.make_app([parent])

        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "schedules.json"
            log_file = Path(temp_dir) / "completed_tasks.jsonl"
            data_file.write_text(
                app_module._schedule_text(app.schedule), encoding="utf-8", newline="\n"
            )
            record = app._completion_record(parent)
            journal = {
                "version": 1,
                "records": [record],
                "schedule": {"version": 2, "parents": []},
            }
            pending = Path(f"{log_file}.pending")
            pending.write_text(
                json.dumps(journal, ensure_ascii=False), encoding="utf-8", newline="\n"
            )
            with (
                patch.object(app_module, "DATA_FILE", str(data_file)),
                patch.object(app_module, "COMPLETE_LOG_FILE", str(log_file)),
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                app._load()
                pending.write_text(
                    json.dumps(journal, ensure_ascii=False),
                    encoding="utf-8",
                    newline="\n",
                )
                app._load()

            saved = json.loads(data_file.read_text(encoding="utf-8"))
            records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(saved["parents"], [])
        self.assertEqual([item[app_module.LOG_FIELD_ID] for item in records], [parent["id"]])
        self.assertFalse(pending.exists())
        self.assertFalse(app.load_failed)
        showerror.assert_not_called()

    def test_atomic_log_update_salvages_only_a_torn_final_line(self) -> None:
        parent, child_a, _child_b = self.make_hierarchy()
        app = self.make_app([parent])

        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "completed_tasks.jsonl"
            first = app._completion_record(parent)
            log_file.write_bytes(
                (json.dumps(first, ensure_ascii=False) + "\n").encode("utf-8")
                + '{"途中":"あ'.encode("utf-8")[:-1]
            )
            with (
                patch.object(app_module, "COMPLETE_LOG_FILE", str(log_file)),
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                self.assertTrue(app._append_completion_logs([child_a]))

            records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
            backup_exists = Path(f"{log_file}.bak").exists()

        self.assertEqual(
            [item[app_module.LOG_FIELD_ID] for item in records],
            [parent["id"], child_a["id"]],
        )
        self.assertTrue(backup_exists)
        showerror.assert_not_called()

    def test_completion_log_recovers_from_valid_backup(self) -> None:
        parent, _child_a, _child_b = self.make_hierarchy()
        app = self.make_app([parent])

        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "completed_tasks.jsonl"
            record = app._completion_record(parent)
            log_file.write_text('{"壊れた行"\n', encoding="utf-8", newline="\n")
            Path(f"{log_file}.bak").write_text(
                json.dumps(record, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            with (
                patch.object(app_module, "COMPLETE_LOG_FILE", str(log_file)),
                patch.object(app_module.messagebox, "showerror") as showerror,
            ):
                latest = app._load_latest_completion_states()

            repaired = [
                json.loads(line)
                for line in log_file.read_text(encoding="utf-8").splitlines()
            ]

        self.assertIsNotNone(latest)
        self.assertEqual(repaired[0][app_module.LOG_FIELD_ID], parent["id"])
        showerror.assert_not_called()

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

    def test_extreme_date_scale_limits_canvas_items_to_visible_resolution(self) -> None:
        app = self.make_app()
        app.scale_canvas = Mock()
        app.scale_canvas.winfo_width.return_value = 1360
        app.scale_canvas.winfo_height.return_value = 58
        app.scale_canvas.create_text.return_value = 1
        app.scale_canvas.bbox.return_value = None
        app.today_label_screen_x = None
        app.current_jst_date = app_module.date(2026, 7, 15)
        app._visible_range = Mock(return_value=(app_module.date.min, app_module.date.max))
        app._redraw_all_gantt = Mock()

        app._redraw_scale()

        self.assertLess(app.scale_canvas.create_line.call_count, 200)
        self.assertLess(app.scale_canvas.create_text.call_count, 200)
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

    def test_move_to_todo_moves_the_whole_parent_group_and_rolls_back_on_save_failure(self) -> None:
        parent, child_a, child_b = self.make_hierarchy()
        app = self.make_app([parent])
        app.schedule["todos"] = []
        app.schedule["settings"] = {"row_height": 40}
        app.todos = app.schedule["todos"]
        app.selected_id = child_a["id"]
        app.selected_todo_id = None
        app._rebuild_todo_rows = Mock()
        app._switch_mode = Mock()
        app._save = Mock(return_value=False)

        with (
            patch.object(app_module.messagebox, "askyesno", return_value=True),
            patch.object(app_module.messagebox, "showerror"),
        ):
            app._on_move_to_todo()

        self.assertEqual([item["id"] for item in app.entries], [parent["id"]])
        self.assertEqual([item["id"] for item in parent["children"]], [child_a["id"], child_b["id"]])
        self.assertEqual(app.todos, [])
        self.assertEqual(app.selected_id, child_a["id"])
        app._switch_mode.assert_not_called()

    def test_move_to_todo_succeeds_with_default_notifications(self) -> None:
        parent, child_a, _child_b = self.make_hierarchy()
        app = self.make_app([parent])
        app.schedule["todos"] = []
        app.schedule["settings"] = {"row_height": 40}
        app.todos = app.schedule["todos"]
        app.selected_id = child_a["id"]
        app.selected_todo_id = None
        app._rebuild_todo_rows = Mock()
        app._switch_mode = Mock()
        app._save = Mock(return_value=True)

        with patch.object(app_module.messagebox, "askyesno", return_value=True):
            app._on_move_to_todo()

        self.assertEqual(app.entries, [])
        self.assertEqual(app.todos[0]["id"], parent["id"])
        self.assertTrue(app.todos[0]["notify"])
        self.assertTrue(all(child["notify"] for child in app.todos[0]["children"]))
        app._switch_mode.assert_called_once_with("todo")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import gc
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

import sch_gantt_main as app_module
from schedule_model import KIND_CHILD, KIND_PARENT, new_entry


class ScheduleAppTkTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tkを初期化できません: {exc}")
        self.addCleanup(self.root.destroy)
        self.load_patcher = patch.object(app_module.ScheduleApp, "_load", autospec=True)
        self.load_patcher.start()
        self.addCleanup(self.load_patcher.stop)

        self.app = app_module.ScheduleApp(self.root)
        self.root.geometry("1280x720+20+20")
        parent = new_entry(
            KIND_PARENT,
            "日本語の親タスク",
            "2026-07-01",
            "2026-07-31",
            entry_id="parent-1",
            progress_value=45,
        )
        child_a = new_entry(
            KIND_CHILD,
            "デザインを調整する",
            "2026-07-02",
            "2026-07-12",
            parent_id=parent["id"],
            entry_id="child-a",
            progress_value=60,
        )
        child_b = new_entry(
            KIND_CHILD,
            "日本語表示を確認する",
            "2026-07-13",
            "2026-07-24",
            parent_id=parent["id"],
            entry_id="child-b",
            progress_value=20,
        )
        parent["children"] = [child_a, child_b]
        self.parent = parent
        self.child_a = child_a
        self.child_b = child_b
        self.app.schedule = {"version": 2, "parents": [parent]}
        self.app.entries = self.app.schedule["parents"]
        self.app._save = Mock(return_value=True)
        self.app._rebuild_rows()
        self._pump()

    def _pump(self) -> None:
        self.root.update_idletasks()
        self.root.update()

    def test_theme_fonts_tree_and_row_dimensions(self) -> None:
        self.assertEqual(self.root.cget("bg").upper(), app_module.COLOR_APP_BG)
        self.assertEqual(self.app.style.theme_use(), "clam")
        self.assertEqual(
            set(self.app.toolbar_buttons),
            {
                app_module.TEXT_ADD_PARENT,
                app_module.TEXT_ADD_CHILD,
                app_module.TEXT_DELETE,
                app_module.TEXT_UP,
                app_module.TEXT_DOWN,
                app_module.TEXT_EXPORT_EXCEL,
                app_module.TEXT_RELOAD_INCOMPLETE,
            },
        )
        self.assertTrue(
            all(isinstance(button, ttk.Button) for button in self.app.toolbar_buttons.values())
        )

        task_font = self.app.task_font.actual()
        parent_font = self.app.parent_font.actual()
        self.assertEqual(parent_font["family"], task_font["family"])
        self.assertEqual(parent_font["size"], task_font["size"])
        self.assertEqual(task_font["weight"], "normal")
        self.assertEqual(parent_font["weight"], "bold")

        rows = self.app.row_widgets
        self.assertEqual([row.task_label.cget("text") for row in rows], [
            self.parent["task"],
            self.child_a["task"],
            self.child_b["task"],
        ])
        self.assertEqual([row.tree_indicator.cget("text") for row in rows], ["▼", "├─", "└─"])
        self.assertEqual(rows[0].task_label.cget("font"), str(self.app.parent_font))
        self.assertEqual(rows[1].task_label.cget("font"), str(self.app.task_font))
        for row in rows:
            self.assertEqual(row.task_frame.winfo_height(), self.app.row_content_height)
            self.assertEqual(row.gantt_canvas.winfo_height(), self.app.row_content_height)
            self.assertGreaterEqual(row.task_label.winfo_height(), self.app.task_font.metrics("linespace"))

    def test_columns_selection_and_collapse_stay_aligned(self) -> None:
        for width in (1050, 1280, 1600):
            self.root.geometry(f"{width}x720+20+20")
            self._pump()
            first_row = self.app.row_widgets[0]
            self.assertLessEqual(
                abs(
                    self.app.scale_canvas.winfo_rootx()
                    - first_row.gantt_canvas.winfo_rootx()
                ),
                2,
            )
            self.assertLessEqual(
                abs(self.app.splitter.winfo_rootx() - self._row_splitter_x(first_row)),
                2,
            )
            self.assertLessEqual(
                abs(self.app.rows_container.winfo_width() - self.app.rows_canvas.winfo_width()),
                2,
            )

        self.app._select(self.child_a["id"])
        self._pump()
        selected = self.app.row_widgets[1]
        self.assertEqual(selected.container.cget("bg").upper(), app_module.COLOR_PRIMARY_SOFT)
        self.assertEqual(selected.selection_bar.cget("bg").upper(), app_module.COLOR_PRIMARY)
        self.assertNotEqual(
            self.app.row_widgets[0].container.cget("bg").upper(),
            app_module.COLOR_PRIMARY_SOFT,
        )

        self.app._toggle_collapsed(self.parent["id"])
        self._pump()
        self.assertEqual(self.app.selected_id, self.parent["id"])
        self.assertEqual(len(self.app.row_widgets), 1)
        self.assertEqual(self.app.row_widgets[0].tree_indicator.cget("text"), "▶")

    def _row_splitter_x(self, widgets: app_module.RowWidgets) -> int:
        column_box = widgets.container.grid_bbox(5, 0, 5, 0)
        return widgets.container.winfo_rootx() + column_box[0]

    def test_scroll_range_and_modern_dialog(self) -> None:
        parents = []
        for index in range(45):
            parents.append(
                new_entry(
                    KIND_PARENT,
                    f"親タスク {index + 1}",
                    "2026-07-01",
                    "2026-07-31",
                    entry_id=f"parent-{index + 10}",
                )
            )
        self.app.schedule = {"version": 2, "parents": parents}
        self.app.entries = parents
        self.app._rebuild_rows()
        self._pump()

        scroll_region = tuple(float(value) for value in self.app.rows_canvas.cget("scrollregion").split())
        self.assertGreater(scroll_region[3] - scroll_region[1], self.app.rows_canvas.winfo_height())
        self.assertEqual(self.app.rows_canvas.yview()[0], 0.0)
        self.app.rows_canvas.yview_moveto(1.0)
        self._pump()
        self.assertAlmostEqual(self.app.rows_canvas.yview()[1], 1.0, places=3)

        self.app._open_entry_dialog(kind="parent")
        self._pump()
        dialogs = [
            widget for widget in self.root.winfo_children() if isinstance(widget, tk.Toplevel)
        ]
        self.assertEqual(len(dialogs), 1)
        dialog = dialogs[0]
        self.assertEqual(str(dialog.transient()), str(self.root))
        self.assertTrue(self._descendants_of_type(dialog, ttk.Entry))
        self.assertTrue(self._descendants_of_type(dialog, ttk.Radiobutton))
        primary_buttons = [
            button
            for button in self._descendants_of_type(dialog, ttk.Button)
            if button.cget("style") == "Primary.TButton"
        ]
        self.assertEqual(len(primary_buttons), 1)
        cancel_buttons = [
            button
            for button in self._descendants_of_type(dialog, ttk.Button)
            if button.cget("text") == app_module.BUTTON_CANCEL
        ]
        self.assertEqual(len(cancel_buttons), 1)
        cancel_buttons[0].invoke()
        self._pump()
        self.assertFalse(dialog.winfo_exists())

    def test_repeated_dialog_close_does_not_leak_trace_commands(self) -> None:
        before = set(self.root.tk.splitlist(self.root.tk.call("info", "commands")))
        for _index in range(5):
            self.app._open_entry_dialog(kind="parent")
            self._pump()
            dialog = next(
                widget
                for widget in self.root.winfo_children()
                if isinstance(widget, tk.Toplevel)
            )
            cancel = next(
                button
                for button in self._descendants_of_type(dialog, ttk.Button)
                if button.cget("text") == app_module.BUTTON_CANCEL
            )
            cancel.invoke()
            self._pump()
        gc.collect()
        after = set(self.root.tk.splitlist(self.root.tk.call("info", "commands")))
        leaked_callbacks = [
            command
            for command in after - before
            if "<lambda>" in command or "refresh_progress_mode" in command
        ]
        self.assertEqual(leaked_callbacks, [])

    def _descendants_of_type(self, widget: tk.Misc, widget_type: type) -> list:
        matches = []
        for child in widget.winfo_children():
            if isinstance(child, widget_type):
                matches.append(child)
            matches.extend(self._descendants_of_type(child, widget_type))
        return matches


if __name__ == "__main__":
    unittest.main()

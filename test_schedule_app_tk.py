from __future__ import annotations

import copy
import gc
from datetime import timedelta
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import sch_gantt_main as app_module
from schedule_model import KIND_CHILD, KIND_PARENT, new_entry, new_todo_entry


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
        self.addCleanup(self._cancel_scheduled_callbacks)
        self.root.geometry("1280x720+20+20")
        parent = new_entry(
            KIND_PARENT,
            "日本語の親タスク",
            "2026-07-01",
            "2026-07-31",
            entry_id="parent-1",
            progress_value=45,
            started="2026-07-14",
        )
        child_a = new_entry(
            KIND_CHILD,
            "デザインを調整する",
            "2026-07-02",
            "2026-07-12",
            parent_id=parent["id"],
            entry_id="child-a",
            progress_value=60,
            started="2026-07-16",
        )
        child_b = new_entry(
            KIND_CHILD,
            "日本語表示を確認する",
            "2026-07-13",
            "2026-07-24",
            parent_id=parent["id"],
            entry_id="child-b",
            progress_value=20,
            started="2026-07-13",
        )
        parent["children"] = [child_a, child_b]
        self.parent = parent
        self.child_a = child_a
        self.child_b = child_b
        self.app.schedule = {
            "version": 3,
            "parents": [parent],
            "todos": [],
            "settings": {"row_height": 40},
        }
        self.app._ensure_schedule_defaults()
        self.app._save = Mock(return_value=True)
        self.app._rebuild_rows()
        self._pump()

    def _pump(self) -> None:
        self.root.update_idletasks()
        self.root.update()

    def test_theme_fonts_tree_and_row_dimensions(self) -> None:
        self.assertEqual(self.root.title(), "Schedule-board")
        self.assertTrue(self.root.protocol("WM_DELETE_WINDOW"))
        self.assertEqual(self.root.cget("bg").upper(), app_module.COLOR_APP_BG)
        self.assertEqual(self.app.style.theme_use(), "clam")
        self.assertEqual(
            set(self.app.toolbar_buttons),
            {
                app_module.TEXT_ADD_MENU,
                app_module.TEXT_MOVE_TO_TODO,
                app_module.TEXT_DELETE,
                app_module.TEXT_UP,
                app_module.TEXT_DOWN,
                app_module.TEXT_COMPLETE,
                app_module.TEXT_SORT,
                app_module.TEXT_MORE,
            },
        )
        self.assertEqual(
            sum(
                isinstance(control, ttk.Menubutton)
                for control in self.app.toolbar_buttons.values()
            ),
            3,
        )
        add_menu = self.app.toolbar_buttons[app_module.TEXT_ADD_MENU].menu
        self.assertEqual(add_menu.entrycget(0, "label"), "親タスクを追加")
        self.assertEqual(add_menu.entrycget(1, "label"), "子タスクを追加")
        self.assertEqual(
            set(self.app.todo_toolbar_buttons),
            {
                app_module.TEXT_ADD_MENU,
                app_module.TEXT_MOVE_TO_SCHEDULE,
                app_module.TEXT_DELETE,
                app_module.TEXT_UP,
                app_module.TEXT_DOWN,
                app_module.TEXT_COMPLETE,
                app_module.TEXT_SORT,
                app_module.TEXT_SETTINGS,
            },
        )
        self.assertTrue(
            isinstance(self.app.toolbar_buttons[app_module.TEXT_UP], ttk.Button)
        )
        self.assertTrue(
            isinstance(self.app.toolbar_buttons[app_module.TEXT_DOWN], ttk.Button)
        )
        complete_button = self.app.toolbar_buttons[app_module.TEXT_COMPLETE]
        self.assertIsInstance(complete_button, ttk.Button)
        self.assertEqual(complete_button.cget("text"), "✓ 完了")
        self.assertEqual(complete_button.cget("style"), "Success.TButton")
        self.assertEqual(
            self.app.schedule_sort_button.menu.entrycget(0, "label"),
            "ソートなし",
        )
        self.assertEqual(
            self.app.schedule_sort_button.menu.entrycget(10, "label"),
            "開始日：降順",
        )
        self.assertEqual(
            self.app.todo_sort_button.menu.entrycget(4, "label"),
            "期限：降順",
        )
        todo_complete = self.app.todo_toolbar_buttons[app_module.TEXT_COMPLETE]
        self.assertIsInstance(todo_complete, ttk.Button)
        self.assertEqual(todo_complete.cget("text"), "✓ 完了")
        self.assertEqual(todo_complete.cget("style"), "Success.TButton")

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
        self.assertEqual(rows[0].started_label.cget("text"), "07/13")
        self.assertEqual(rows[1].started_label.cget("text"), "07/16")
        self.assertEqual(rows[2].started_label.cget("text"), "07/13")
        for row in rows:
            self.assertFalse(hasattr(row, "complete_button"))
            self.assertEqual(row.drag_handle.cget("text"), app_module.DRAG_HANDLE_TEXT)
            self.assertEqual(row.drag_handle.cget("cursor"), "fleur")
            self.assertTrue(row.drag_handle.bind("<B1-Motion>"))
            self.assertEqual(row.task_frame.winfo_height(), self.app.row_content_height)
            self.assertEqual(row.gantt_canvas.winfo_height(), self.app.row_content_height)
            self.assertGreaterEqual(row.task_label.winfo_height(), self.app.task_font.metrics("linespace"))

    def test_primary_navigation_uses_exclusive_tab_styling(self) -> None:
        self.assertEqual(
            self.app.schedule_tab_indicator.cget("bg").upper(),
            app_module.COLOR_PRIMARY,
        )
        self.assertEqual(
            self.app.todo_tab_indicator.cget("bg").upper(),
            app_module.COLOR_HEADER,
        )
        self.assertTrue(self.app.schedule_toolbar.winfo_ismapped())
        self.assertFalse(self.app.todo_toolbar.winfo_ismapped())

        self.app._switch_mode("todo")
        self._pump()

        self.assertEqual(
            self.app.schedule_tab_indicator.cget("bg").upper(),
            app_module.COLOR_HEADER,
        )
        self.assertEqual(
            self.app.todo_tab_indicator.cget("bg").upper(),
            app_module.COLOR_PRIMARY,
        )
        self.assertFalse(self.app.schedule_toolbar.winfo_ismapped())
        self.assertTrue(self.app.todo_toolbar.winfo_ismapped())

    def test_list_move_buttons_are_separated_on_toolbar_right(self) -> None:
        def assert_right_aligned(
            toolbar: tk.Frame,
            buttons: dict[str, tk.Widget],
            move_key: str,
        ) -> None:
            move_button = buttons[move_key]
            left_controls = [
                control for key, control in buttons.items() if key != move_key
            ]
            for width in (1050, 1280):
                with self.subTest(move_key=move_key, width=width):
                    self.root.geometry(f"{width}x720+20+20")
                    self._pump()
                    left_edge = max(
                        control.winfo_rootx() + control.winfo_width()
                        for control in left_controls
                    )
                    toolbar_right = toolbar.winfo_rootx() + toolbar.winfo_width()

                    self.assertGreater(move_button.winfo_rootx(), left_edge + 40)
                    self.assertLessEqual(
                        abs(
                            move_button.winfo_rootx()
                            + move_button.winfo_width()
                            - toolbar_right
                        ),
                        2,
                    )

        assert_right_aligned(
            self.app.schedule_toolbar,
            self.app.toolbar_buttons,
            app_module.TEXT_MOVE_TO_TODO,
        )
        self.app._switch_mode("todo")
        self._pump()
        assert_right_aligned(
            self.app.todo_toolbar,
            self.app.todo_toolbar_buttons,
            app_module.TEXT_MOVE_TO_SCHEDULE,
        )

    def test_moves_between_lists_keep_the_current_view(self) -> None:
        self.app.selected_id = self.child_a["id"]

        self.app._on_move_to_todo()
        self._pump()

        self.assertEqual(self.app.active_mode, "schedule")
        self.assertTrue(self.app.schedule_toolbar.winfo_ismapped())
        self.assertFalse(self.app.todo_toolbar.winfo_ismapped())

        self.app._switch_mode("todo")
        self._pump()
        self.app._on_move_to_schedule()
        self._pump()

        self.assertEqual(self.app.active_mode, "todo")
        self.assertFalse(self.app.schedule_toolbar.winfo_ismapped())
        self.assertTrue(self.app.todo_toolbar.winfo_ismapped())

    def test_row_context_menus_move_the_right_clicked_group(self) -> None:
        schedule_row = next(
            row for row in self.app.row_widgets if row.entry_id == self.child_a["id"]
        )
        self.assertTrue(schedule_row.container.bind("<Button-3>"))
        self.assertTrue(schedule_row.task_label.bind("<Button-3>"))
        self.assertTrue(schedule_row.gantt_canvas.bind("<Button-3>"))

        schedule_event = SimpleNamespace(
            x_root=schedule_row.task_label.winfo_rootx() + 4,
            y_root=schedule_row.task_label.winfo_rooty() + 4,
        )
        with (
            patch.object(self.app.schedule_row_menu, "tk_popup") as popup,
            patch.object(self.app.schedule_row_menu, "grab_release") as release,
        ):
            result = self.app._show_row_context_menu(
                "schedule",
                self.child_a["id"],
                schedule_event,
            )

        self.assertEqual(result, "break")
        popup.assert_called_once_with(schedule_event.x_root, schedule_event.y_root)
        release.assert_called_once_with()
        self.assertEqual(self.app.selected_id, self.child_a["id"])
        self.assertEqual(
            self.app.schedule_row_menu.entrycget(0, "label"),
            app_module.TEXT_MOVE_TO_TODO,
        )
        self.app.schedule_row_menu.invoke(0)
        self._pump()

        self.assertEqual(self.app.active_mode, "schedule")
        self.assertEqual(self.app.entries, [])
        self.assertEqual(self.app.todos[0]["id"], self.parent["id"])

        self.app._switch_mode("todo")
        self._pump()
        todo_row = next(
            row for row in self.app.todo_row_widgets if row.entry_id == self.child_a["id"]
        )
        self.assertTrue(todo_row.container.bind("<Button-3>"))
        self.assertTrue(todo_row.task_label.bind("<Button-3>"))
        self.assertTrue(todo_row.notify_button.bind("<Button-3>"))

        todo_event = SimpleNamespace(
            x_root=todo_row.task_label.winfo_rootx() + 4,
            y_root=todo_row.task_label.winfo_rooty() + 4,
        )
        with (
            patch.object(self.app.todo_row_menu, "tk_popup") as popup,
            patch.object(self.app.todo_row_menu, "grab_release") as release,
        ):
            result = self.app._show_row_context_menu(
                "todo",
                self.child_a["id"],
                todo_event,
            )

        self.assertEqual(result, "break")
        popup.assert_called_once_with(todo_event.x_root, todo_event.y_root)
        release.assert_called_once_with()
        self.assertEqual(self.app.selected_todo_id, self.child_a["id"])
        self.assertEqual(
            self.app.todo_row_menu.entrycget(0, "label"),
            app_module.TEXT_MOVE_TO_SCHEDULE,
        )
        self.app.todo_row_menu.invoke(0)
        self._pump()

        self.assertEqual(self.app.active_mode, "todo")
        self.assertEqual(self.app.todos, [])
        self.assertEqual(self.app.entries[0]["id"], self.parent["id"])

    def test_sort_menus_restore_order_captured_before_first_sort(self) -> None:
        first = new_entry(
            KIND_PARENT,
            "Gamma",
            "2026-07-01",
            "2026-07-31",
            entry_id="sort-first",
        )
        second = new_entry(
            KIND_PARENT,
            "Alpha",
            "2026-07-01",
            "2026-07-31",
            entry_id="sort-second",
        )
        third = new_entry(
            KIND_PARENT,
            "Beta",
            "2026-07-01",
            "2026-07-31",
            entry_id="sort-third",
        )
        self.app.schedule = {
            "version": 3,
            "parents": [first, second, third],
            "todos": [],
            "settings": {"row_height": 40},
        }
        self.app._ensure_schedule_defaults()
        self.app._rebuild_rows()

        self.app.schedule_sort_button.menu.invoke(1)
        self.app.schedule_sort_button.menu.invoke(2)
        self._pump()

        self.assertEqual(
            [parent["id"] for parent in self.app.entries],
            ["sort-first", "sort-third", "sort-second"],
        )
        self.assertEqual(
            self.app.schedule["settings"]["schedule_original_order"]["parents"],
            ["sort-first", "sort-second", "sort-third"],
        )
        self.assertEqual(self.app.schedule_sort_button.cget("text"), "ソート: タスク名 ↓")

        self.app.selected_id = first["id"]
        self.app._on_down()
        self.app.schedule_sort_button.menu.invoke(0)
        self._pump()

        self.assertEqual(
            [parent["id"] for parent in self.app.entries],
            ["sort-first", "sort-second", "sort-third"],
        )
        self.assertIsNone(
            self.app.schedule["settings"]["schedule_original_order"]
        )
        self.assertEqual(self.app.schedule_sort_button.cget("text"), "ソート: なし")

        todo_first = new_todo_entry(
            KIND_PARENT,
            "Gamma",
            "2026-07-30",
            entry_id="todo-sort-first",
        )
        todo_second = new_todo_entry(
            KIND_PARENT,
            "Alpha",
            "2026-07-10",
            entry_id="todo-sort-second",
        )
        todo_third = new_todo_entry(
            KIND_PARENT,
            "Beta",
            "2026-07-20",
            entry_id="todo-sort-third",
        )
        self.app.schedule["todos"] = [todo_first, todo_second, todo_third]
        self.app._ensure_schedule_defaults()
        self.app._rebuild_todo_rows()
        self.app.todo_sort_button.menu.invoke(1)
        self._pump()

        self.assertEqual(
            [todo["id"] for todo in self.app.todos],
            ["todo-sort-second", "todo-sort-third", "todo-sort-first"],
        )
        self.app.selected_todo_id = todo_second["id"]
        self.app._move_selected_todo(1)
        self.app.todo_sort_button.menu.invoke(0)
        self._pump()

        self.assertEqual(
            [todo["id"] for todo in self.app.todos],
            ["todo-sort-first", "todo-sort-second", "todo-sort-third"],
        )
        self.assertEqual(self.app.todo_sort_button.cget("text"), "ソート: なし")

        self.app._save = Mock(return_value=False)
        self.app.schedule_sort_button.menu.invoke(1)
        self._pump()

        self.assertEqual(
            [parent["id"] for parent in self.app.entries],
            ["sort-first", "sort-second", "sort-third"],
        )
        self.assertEqual(
            self.app.schedule["settings"]["schedule_sort"],
            app_module.SORT_NONE,
        )
        self.assertIsNone(
            self.app.schedule["settings"]["schedule_original_order"]
        )

    def test_separate_up_down_buttons_support_repeated_moves(self) -> None:
        child_c = new_entry(
            KIND_CHILD,
            "連続移動するタスク",
            "2026-07-25",
            "2026-07-28",
            parent_id=self.parent["id"],
            entry_id="child-c",
        )
        self.parent["children"].append(child_c)
        self.app.selected_id = child_c["id"]
        self.app._rebuild_rows()

        self.app.toolbar_buttons[app_module.TEXT_UP].invoke()
        self.app.toolbar_buttons[app_module.TEXT_UP].invoke()
        self._pump()

        self.assertEqual(
            [child["id"] for child in self.parent["children"]],
            ["child-c", "child-a", "child-b"],
        )

    def test_schedule_parent_drag_shows_group_preview_and_reorders_group(self) -> None:
        second_parent = new_entry(
            KIND_PARENT,
            "第2の親タスク",
            "2026-08-01",
            "2026-08-31",
            entry_id="parent-2",
        )
        second_parent["children"] = [
            new_entry(
                KIND_CHILD,
                "第2の子タスク",
                "2026-08-01",
                "2026-08-10",
                parent_id=second_parent["id"],
                entry_id="child-2",
            )
        ]
        self.app.entries.append(second_parent)
        self.app._rebuild_rows()
        self._pump()
        source = self.app.row_widgets[0]
        target = self.app.row_widgets[-1]
        start_event = SimpleNamespace(
            x_root=source.drag_handle.winfo_rootx(),
            y_root=source.drag_handle.winfo_rooty() + 2,
        )
        drop_event = SimpleNamespace(
            x_root=start_event.x_root,
            y_root=target.container.winfo_rooty() + target.container.winfo_height() - 2,
        )

        self.app._on_row_drag_press("schedule", self.parent["id"], start_event)
        self.app._on_row_drag_motion("schedule", self.parent["id"], drop_event)
        self._pump()

        state = self.app._row_drag
        self.assertIsNotNone(state)
        self.assertTrue(state.active)
        self.assertTrue(state.target_valid)
        self.assertIsNotNone(state.placeholder)
        self.assertGreaterEqual(
            state.placeholder.winfo_height(),
            self.app.row_content_height * 3,
        )
        self.assertFalse(source.container.winfo_ismapped())

        self.app._on_row_drag_release("schedule", self.parent["id"], drop_event)
        self._pump()

        self.assertEqual(
            [parent["id"] for parent in self.app.entries],
            ["parent-2", "parent-1"],
        )
        self.assertEqual(
            [child["id"] for child in self.app.entries[1]["children"]],
            ["child-a", "child-b"],
        )

    def test_drag_preview_to_top_keeps_short_list_at_canvas_top(self) -> None:
        parent_a = new_entry(
            KIND_PARENT,
            "先頭の親",
            "2026-07-01",
            "2026-07-10",
            entry_id="top-parent-a",
        )
        parent_b = new_entry(
            KIND_PARENT,
            "中央の親",
            "2026-07-01",
            "2026-07-10",
            entry_id="top-parent-b",
        )
        parent_c = new_entry(
            KIND_PARENT,
            "末尾から移動する親",
            "2026-07-01",
            "2026-07-10",
            entry_id="top-parent-c",
        )
        parent_c["children"] = [
            new_entry(
                KIND_CHILD,
                "末尾親の子",
                "2026-07-01",
                "2026-07-02",
                parent_id=parent_c["id"],
                entry_id="top-child-c",
            )
        ]
        self.app.schedule = {
            "version": 3,
            "parents": [parent_a, parent_b, parent_c],
            "todos": [],
            "settings": {"row_height": 40},
        }
        self.app._ensure_schedule_defaults()
        self.app._rebuild_rows()
        self._pump()
        source = next(
            row for row in self.app.row_widgets if row.entry_id == parent_c["id"]
        )
        start_event = SimpleNamespace(
            x_root=source.drag_handle.winfo_rootx(),
            y_root=source.drag_handle.winfo_rooty() + 2,
        )
        top_event = SimpleNamespace(
            x_root=start_event.x_root,
            y_root=self.app.rows_canvas.winfo_rooty() + 2,
        )

        self.app._on_row_drag_press("schedule", source.entry_id, start_event)
        for _index in range(10):
            self.app._on_row_drag_motion("schedule", source.entry_id, top_event)
            self._pump()

        state = self.app._row_drag
        self.assertTrue(state.target_valid)
        self.assertIsNotNone(state.placeholder)
        self.assertAlmostEqual(self.app.rows_canvas.yview()[0], 0.0, places=3)
        self.assertLessEqual(
            abs(
                state.placeholder.winfo_rooty()
                - self.app.rows_canvas.winfo_rooty()
            ),
            2,
        )
        self.app._on_row_drag_escape()

    def test_drag_auto_scroll_remains_available_for_long_lists(self) -> None:
        parents = [
            new_entry(
                KIND_PARENT,
                f"スクロール対象 {index}",
                "2026-07-01",
                "2026-07-31",
                entry_id=f"scroll-parent-{index}",
            )
            for index in range(45)
        ]
        self.app.schedule = {"version": 3, "parents": parents, "todos": []}
        self.app._ensure_schedule_defaults()
        self.app._rebuild_rows()
        self._pump()
        canvas = self.app.rows_canvas
        canvas.yview_moveto(0.5)
        self._pump()
        middle = canvas.yview()[0]

        self.app._auto_scroll_row_drag("schedule", canvas.winfo_rooty() + 1)
        self._pump()
        moved_up = canvas.yview()[0]
        self.assertLess(moved_up, middle)

        self.app._auto_scroll_row_drag(
            "schedule",
            canvas.winfo_rooty() + canvas.winfo_height() - 1,
        )
        self._pump()
        self.assertGreater(canvas.yview()[0], moved_up)

    def test_drag_threshold_escape_and_parent_boundary_preserve_order(self) -> None:
        source = self.app.row_widgets[1]
        target = self.app.row_widgets[2]
        start_event = SimpleNamespace(
            x_root=source.drag_handle.winfo_rootx(),
            y_root=source.drag_handle.winfo_rooty() + 2,
        )
        small_motion = SimpleNamespace(
            x_root=start_event.x_root,
            y_root=start_event.y_root + app_module.DRAG_START_THRESHOLD - 1,
        )
        drop_event = SimpleNamespace(
            x_root=start_event.x_root,
            y_root=target.container.winfo_rooty() + target.container.winfo_height() - 2,
        )
        original_order = [child["id"] for child in self.parent["children"]]
        self.app._save.reset_mock()

        self.app._on_row_drag_press("schedule", source.entry_id, start_event)
        self.app._on_row_drag_motion("schedule", source.entry_id, small_motion)
        self.app._on_row_drag_release("schedule", source.entry_id, small_motion)
        self.assertEqual(
            [child["id"] for child in self.parent["children"]],
            original_order,
        )
        self.app._save.assert_not_called()

        self.app._on_row_drag_press("schedule", source.entry_id, start_event)
        self.app._on_row_drag_motion("schedule", source.entry_id, drop_event)
        self._pump()
        self.assertIsNotNone(self.app._row_drag.placeholder)
        self.assertEqual(self.app._on_row_drag_escape(), "break")
        self._pump()
        self.assertIsNone(self.app._row_drag)
        self.assertEqual(
            [child["id"] for child in self.parent["children"]],
            original_order,
        )
        self.assertTrue(all(row.container.winfo_ismapped() for row in self.app.row_widgets))
        self.app._save.assert_not_called()

        second_parent = new_entry(
            KIND_PARENT,
            "別の親",
            "2026-08-01",
            "2026-08-10",
            entry_id="boundary-parent",
        )
        second_parent["children"] = [
            new_entry(
                KIND_CHILD,
                "別の親の子",
                "2026-08-01",
                "2026-08-02",
                parent_id=second_parent["id"],
                entry_id="boundary-child",
            )
        ]
        self.app.entries.append(second_parent)
        self.app._rebuild_rows()
        self._pump()
        source = next(row for row in self.app.row_widgets if row.entry_id == "child-a")
        foreign = next(
            row for row in self.app.row_widgets if row.entry_id == "boundary-child"
        )
        start_event = SimpleNamespace(
            x_root=source.drag_handle.winfo_rootx(),
            y_root=source.drag_handle.winfo_rooty() + 2,
        )
        foreign_event = SimpleNamespace(
            x_root=start_event.x_root,
            y_root=foreign.container.winfo_rooty() + 2,
        )
        self.app._on_row_drag_press("schedule", source.entry_id, start_event)
        self.app._on_row_drag_motion("schedule", source.entry_id, foreign_event)
        self.assertFalse(self.app._row_drag.target_valid)
        self.assertIsNone(self.app._row_drag.placeholder)
        self.app._on_row_drag_release("schedule", source.entry_id, foreign_event)
        self.assertEqual(
            [child["id"] for child in self.parent["children"]],
            original_order,
        )

    def test_todo_child_drag_reorders_only_inside_its_parent(self) -> None:
        parent = new_todo_entry(
            KIND_PARENT,
            "親TODO",
            "2026-07-20",
            entry_id="todo-parent-drag",
        )
        parent["children"] = [
            new_todo_entry(
                KIND_CHILD,
                f"子TODO {index}",
                "2026-07-20",
                parent_id=parent["id"],
                entry_id=f"todo-child-{index}",
            )
            for index in (1, 2)
        ]
        self.app.schedule["todos"] = [parent]
        self.app._ensure_schedule_defaults()
        self.app._rebuild_todo_rows()
        self.app._switch_mode("todo")
        self._pump()
        source = self.app.todo_row_widgets[1]
        target = self.app.todo_row_widgets[2]
        start_event = SimpleNamespace(
            x_root=source.drag_handle.winfo_rootx(),
            y_root=source.drag_handle.winfo_rooty() + 2,
        )
        drop_event = SimpleNamespace(
            x_root=start_event.x_root,
            y_root=target.container.winfo_rooty() + target.container.winfo_height() - 2,
        )

        self.app._on_row_drag_press("todo", source.entry_id, start_event)
        self.app._on_row_drag_motion("todo", source.entry_id, drop_event)
        self._pump()
        self.assertIsNotNone(self.app._row_drag.placeholder)
        self.app._on_row_drag_release("todo", source.entry_id, drop_event)
        self._pump()

        self.assertEqual(
            [child["id"] for child in parent["children"]],
            ["todo-child-2", "todo-child-1"],
        )
        self.app.selected_todo_id = "todo-child-1"
        self.app.todo_toolbar_buttons[app_module.TEXT_UP].invoke()
        self.assertEqual(
            [child["id"] for child in parent["children"]],
            ["todo-child-1", "todo-child-2"],
        )
        self.app.todo_toolbar_buttons[app_module.TEXT_DOWN].invoke()
        self.assertEqual(
            [child["id"] for child in parent["children"]],
            ["todo-child-2", "todo-child-1"],
        )

    def test_scale_year_month_and_day_labels_do_not_overlap(self) -> None:
        self.app._redraw_scale()
        self._pump()
        canvas = self.app.scale_canvas
        text_items = [item for item in canvas.find_all() if canvas.type(item) == "text"]

        def item_for_text(text: str) -> int:
            return next(
                item for item in text_items if canvas.itemcget(item, "text") == text
            )

        year_bbox = canvas.bbox(item_for_text("2026"))
        month_bbox = canvas.bbox(item_for_text("7月"))
        day_bboxes = [
            canvas.bbox(item)
            for item in text_items
            if canvas.itemcget(item, "text").isdigit()
            and canvas.itemcget(item, "text") != "2026"
        ]
        self.assertIsNotNone(year_bbox)
        self.assertIsNotNone(month_bbox)
        self.assertTrue(day_bboxes)
        self.assertLess(year_bbox[3], month_bbox[1])
        self.assertLess(month_bbox[3], min(bbox[1] for bbox in day_bboxes if bbox))

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

    def test_today_line_stays_aligned_after_window_move_and_row_redraw(self) -> None:
        self.app.current_jst_date = app_module.date(2026, 7, 15)
        self.app._redraw_scale()
        self._pump()

        self.root.geometry("1280x720+260+20")
        self._pump()
        row = self.app.row_widgets[0]
        self.app._redraw_gantt_for(row.entry_id)

        today_label = next(
            item
            for item in self.app.scale_canvas.find_all()
            if self.app.scale_canvas.type(item) == "text"
            and self.app.scale_canvas.itemcget(item, "text") == "15"
            and self.app.scale_canvas.itemcget(item, "fill") == "white"
        )
        label_box = self.app.scale_canvas.bbox(today_label)
        self.assertIsNotNone(label_box)
        header_x = self.app.scale_canvas.winfo_rootx() + (
            label_box[0] + label_box[2]
        ) / 2
        today_line = next(
            item
            for item in row.gantt_canvas.find_all()
            if row.gantt_canvas.type(item) == "line"
            and row.gantt_canvas.itemcget(item, "fill").upper()
            == app_module.TODAY_LINE_COLOR
        )
        line_x = row.gantt_canvas.winfo_rootx() + row.gantt_canvas.coords(today_line)[0]
        self.assertLessEqual(abs(header_x - line_x), 2)

    def test_short_schedule_list_stays_at_top_when_mousewheel_is_used(self) -> None:
        for delta in (-120, 120):
            self.app._on_rows_mousewheel(SimpleNamespace(delta=delta))
            self._pump()
            self.assertAlmostEqual(self.app.rows_canvas.yview()[0], 0.0, places=3)
            self.assertLessEqual(
                abs(
                    self.app.row_widgets[0].container.winfo_rooty()
                    - self.app.rows_canvas.winfo_rooty()
                ),
                2,
            )

    def test_rebuilding_a_long_list_as_short_resets_scroll_to_top(self) -> None:
        parents = [
            new_entry(
                KIND_PARENT,
                f"親タスク {index + 1}",
                "2026-07-01",
                "2026-07-31",
                entry_id=f"long-parent-{index}",
            )
            for index in range(45)
        ]
        self.app.schedule = {"version": 3, "parents": parents, "todos": []}
        self.app._ensure_schedule_defaults()
        self.app._rebuild_rows()
        self._pump()
        self.app.rows_canvas.yview_moveto(1.0)
        self._pump()
        self.assertAlmostEqual(self.app.rows_canvas.yview()[1], 1.0, places=3)

        self.app.schedule = {
            "version": 3,
            "parents": [self.parent],
            "todos": [],
            "settings": {"row_height": 40},
        }
        self.app._ensure_schedule_defaults()
        self.app._rebuild_rows()
        self._pump()

        scroll_region = tuple(
            float(value)
            for value in self.app.rows_canvas.cget("scrollregion").split()
        )
        self.assertLessEqual(
            scroll_region[3] - scroll_region[1],
            self.app.rows_canvas.winfo_height(),
        )
        self.assertAlmostEqual(self.app.rows_canvas.yview()[0], 0.0, places=3)
        self.assertLessEqual(
            abs(
                self.app.row_widgets[0].container.winfo_rooty()
                - self.app.rows_canvas.winfo_rooty()
            ),
            2,
        )

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
        self.app.schedule = {"version": 3, "parents": parents, "todos": []}
        self.app._ensure_schedule_defaults()
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
        date_inputs = self._descendants_of_type(dialog, app_module.DateInput)
        self.assertEqual(len(date_inputs), 3)
        date_inputs[2].set_date(None)
        self.assertIsNone(date_inputs[2].get_date(required=False))
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

    def test_add_dialogs_are_centered_with_ok_on_left_and_todo_notify_on(self) -> None:
        self.root.geometry("1280x720+260+80")
        self._pump()

        for open_dialog in (
            lambda: self.app._open_entry_dialog(kind="parent"),
            lambda: self.app._open_todo_dialog(kind="parent"),
        ):
            with self.subTest(open_dialog=open_dialog):
                open_dialog()
                self._pump()
                dialog = next(
                    widget
                    for widget in self.root.winfo_children()
                    if isinstance(widget, tk.Toplevel)
                )
                expected_x = self.root.winfo_rootx() + (
                    self.root.winfo_width() - dialog.winfo_width()
                ) // 2
                expected_y = self.root.winfo_rooty() + (
                    self.root.winfo_height() - dialog.winfo_height()
                ) // 2
                self.assertEqual(dialog.winfo_x(), expected_x)
                self.assertEqual(dialog.winfo_y(), expected_y)

                buttons = {
                    button.cget("text"): button
                    for button in self._descendants_of_type(dialog, ttk.Button)
                    if button.cget("text") in (app_module.BUTTON_OK, app_module.BUTTON_CANCEL)
                }
                self.assertLess(
                    buttons[app_module.BUTTON_OK].winfo_rootx(),
                    buttons[app_module.BUTTON_CANCEL].winfo_rootx(),
                )

                if dialog.title() == "TODO追加":
                    notify_check = self._descendants_of_type(
                        dialog, ttk.Checkbutton
                    )[0]
                    self.assertTrue(
                        self.root.getvar(notify_check.cget("variable"))
                    )

                buttons[app_module.BUTTON_CANCEL].invoke()
                self._pump()
                self.assertFalse(dialog.winfo_exists())

    def test_settings_dialog_is_centered_on_parent_window(self) -> None:
        self.root.geometry("1280x720+260+80")
        self._pump()

        self.app._open_settings_dialog()
        self._pump()
        dialog = next(
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel)
        )
        expected_x = self.root.winfo_rootx() + (
            self.root.winfo_width() - dialog.winfo_width()
        ) // 2
        expected_y = self.root.winfo_rooty() + (
            self.root.winfo_height() - dialog.winfo_height()
        ) // 2

        self.assertEqual(str(dialog.transient()), str(self.root))
        self.assertEqual(dialog.winfo_x(), expected_x)
        self.assertEqual(dialog.winfo_y(), expected_y)

        cancel_button = next(
            button
            for button in self._descendants_of_type(dialog, ttk.Button)
            if button.cget("text") == app_module.BUTTON_CANCEL
        )
        cancel_button.invoke()
        self._pump()
        self.assertFalse(dialog.winfo_exists())

    def test_parent_and_child_date_inputs_keep_start_before_end(self) -> None:
        for kind, parent_id in (("parent", None), ("child", self.parent["id"])):
            with self.subTest(kind=kind):
                self.app._open_entry_dialog(kind=kind, parent_id=parent_id)
                self._pump()
                dialog = next(
                    widget
                    for widget in self.root.winfo_children()
                    if isinstance(widget, tk.Toplevel)
                )
                date_inputs = self._descendants_of_type(dialog, app_module.DateInput)
                start_input, end_input = date_inputs[:2]

                end_input.set_date(app_module.date(2026, 8, 4))
                start_input.set_date(app_module.date(2026, 8, 5))
                self.assertEqual(end_input.get_date(), app_module.date(2026, 8, 5))

                end_input.set_date(app_module.date(2026, 7, 20))
                self.assertEqual(start_input.get_date(), app_module.date(2026, 7, 20))

                end_input.set_date(app_module.date(2026, 7, 25))
                start_input.day_entry.focus_set()
                self._pump()
                start_input.day_entry.delete(0, "end")
                start_input.day_entry.insert(0, "30")
                end_input.year_entry.focus_set()
                start_input.day_entry.event_generate("<FocusOut>")
                self._pump()
                self.assertEqual(end_input.get_date(), app_module.date(2026, 7, 30))

                end_input.day_entry.focus_set()
                self._pump()
                end_input.day_entry.delete(0, "end")
                end_input.day_entry.insert(0, "10")
                start_input.year_entry.focus_set()
                end_input.day_entry.event_generate("<FocusOut>")
                self._pump()
                self.assertEqual(start_input.get_date(), app_module.date(2026, 7, 10))

                cancel = next(
                    button
                    for button in self._descendants_of_type(dialog, ttk.Button)
                    if button.cget("text") == app_module.BUTTON_CANCEL
                )
                cancel.invoke()
                self._pump()

    def test_parent_period_change_clamps_all_child_periods(self) -> None:
        self.app._on_edit(self.parent["id"])
        self._pump()
        dialog = next(
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel)
        )
        start_input, end_input = self._descendants_of_type(
            dialog,
            app_module.DateInput,
        )[:2]
        start_input.set_date(app_module.date(2026, 7, 10))
        end_input.set_date(app_module.date(2026, 7, 20))

        save_button = next(
            button
            for button in self._descendants_of_type(dialog, ttk.Button)
            if button.cget("style") == "Primary.TButton"
        )
        save_button.invoke()
        self._pump()

        self.assertEqual(
            (self.child_a["start"], self.child_a["end"]),
            (app_module.date(2026, 7, 10), app_module.date(2026, 7, 12)),
        )
        self.assertEqual(
            (self.child_b["start"], self.child_b["end"]),
            (app_module.date(2026, 7, 13), app_module.date(2026, 7, 20)),
        )
        self.assertFalse(dialog.winfo_exists())

    def test_child_creation_defaults_to_parent_start_and_expands_parent(self) -> None:
        parent = new_entry(
            KIND_PARENT,
            "親タスク",
            "2026-08-22",
            "2026-08-24",
            entry_id="parent-overrun",
        )
        self.app.schedule["parents"] = [parent]
        self.app._ensure_schedule_defaults()
        self.app._rebuild_rows()

        self.app._open_entry_dialog(kind="child", parent_id=parent["id"])
        self._pump()
        dialog = next(
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel)
        )
        all_entries = self._descendants_of_type(dialog, ttk.Entry)
        all_entries[0].delete(0, "end")
        all_entries[0].insert(0, "親期間外の子")
        start_input, end_input = self._descendants_of_type(
            dialog,
            app_module.DateInput,
        )[:2]
        notice = next(
            label
            for label in self._descendants_of_type(dialog, tk.Label)
            if label.cget("fg") == app_module.COLOR_WARNING
        )
        self.assertEqual(start_input.get_date(), app_module.date(2026, 8, 22))
        self.assertEqual(end_input.get_date(), app_module.date(2026, 8, 22))
        self.assertEqual(notice.cget("text"), "")

        start_input.set_date(app_module.date(2026, 8, 21))
        self.assertEqual(
            notice.cget("text"),
            "親スケジュールの開始日より前に1日はみ出しています。",
        )
        end_input.set_date(app_module.date(2026, 8, 25))
        self.assertEqual(
            notice.cget("text"),
            "親スケジュールの開始日より前に1日はみ出しています。\n"
            "親スケジュールの終了日より後に1日はみ出しています。",
        )

        start_input.day_entry.delete(0, "end")
        start_input.day_entry.event_generate("<KeyRelease>")
        self._pump()
        self.assertEqual(notice.cget("text"), "")
        start_input.set_date(app_module.date(2026, 8, 21))

        save_button = next(
            button
            for button in self._descendants_of_type(dialog, ttk.Button)
            if button.cget("style") == "Primary.TButton"
        )
        self.app._save.reset_mock()

        with patch.object(app_module.messagebox, "showerror") as showerror:
            save_button.invoke()
            self._pump()

        showerror.assert_not_called()
        self.app._save.assert_called_once_with()
        self.assertEqual(
            (parent["start"], parent["end"]),
            (app_module.date(2026, 8, 21), app_module.date(2026, 8, 25)),
        )
        self.assertEqual(len(parent["children"]), 1)
        self.assertEqual(
            (parent["children"][0]["start"], parent["children"][0]["end"]),
            (app_module.date(2026, 8, 21), app_module.date(2026, 8, 25)),
        )
        self.assertFalse(dialog.winfo_exists())

    def test_child_edit_shows_live_overrun_and_expands_parent(self) -> None:
        self.app._on_edit(self.child_a["id"])
        self._pump()
        dialog = next(
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel)
        )
        start_input, end_input = self._descendants_of_type(
            dialog,
            app_module.DateInput,
        )[:2]
        notice = next(
            label
            for label in self._descendants_of_type(dialog, tk.Label)
            if label.cget("fg") == app_module.COLOR_WARNING
        )

        start_input.set_date(app_module.date(2026, 6, 30))
        self.assertEqual(
            notice.cget("text"),
            "親スケジュールの開始日より前に1日はみ出しています。",
        )
        start_input.set_date(app_module.date(2026, 7, 1))
        self.assertEqual(notice.cget("text"), "")
        end_input.set_date(app_module.date(2026, 8, 1))
        self.assertEqual(
            notice.cget("text"),
            "親スケジュールの終了日より後に1日はみ出しています。",
        )
        start_input.set_date(app_module.date(2026, 6, 30))
        self.assertEqual(
            notice.cget("text"),
            "親スケジュールの開始日より前に1日はみ出しています。\n"
            "親スケジュールの終了日より後に1日はみ出しています。",
        )
        save_button = next(
            button
            for button in self._descendants_of_type(dialog, ttk.Button)
            if button.cget("style") == "Primary.TButton"
        )
        self.app._save.reset_mock()

        with patch.object(app_module.messagebox, "showerror") as showerror:
            save_button.invoke()
            self._pump()

        showerror.assert_not_called()
        self.app._save.assert_called_once_with()
        self.assertEqual(
            (self.child_a["start"], self.child_a["end"]),
            (app_module.date(2026, 6, 30), app_module.date(2026, 8, 1)),
        )
        self.assertEqual(
            (self.parent["start"], self.parent["end"]),
            (app_module.date(2026, 6, 30), app_module.date(2026, 8, 1)),
        )
        self.assertFalse(dialog.winfo_exists())

    def test_child_creation_rolls_back_parent_expansion_when_save_fails(self) -> None:
        original_child_ids = [child["id"] for child in self.parent["children"]]
        self.app._open_entry_dialog(kind="child", parent_id=self.parent["id"])
        self._pump()
        dialog = next(
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel)
        )
        all_entries = self._descendants_of_type(dialog, ttk.Entry)
        all_entries[0].insert(0, "保存失敗する子")
        start_input, end_input = self._descendants_of_type(
            dialog,
            app_module.DateInput,
        )[:2]
        start_input.set_date(app_module.date(2026, 6, 30))
        end_input.set_date(app_module.date(2026, 8, 1))
        save_button = next(
            button
            for button in self._descendants_of_type(dialog, ttk.Button)
            if button.cget("style") == "Primary.TButton"
        )
        self.app._save = Mock(return_value=False)

        save_button.invoke()
        self._pump()

        restored_parent = self.app.schedule["parents"][0]
        self.assertEqual(
            (restored_parent["start"], restored_parent["end"]),
            (app_module.date(2026, 7, 1), app_module.date(2026, 7, 31)),
        )
        self.assertEqual(
            [child["id"] for child in restored_parent["children"]],
            original_child_ids,
        )
        self.assertTrue(dialog.winfo_exists())

    def test_child_edit_rolls_back_parent_expansion_when_save_fails(self) -> None:
        self.app._on_edit(self.child_a["id"])
        self._pump()
        dialog = next(
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel)
        )
        start_input, end_input = self._descendants_of_type(
            dialog,
            app_module.DateInput,
        )[:2]
        start_input.set_date(app_module.date(2026, 6, 30))
        end_input.set_date(app_module.date(2026, 8, 1))
        save_button = next(
            button
            for button in self._descendants_of_type(dialog, ttk.Button)
            if button.cget("style") == "Primary.TButton"
        )
        self.app._save = Mock(return_value=False)

        save_button.invoke()
        self._pump()

        restored_parent = self.app.schedule["parents"][0]
        restored_child = restored_parent["children"][0]
        self.assertEqual(
            (restored_parent["start"], restored_parent["end"]),
            (app_module.date(2026, 7, 1), app_module.date(2026, 7, 31)),
        )
        self.assertEqual(
            (restored_child["start"], restored_child["end"]),
            (app_module.date(2026, 7, 2), app_module.date(2026, 7, 12)),
        )
        self.assertTrue(dialog.winfo_exists())

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

    def test_parent_with_children_shows_derived_started_date_as_read_only(self) -> None:
        self.assertEqual(
            self.app._completion_record(self.parent)[app_module.LOG_FIELD_STARTED],
            "2026-07-13",
        )
        self.app._on_edit(self.parent["id"])
        self._pump()

        dialog = next(
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel)
        )
        date_inputs = self._descendants_of_type(dialog, app_module.DateInput)
        self.assertEqual(date_inputs[2].get_date(required=False).isoformat(), "2026-07-13")
        self.assertEqual(
            [str(entry.cget("state")) for entry in date_inputs[2].entries],
            ["disabled", "disabled", "disabled"],
        )
        self.assertEqual(str(date_inputs[2].calendar_button.cget("state")), "disabled")
        self.assertIn(
            app_module.LABEL_STARTED_DATE_DERIVED,
            [
                label.cget("text")
                for label in self._descendants_of_type(dialog, tk.Label)
            ],
        )

        cancel = next(
            button
            for button in self._descendants_of_type(dialog, ttk.Button)
            if button.cget("text") == app_module.BUTTON_CANCEL
        )
        cancel.invoke()
        self._pump()

    def test_todo_dialog_edits_deadline_hour_and_minute(self) -> None:
        todo = new_todo_entry(
            KIND_PARENT,
            "時刻付きTODO",
            "2026-07-22T09:00",
            entry_id="todo-with-time",
        )
        self.app.schedule["todos"] = [todo]
        self.app._ensure_schedule_defaults()
        self.app._on_edit_todo(todo["id"])
        self._pump()

        dialog = next(
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel)
        )
        deadline_input = self._descendants_of_type(
            dialog, app_module.DateTimeInput
        )[0]
        self.assertEqual(
            deadline_input.get_datetime(),
            app_module.datetime(2026, 7, 22, 9, 0),
        )
        deadline_input.time_input.hour_var.set("24")
        with self.assertRaises(ValueError):
            deadline_input.get_datetime()
        deadline_input.set_datetime(app_module.datetime(2026, 7, 22, 10, 45))
        ok_button = next(
            button
            for button in self._descendants_of_type(dialog, ttk.Button)
            if button.cget("text") == app_module.BUTTON_OK
        )
        ok_button.invoke()
        self._pump()

        self.assertEqual(todo["deadline"], app_module.datetime(2026, 7, 22, 10, 45))

    def test_todo_tab_displays_hierarchy_and_notification_state(self) -> None:
        parent = new_todo_entry(
            KIND_PARENT,
            "親TODO",
            "2026-07-20",
            entry_id="todo-parent",
            notify=True,
        )
        parent["children"].append(
            new_todo_entry(
                KIND_CHILD,
                "子TODO",
                "2026-07-21",
                parent_id=parent["id"],
                entry_id="todo-child",
                notify=False,
            )
        )
        self.app.schedule["todos"] = [parent]
        self.app._ensure_schedule_defaults()
        self.app._rebuild_todo_rows()
        self.app._switch_mode("todo")
        self._pump()

        self.assertEqual(
            [row.task_label.cget("text") for row in self.app.todo_row_widgets],
            ["親TODO", "子TODO"],
        )
        self.assertEqual(
            [row.notify_button.cget("text") for row in self.app.todo_row_widgets],
            ["ON", "OFF"],
        )
        self.assertEqual(
            [row.deadline_label.cget("text") for row in self.app.todo_row_widgets],
            ["2026-07-20 00:00", "2026-07-21 00:00"],
        )
        self.assertTrue(self.app.todo_header.winfo_ismapped())
        self.assertFalse(self.app.header.winfo_ismapped())

    def test_schedule_multiselect_copy_feedback_and_shortcut_guards(self) -> None:
        self.app._select_from_event(self.parent["id"], SimpleNamespace(state=0))
        self.app._select_from_event(
            self.child_a["id"],
            SimpleNamespace(state=app_module.CONTROL_STATE_MASK),
        )
        self.assertEqual(
            self.app.selected_ids,
            {self.parent["id"], self.child_a["id"]},
        )
        self.assertEqual(self.app.selected_id, self.child_a["id"])

        self.assertEqual(self.app._on_copy_shortcut(), "break")
        self.assertEqual(len(self.app._schedule_clipboard), 1)
        self.assertEqual(self.app._schedule_clipboard[0]["id"], self.parent["id"])
        self.assertEqual(
            self.app.status_label.cget("text"),
            f"「{self.parent['task']}」をコピーしました。",
        )
        copied_task = self.app._schedule_clipboard[0]["task"]
        self.parent["task"] = "コピー後に変更"
        self.assertEqual(self.app._schedule_clipboard[0]["task"], copied_task)

        self.app._select_from_event(
            self.child_a["id"],
            SimpleNamespace(state=app_module.CONTROL_STATE_MASK),
        )
        self.assertEqual(self.app.selected_ids, {self.parent["id"]})
        clipboard_before = copy.deepcopy(self.app._schedule_clipboard)
        self.app._switch_mode("todo")
        self.assertIsNone(self.app._on_copy_shortcut())
        self.assertEqual(self.app._schedule_clipboard, clipboard_before)

        self.app._switch_mode("schedule")
        text_input = ttk.Entry(self.root)
        text_input.grid(row=99, column=0)
        text_input.focus_force()
        self._pump()
        self.assertIsNone(self.app._on_paste_shortcut())
        text_input.destroy()

    def test_schedule_paste_keeps_tree_fields_positions_and_rolls_back(self) -> None:
        self.parent["custom_parent_field"] = {"theme": "blue"}
        self.child_a["custom_child_field"] = ["保持", 1]
        self.app._select(self.parent["id"])
        self.app._on_copy_shortcut()
        self.app._select(self.child_a["id"])
        self.app._save.reset_mock()

        self.assertEqual(self.app._on_paste_shortcut(), "break")
        self.assertEqual(len(self.app.entries), 2)
        pasted_parent = self.app.entries[1]
        self.assertEqual(pasted_parent["task"], self.parent["task"])
        self.assertNotEqual(pasted_parent["id"], self.parent["id"])
        self.assertEqual(pasted_parent["custom_parent_field"], {"theme": "blue"})
        self.assertEqual(len(pasted_parent["children"]), 2)
        self.assertTrue(
            all(
                child["parent_id"] == pasted_parent["id"]
                and child["id"] not in {self.child_a["id"], self.child_b["id"]}
                for child in pasted_parent["children"]
            )
        )
        self.app._save.assert_called_once_with()

        self.app._select(self.child_a["id"])
        self.app._on_copy_shortcut()
        self.app._schedule_clipboard[0]["start"] = self.parent["start"] - timedelta(days=2)
        self.app._schedule_clipboard[0]["end"] = self.parent["end"] + timedelta(days=3)
        self.app._select(self.child_b["id"])
        self.parent["collapsed"] = True
        self.app._save.reset_mock()
        self.app._on_paste_shortcut()

        pasted_child = self.parent["children"][2]
        self.assertEqual(pasted_child["task"], self.child_a["task"])
        self.assertNotEqual(pasted_child["id"], self.child_a["id"])
        self.assertEqual(pasted_child["parent_id"], self.parent["id"])
        self.assertEqual(pasted_child["custom_child_field"], ["保持", 1])
        self.assertFalse(self.parent["collapsed"])
        self.assertEqual(self.parent["start"], pasted_child["start"])
        self.assertEqual(self.parent["end"], pasted_child["end"])

        self.app._select(self.child_a["id"])
        self.app._on_copy_shortcut()
        self.app._schedule_clipboard[0]["task"] = "非常に長い予定名" * 30
        self.app._select(self.parent["id"])
        self.app._select(self.child_b["id"], additive=True)
        schedule_before = copy.deepcopy(self.app.schedule)
        selected_before = set(self.app.selected_ids)
        primary_before = self.app.selected_id
        task_width_before = self.app.task_column_width
        self.app._save = Mock(return_value=False)

        self.app._on_paste_shortcut()

        self.assertEqual(self.app.schedule, schedule_before)
        self.assertEqual(self.app.selected_ids, selected_before)
        self.assertEqual(self.app.selected_id, primary_before)
        self.assertEqual(self.app.task_column_width, task_width_before)
        self.assertEqual(self.app.status_label.cget("text"), "貼り付けを元に戻しました。")

    def test_schedule_mixed_paste_preserves_source_order_by_kind(self) -> None:
        second_parent = new_entry(
            KIND_PARENT,
            "2番目の親",
            "2026-08-01",
            "2026-08-05",
            entry_id="parent-2",
        )
        second_child = new_entry(
            KIND_CHILD,
            "2番目の子",
            "2026-08-02",
            "2026-08-03",
            parent_id=second_parent["id"],
            entry_id="child-c",
        )
        second_parent["children"].append(second_child)
        self.app.entries.append(second_parent)
        self.app._rebuild_rows()
        self._pump()

        self.app._select(self.child_a["id"])
        self.app._select(second_parent["id"], additive=True)
        self.app._on_copy_shortcut()
        self.assertEqual(
            [entry["task"] for entry in self.app._schedule_clipboard],
            [self.child_a["task"], second_parent["task"]],
        )
        self.app._select(self.child_b["id"])
        self.app._on_paste_shortcut()

        pasted_child = self.parent["children"][2]
        pasted_parent = self.app.entries[1]
        self.assertEqual(pasted_child["task"], self.child_a["task"])
        self.assertEqual(pasted_parent["task"], second_parent["task"])
        self.assertEqual(self.app.entries[2]["id"], second_parent["id"])
        self.assertNotEqual(pasted_child["id"], self.child_a["id"])
        self.assertNotEqual(pasted_parent["id"], second_parent["id"])
        self.assertEqual(
            self.app.selected_ids,
            {pasted_child["id"], pasted_parent["id"]},
        )
        self.assertEqual(self.app.status_label.cget("text"), "2件の予定を貼り付けました。")

    def test_gantt_double_click_hit_testing_and_cursor(self) -> None:
        row = self.app.row_widgets[1]
        self.assertIsNotNone(row.gantt_bounds)
        x0, y0, x1, y1 = row.gantt_bounds
        center = SimpleNamespace(x=(x0 + x1) / 2, y=(y0 + y1) / 2)
        background = SimpleNamespace(x=(x0 + x1) / 2, y=0)
        with patch.object(self.app, "_on_edit") as edit:
            self.app._on_gantt_double_click(self.child_a["id"], background)
            edit.assert_not_called()
            self.app._on_gantt_double_click(self.child_a["id"], center)
            edit.assert_called_once_with(self.child_a["id"])
        self.assertEqual(self.app.selected_ids, {self.child_a["id"]})

        self.app._on_gantt_hover(
            self.child_a["id"],
            SimpleNamespace(x=x0 + 1, y=(y0 + y1) / 2),
        )
        self.assertEqual(row.gantt_canvas.cget("cursor"), "sb_h_double_arrow")
        self.app._on_gantt_hover(self.child_a["id"], center)
        self.assertEqual(row.gantt_canvas.cget("cursor"), "fleur")
        self.app._on_gantt_hover(self.child_a["id"], background)
        self.assertEqual(row.gantt_canvas.cget("cursor"), "arrow")

    def test_one_day_gantt_bar_body_moves_and_outer_edges_resize(self) -> None:
        standalone = new_entry(
            KIND_PARENT,
            "1日の予定",
            "2026-07-25",
            "2026-07-25",
            entry_id="one-day-parent",
        )
        self.app.entries.append(standalone)
        self.app._rebuild_rows()
        self._pump()

        row = self.app._row_widgets_for(standalone["id"])
        self.assertIsNotNone(row)
        x0, y0, x1, y1 = row.gantt_bounds
        y = (y0 + y1) / 2
        self.assertLessEqual(x1 - x0, app_module.GANTT_EDGE_HIT_PX * 2)
        self.assertEqual(
            self.app._gantt_hit_operation(row, (x0 + x1) / 2, y),
            "move",
        )
        self.assertEqual(
            self.app._gantt_hit_operation(row, x0 - 2, y),
            "resize_start",
        )
        self.assertEqual(
            self.app._gantt_hit_operation(row, x1 + 2, y),
            "resize_end",
        )

        original_start = standalone["start"]
        original_end = standalone["end"]
        self.app._on_gantt_press(
            standalone["id"],
            SimpleNamespace(
                x=(x0 + x1) / 2,
                y=y,
                x_root=500,
                state=0,
            ),
        )
        pixels_per_day = self.app._gantt_drag.pixels_per_day
        self.assertEqual(self.app._gantt_drag.operation, "move")
        self.app._on_gantt_motion(
            standalone["id"],
            SimpleNamespace(x_root=500 + pixels_per_day * 2),
        )
        self.app._on_gantt_release(standalone["id"], SimpleNamespace())

        self.assertEqual(standalone["start"], original_start + timedelta(days=2))
        self.assertEqual(standalone["end"], original_end + timedelta(days=2))
        self.assertEqual(standalone["end"] - standalone["start"], timedelta(0))

    def test_gantt_move_previews_then_moves_selected_parent_tree_once(self) -> None:
        unrelated = new_entry(
            KIND_PARENT,
            "移動対象外",
            "2026-07-08",
            "2026-07-10",
            entry_id="unrelated-parent",
        )
        self.app.entries.append(unrelated)
        self.app._rebuild_rows()
        self._pump()
        original_ranges = {
            entry["id"]: (entry["start"], entry["end"])
            for entry in (self.parent, self.child_a, self.child_b)
        }
        self.app._select(self.parent["id"])
        self.app._select(self.child_a["id"], additive=True)
        row = self.app.row_widgets[0]
        x0, y0, x1, y1 = row.gantt_bounds
        press = SimpleNamespace(
            x=(x0 + x1) / 2,
            y=(y0 + y1) / 2,
            x_root=500,
            state=0,
        )
        self.app._save.reset_mock()
        self.app._on_gantt_press(self.parent["id"], press)
        pixels_per_day = self.app._gantt_drag.pixels_per_day
        with patch.object(
            self.app,
            "_redraw_gantt_for",
            wraps=self.app._redraw_gantt_for,
        ) as redraw:
            self.app._on_gantt_motion(
                self.parent["id"],
                SimpleNamespace(x_root=500 + pixels_per_day * 2),
            )

        self.assertEqual(
            {item.args[0] for item in redraw.call_args_list},
            {self.parent["id"], self.child_a["id"], self.child_b["id"]},
        )
        self.assertNotIn(unrelated["id"], {item.args[0] for item in redraw.call_args_list})

        self.assertTrue(self.app._gantt_drag.active)
        self.assertEqual(self.app._gantt_drag.root_entry_ids, (self.parent["id"],))
        self.assertEqual(
            self.app._gantt_drag.preview_ranges[self.parent["id"]][0],
            original_ranges[self.parent["id"]][0] + timedelta(days=2),
        )
        for entry in (self.parent, self.child_a, self.child_b):
            self.assertEqual(
                (entry["start"], entry["end"]),
                original_ranges[entry["id"]],
            )

        row_containers = tuple(row.container for row in self.app.row_widgets)
        with patch.object(self.app, "_rebuild_rows") as rebuild:
            self.app._on_gantt_release(self.parent["id"], SimpleNamespace())
        rebuild.assert_not_called()
        self._pump()
        self.assertEqual(
            tuple(row.container for row in self.app.row_widgets),
            row_containers,
        )
        for entry in (self.parent, self.child_a, self.child_b):
            self.assertEqual(
                (entry["start"], entry["end"]),
                tuple(value + timedelta(days=2) for value in original_ranges[entry["id"]]),
            )
        self.app._save.assert_called_once_with()

        after_move = copy.deepcopy(self.app.schedule)
        self.app._select(self.parent["id"])
        row = self.app.row_widgets[0]
        x0, y0, x1, y1 = row.gantt_bounds
        self.app._on_gantt_press(
            self.parent["id"],
            SimpleNamespace(
                x=(x0 + x1) / 2,
                y=(y0 + y1) / 2,
                x_root=600,
                state=0,
            ),
        )
        pixels_per_day = self.app._gantt_drag.pixels_per_day
        self.app._on_gantt_motion(
            self.parent["id"],
            SimpleNamespace(x_root=600 - pixels_per_day * 3),
        )
        self.assertEqual(self.app._on_row_drag_escape(), "break")
        self.assertEqual(self.app.schedule, after_move)
        self.assertIsNone(self.app._gantt_drag)

    def test_gantt_zero_drop_and_multiple_child_move(self) -> None:
        self.app._select(self.parent["id"])
        self.app._select(self.child_a["id"], additive=True)
        parent_row = self.app.row_widgets[0]
        x0, y0, x1, y1 = parent_row.gantt_bounds
        self.app._save.reset_mock()
        self.app._on_gantt_press(
            self.parent["id"],
            SimpleNamespace(
                x=(x0 + x1) / 2,
                y=(y0 + y1) / 2,
                x_root=500,
                state=0,
            ),
        )
        self.app._on_gantt_release(self.parent["id"], SimpleNamespace())
        self.assertEqual(self.app.selected_ids, {self.parent["id"]})
        self.app._save.assert_not_called()

        original_parent_start = self.parent["start"]
        original_ranges = {
            child["id"]: (child["start"], child["end"], child["started"])
            for child in (self.child_a, self.child_b)
        }
        self.app._select(self.child_a["id"])
        self.app._select(self.child_b["id"], additive=True)
        child_row = self.app.row_widgets[2]
        x0, y0, x1, y1 = child_row.gantt_bounds
        self.app._on_gantt_press(
            self.child_b["id"],
            SimpleNamespace(
                x=(x0 + x1) / 2,
                y=(y0 + y1) / 2,
                x_root=700,
                state=0,
            ),
        )
        pixels_per_day = self.app._gantt_drag.pixels_per_day
        self.app._on_gantt_motion(
            self.child_b["id"],
            SimpleNamespace(x_root=700 + pixels_per_day * 10),
        )
        self.app._on_gantt_release(self.child_b["id"], SimpleNamespace())
        self._pump()

        for child in (self.child_a, self.child_b):
            old_start, old_end, old_started = original_ranges[child["id"]]
            self.assertEqual(child["start"], old_start + timedelta(days=10))
            self.assertEqual(child["end"], old_end + timedelta(days=10))
            self.assertEqual(child["started"], old_started)
        self.assertEqual(self.parent["start"], original_parent_start)
        self.assertEqual(self.parent["end"], self.child_b["end"])
        self.app._save.assert_called_once_with()

    def test_gantt_resize_clamps_parent_expands_child_and_restores_failure(self) -> None:
        parent_row = self.app.row_widgets[0]
        x0, y0, _x1, y1 = parent_row.gantt_bounds
        self.app._on_gantt_press(
            self.parent["id"],
            SimpleNamespace(x=x0 + 1, y=(y0 + y1) / 2, x_root=400, state=0),
        )
        pixels_per_day = self.app._gantt_drag.pixels_per_day
        self.app._on_gantt_motion(
            self.parent["id"],
            SimpleNamespace(x_root=400 + pixels_per_day * 5),
        )
        self.app._on_gantt_release(self.parent["id"], SimpleNamespace())
        self._pump()
        self.assertEqual(self.parent["start"], app_module.date(2026, 7, 6))
        self.assertEqual(self.child_a["start"], self.parent["start"])

        self.app._select(self.child_b["id"])
        child_row = next(
            row for row in self.app.row_widgets if row.entry_id == self.child_b["id"]
        )
        _x0, y0, x1, y1 = child_row.gantt_bounds
        child_a_range = (self.child_a["start"], self.child_a["end"])
        self.app._select(self.child_a["id"], additive=True)
        self.app._on_gantt_press(
            self.child_b["id"],
            SimpleNamespace(x=x1 - 1, y=(y0 + y1) / 2, x_root=700, state=0),
        )
        pixels_per_day = self.app._gantt_drag.pixels_per_day
        self.app._on_gantt_motion(
            self.child_b["id"],
            SimpleNamespace(x_root=700 + pixels_per_day * 10),
        )
        self.app._on_gantt_release(self.child_b["id"], SimpleNamespace())
        self._pump()
        self.assertEqual(self.child_b["end"], app_module.date(2026, 8, 3))
        self.assertEqual(self.parent["end"], self.child_b["end"])
        self.assertEqual((self.child_a["start"], self.child_a["end"]), child_a_range)

        self.app._select(self.parent["id"])
        schedule_before = copy.deepcopy(self.app.schedule)
        selection_before = set(self.app.selected_ids)
        primary_before = self.app.selected_id
        child_row = next(
            row for row in self.app.row_widgets if row.entry_id == self.child_b["id"]
        )
        x0, y0, x1, y1 = child_row.gantt_bounds
        self.app._save = Mock(return_value=False)
        self.app._on_gantt_press(
            self.child_b["id"],
            SimpleNamespace(
                x=(x0 + x1) / 2,
                y=(y0 + y1) / 2,
                x_root=800,
                state=0,
            ),
        )
        pixels_per_day = self.app._gantt_drag.pixels_per_day
        self.app._on_gantt_motion(
            self.child_b["id"],
            SimpleNamespace(x_root=800 + pixels_per_day),
        )
        self.app._on_gantt_release(self.child_b["id"], SimpleNamespace())
        self.assertEqual(self.app.schedule, schedule_before)
        self.assertEqual(self.app.selected_ids, selection_before)
        self.assertEqual(self.app.selected_id, primary_before)
        self.assertEqual(self.app.status_label.cget("text"), "日付変更を元に戻しました。")

    def test_gantt_bar_height_and_measured_labels_follow_row_height(self) -> None:
        for row_height in (30, 40, 72):
            self.app.row_content_height = row_height
            self.app.schedule["settings"]["row_height"] = row_height
            self.app._rebuild_rows()
            self._pump()

            parent_row, child_row = self.app.row_widgets[:2]
            parent_height = parent_row.gantt_bounds[3] - parent_row.gantt_bounds[1]
            child_height = child_row.gantt_bounds[3] - child_row.gantt_bounds[1]
            self.assertGreater(parent_height, child_height)
            self.assertGreaterEqual(
                child_height,
                self.app.small_font.metrics("linespace") + 5,
            )
            self.assertLess(parent_height, row_height)
            self.assertTrue(parent_row.gantt_canvas.find_withtag("gantt_bar"))
            text_items = parent_row.gantt_canvas.find_withtag("gantt_label")
            self.assertTrue(text_items)
            x0, _y0, x1, _y1 = parent_row.gantt_bounds
            text_bbox = parent_row.gantt_canvas.bbox(text_items[0])
            self.assertGreaterEqual(text_bbox[0], x0)
            self.assertLessEqual(text_bbox[2], x1)
            self.assertEqual(
                parent_row.gantt_canvas.itemcget(text_items[0], "text"),
                "31日・40%",
            )

    def test_short_gantt_label_moves_outside_and_parent_colors_show_children(self) -> None:
        standalone = new_entry(
            KIND_PARENT,
            "子を持たない親",
            "2026-07-25",
            "2026-07-25",
            entry_id="standalone-parent",
            progress_mode="value",
            progress_value=3,
            progress_total=4,
        )
        self.app.entries.append(standalone)
        self.app._rebuild_rows()
        self._pump()

        group_row = self.app.row_widgets[0]
        child_row = self.app.row_widgets[1]
        standalone_row = self.app.row_widgets[3]

        def polygon_fills(row) -> list[str]:
            return [
                row.gantt_canvas.itemcget(item, "fill").upper()
                for item in row.gantt_canvas.find_withtag("gantt_bar")
                if row.gantt_canvas.type(item) == "polygon"
            ]

        self.assertEqual(
            polygon_fills(group_row),
            [app_module.COLOR_PARENT_REMAINING, app_module.COLOR_PARENT_COMPLETE],
        )
        self.assertEqual(
            polygon_fills(child_row),
            [app_module.COLOR_CHILD_REMAINING, app_module.COLOR_CHILD_COMPLETE],
        )
        self.assertEqual(
            polygon_fills(standalone_row),
            [
                app_module.COLOR_PARENT_WITHOUT_CHILDREN_REMAINING,
                app_module.COLOR_PARENT_WITHOUT_CHILDREN_COMPLETE,
            ],
        )

        label_items = standalone_row.gantt_canvas.find_withtag("gantt_label")
        self.assertEqual(len(label_items), 1)
        self.assertEqual(
            standalone_row.gantt_canvas.itemcget(label_items[0], "text"),
            "1日・75%",
        )
        _x0, _y0, x1, _y1 = standalone_row.gantt_bounds
        label_bbox = standalone_row.gantt_canvas.bbox(label_items[0])
        self.assertGreater(label_bbox[0], x1)

        self.app._select(standalone["id"])
        self.assertEqual(
            polygon_fills(standalone_row),
            [
                app_module.COLOR_PARENT_WITHOUT_CHILDREN_REMAINING,
                app_module.COLOR_PARENT_WITHOUT_CHILDREN_COMPLETE,
            ],
        )

    def test_short_gantt_labels_choose_available_side_at_date_limits(self) -> None:
        left_entry = new_entry(
            KIND_PARENT,
            "左端",
            app_module.date.min,
            app_module.date.min,
            entry_id="left-limit",
        )
        right_entry = new_entry(
            KIND_PARENT,
            "右端",
            app_module.date.max,
            app_module.date.max,
            entry_id="right-limit",
        )
        self.app.schedule = {
            "version": 4,
            "parents": [left_entry, right_entry],
            "todos": [],
            "settings": {"row_height": 40},
        }
        self.app._ensure_schedule_defaults()
        self.app._rebuild_rows()
        self._pump()

        left_row, right_row = self.app.row_widgets
        left_label = left_row.gantt_canvas.find_withtag("gantt_label")[0]
        right_label = right_row.gantt_canvas.find_withtag("gantt_label")[0]
        left_bbox = left_row.gantt_canvas.bbox(left_label)
        right_bbox = right_row.gantt_canvas.bbox(right_label)
        left_x1 = left_row.gantt_bounds[2]
        right_x0 = right_row.gantt_bounds[0]

        self.assertGreater(left_bbox[0], left_x1)
        self.assertLess(right_bbox[2], right_x0)

    def test_large_schedule_reuses_render_lookups_and_redraws_changed_selection(self) -> None:
        parents = [
            new_entry(
                KIND_PARENT,
                f"大量表示 {index + 1}",
                "2026-07-01",
                "2026-07-03",
                entry_id=f"large-parent-{index}",
            )
            for index in range(120)
        ]
        self.app.schedule = {
            "version": 4,
            "parents": parents,
            "todos": [],
            "settings": {"row_height": 40},
        }
        self.app._ensure_schedule_defaults()
        with patch.object(
            self.app,
            "_timeline_range",
            wraps=self.app._timeline_range,
        ) as build_timeline_range:
            self.app._rebuild_rows()
            self._pump()

        self.assertEqual(len(self.app.row_widgets), 120)
        self.assertEqual(len(self.app._row_widgets_by_id), 120)
        self.assertEqual(len(self.app._row_entries_by_id), 120)
        self.assertLess(build_timeline_range.call_count, 10)
        with (
            patch.object(
                self.app,
                "_timeline_range",
                wraps=self.app._timeline_range,
            ) as timeline_range,
            patch.object(
                self.app,
                "_find",
                side_effect=AssertionError("描画中の全件検索は不要です"),
            ),
        ):
            self.app._redraw_all_gantt()
        timeline_range.assert_called_once_with()

        first_id = parents[0]["id"]
        last_id = parents[-1]["id"]
        self.app._select(first_id)
        with patch.object(
            self.app,
            "_redraw_gantt_for",
            wraps=self.app._redraw_gantt_for,
        ) as redraw:
            self.app._select(last_id)
        self.assertEqual(
            {item.args[0] for item in redraw.call_args_list},
            {first_id, last_id},
        )

    def _descendants_of_type(self, widget: tk.Misc, widget_type: type) -> list:
        matches = []
        for child in widget.winfo_children():
            if isinstance(child, widget_type):
                matches.append(child)
            matches.extend(self._descendants_of_type(child, widget_type))
        return matches

    def _cancel_scheduled_callbacks(self) -> None:
        for after_id in tuple(self.app._after_ids):
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        self.app._after_ids.clear()


if __name__ == "__main__":
    unittest.main()

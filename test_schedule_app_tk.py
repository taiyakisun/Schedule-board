from __future__ import annotations

import gc
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

    def _row_splitter_x(self, widgets: app_module.RowWidgets) -> int:
        column_box = widgets.container.grid_bbox(6, 0, 6, 0)
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
        self.assertTrue(self.app.todo_header.winfo_ismapped())
        self.assertFalse(self.app.header.winfo_ismapped())

    def _descendants_of_type(self, widget: tk.Misc, widget_type: type) -> list:
        matches = []
        for child in widget.winfo_children():
            if isinstance(child, widget_type):
                matches.append(child)
            matches.extend(self._descendants_of_type(child, widget_type))
        return matches


if __name__ == "__main__":
    unittest.main()

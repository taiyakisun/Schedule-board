from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from excel_export import HEADERS, MAIN_NS, export_to_excel


NS = {"m": MAIN_NS}


class ExcelExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.output = Path(self.temporary_directory.name) / "schedule.xlsx"

    def test_exports_grouped_gantt_as_valid_openxml_package(self) -> None:
        parents = [
            {
                "task": "親A",
                "start": "2026-07-01",
                "end": "2026-07-03",
                "visible": True,
                "collapsed": True,
                "progress_mode": "percent",
                "progress_current": 50,
                "children": [
                    {
                        "task": "子A-1",
                        "start": "2026-07-02",
                        "end": "2026-07-04",
                        "visible": True,
                        "progress": {"mode": "custom", "current": 1, "total": 3},
                    },
                    {
                        "task": "子A-2",
                        "start": "2026-07-01",
                        "end": "2026-07-02",
                        "visible": False,
                        "progress_current": 100,
                    },
                ],
            },
            {
                "task": "親B",
                "start": date(2026, 7, 5),
                "end": date(2026, 7, 6),
                "visible": False,
                "expanded": True,
                "progress_current": 0,
                "children": [
                    {
                        "task": "子B-1",
                        "start": "2026-07-05",
                        "end": "2026-07-05",
                        "visible": True,
                        "progress_current": 100,
                    }
                ],
            },
        ]

        result = export_to_excel(parents, date(2026, 7, 5), self.output)

        self.assertEqual(result, self.output)
        self.assertTrue(result.is_file())
        with zipfile.ZipFile(result) as archive:
            self.assertIsNone(archive.testzip())
            required_parts = {
                "[Content_Types].xml",
                "_rels/.rels",
                "docProps/app.xml",
                "docProps/core.xml",
                "xl/workbook.xml",
                "xl/_rels/workbook.xml.rels",
                "xl/styles.xml",
                "xl/worksheets/sheet1.xml",
            }
            self.assertEqual(required_parts, set(archive.namelist()))
            for name in archive.namelist():
                ET.fromstring(archive.read(name))
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            styles = ET.fromstring(archive.read("xl/styles.xml"))

        self.assertEqual(sheet.find("m:dimension", NS).get("ref"), "A1:L6")
        pane = sheet.find("m:sheetViews/m:sheetView/m:pane", NS)
        self.assertEqual(pane.get("xSplit"), "6")
        self.assertEqual(pane.get("ySplit"), "1")
        self.assertEqual(pane.get("topLeftCell"), "G2")
        self.assertEqual(pane.get("state"), "frozen")
        self.assertEqual(sheet.find("m:autoFilter", NS).get("ref"), "A1:L6")

        columns = sheet.findall("m:cols/m:col", NS)
        columns_by_index = {column.get("min"): column for column in columns}
        self.assertEqual(columns_by_index["1"].get("width"), "40")
        self.assertEqual(columns_by_index["4"].get("width"), "8")
        date_columns = columns_by_index["7"]
        self.assertEqual(date_columns.get("max"), "12")
        self.assertEqual(date_columns.get("width"), "4.2")

        rows = {int(row.get("r")): row for row in sheet.findall("m:sheetData/m:row", NS)}
        self.assertEqual(rows[2].get("collapsed"), "1")
        self.assertEqual(rows[3].get("outlineLevel"), "1")
        self.assertEqual(rows[3].get("hidden"), "1")
        self.assertEqual(rows[4].get("hidden"), "1")
        self.assertEqual(rows[6].get("outlineLevel"), "1")
        self.assertIsNone(rows[6].get("hidden"))

        cells = {
            cell.get("r"): cell
            for row in rows.values()
            for cell in row.findall("m:c", NS)
        }
        self.assertEqual(tuple(self._cell_value(cells[f"{column}1"]) for column in "ABCDEF"), HEADERS)
        self.assertNotIn("表示状態", HEADERS)
        self.assertEqual(self._cell_value(cells["A2"]), "▸ 親A")
        self.assertEqual(self._cell_value(cells["A3"]), "├─ 子A-1")
        self.assertEqual(self._cell_value(cells["A4"]), "└─ 子A-2")
        self.assertNotIn("親A", self._cell_value(cells["A3"]))
        self.assertEqual(self._cell_value(cells["A5"]), "▾ 親B")
        self.assertEqual(self._cell_value(cells["D2"]), "67%")
        self.assertAlmostEqual(float(self._cell_value(cells["E2"])), 2 / 3)
        self.assertEqual(self._cell_value(cells["D5"]), "100%")
        self.assertEqual(float(self._cell_value(cells["E5"])), 1.0)
        self.assertEqual(int(self._cell_value(cells["F2"])), 2)
        self.assertEqual(int(self._cell_value(cells["G1"])), 46204)

        self.assertEqual(self._fill_color(cells["G2"], styles), "FF2E7D32")
        self.assertEqual(self._fill_color(cells["H2"], styles), "FF2E7D32")
        self.assertEqual(self._fill_color(cells["I2"], styles), "FFA5D6A7")
        self.assertEqual(self._fill_color(cells["H3"], styles), "FF2E7D32")
        self.assertEqual(self._fill_color(cells["I3"], styles), "FFA5D6A7")
        self.assertNotIn("G4", cells)
        self.assertNotIn("K5", cells)
        self.assertNotIn("K6", cells)

        cell_xfs = styles.find("m:cellXfs", NS)
        parent_title_xf = cell_xfs[int(cells["A2"].get("s"))]
        font_id = int(parent_title_xf.get("fontId"))
        fonts = styles.find("m:fonts", NS)
        self.assertIsNotNone(fonts[font_id].find("m:b", NS))
        child_title_xf = cell_xfs[int(cells["A3"].get("s"))]
        self.assertEqual(child_title_xf.find("m:alignment", NS).get("indent"), "1")

    def test_exports_empty_parent_array(self) -> None:
        export_to_excel([], "2026-07-05", self.output)

        with zipfile.ZipFile(self.output) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        self.assertEqual(sheet.find("m:dimension", NS).get("ref"), "A1:F1")
        self.assertEqual(sheet.find("m:autoFilter", NS).get("ref"), "A1:F1")
        self.assertEqual(len(sheet.findall("m:sheetData/m:row", NS)), 1)

    def test_expands_row_height_for_wrapped_tree_title(self) -> None:
        parents = [
            {
                "task": "長い日本語タイトル" * 5,
                "start": "2026-07-01",
                "end": "2026-07-01",
                "children": [],
            }
        ]
        export_to_excel(parents, "2026-07-01", self.output)

        with zipfile.ZipFile(self.output) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        task_row = sheet.find("m:sheetData/m:row[@r='2']", NS)
        self.assertGreater(int(task_row.get("ht")), 20)

    def test_declares_outline_level_for_expanded_children(self) -> None:
        parents = [
            {
                "task": "親",
                "start": "2026-07-01",
                "end": "2026-07-02",
                "expanded": True,
                "children": [
                    {
                        "task": "子",
                        "start": "2026-07-01",
                        "end": "2026-07-01",
                    }
                ],
            }
        ]
        export_to_excel(parents, "2026-07-01", self.output)

        with zipfile.ZipFile(self.output) as archive:
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        sheet_format = sheet.find("m:sheetFormatPr", NS)
        child_row = sheet.find("m:sheetData/m:row[@r='3']", NS)
        self.assertEqual(sheet_format.get("outlineLevelRow"), "1")
        self.assertEqual(child_row.get("outlineLevel"), "1")
        self.assertIsNone(child_row.get("hidden"))

    def test_rejects_invalid_schedule_and_progress(self) -> None:
        invalid_schedule = [
            {"task": "親", "start": "2026-07-02", "end": "2026-07-01", "children": []}
        ]
        with self.assertRaisesRegex(ValueError, "endはstart以降"):
            export_to_excel(invalid_schedule, "2026-07-05", self.output)

        invalid_progress = [
            {
                "task": "親",
                "start": "2026-07-01",
                "end": "2026-07-02",
                "progress": {"mode": "custom", "current": 4, "total": 3},
                "children": [],
            }
        ]
        with self.assertRaisesRegex(ValueError, "0からprogress_total"):
            export_to_excel(invalid_progress, "2026-07-05", self.output)

    @staticmethod
    def _cell_value(cell: ET.Element) -> str:
        inline_text = cell.find("m:is/m:t", NS)
        if inline_text is not None:
            return inline_text.text or ""
        value = cell.find("m:v", NS)
        return "" if value is None else value.text or ""

    @staticmethod
    def _fill_color(cell: ET.Element, styles: ET.Element) -> str | None:
        cell_xfs = styles.find("m:cellXfs", NS)
        style = cell_xfs[int(cell.get("s"))]
        fill_id = int(style.get("fillId"))
        fills = styles.find("m:fills", NS)
        color = fills[fill_id].find("m:patternFill/m:fgColor", NS)
        return None if color is None else color.get("rgb")


if __name__ == "__main__":
    unittest.main()

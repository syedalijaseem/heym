import unittest

from app.services.markdown_task_list import (
    has_task_items,
    parse_task_line_indices,
    toggle_task_item,
)


class MarkdownTaskListTests(unittest.TestCase):
    def test_has_task_items(self):
        self.assertFalse(has_task_items("plain text"))
        self.assertTrue(has_task_items("- [ ] todo\n- [x] done"))

    def test_parse_task_line_indices(self):
        md = "intro\n- [ ] one\n- [x] two\n\nother"
        self.assertEqual(parse_task_line_indices(md), [1, 2])

    def test_toggle_unchecked_to_checked(self):
        md = "- [ ] Seçenek 2\n- [ ] Seçenek 3"
        result = toggle_task_item(md, 0)
        self.assertEqual(result, "- [x] Seçenek 2\n- [ ] Seçenek 3")

    def test_toggle_checked_to_unchecked(self):
        md = "- [x] Seçili seçenek\n- [ ] Seçenek 2"
        result = toggle_task_item(md, 0)
        self.assertEqual(result, "- [ ] Seçili seçenek\n- [ ] Seçenek 2")

    def test_toggle_uppercase_x(self):
        md = "- [X] done"
        result = toggle_task_item(md, 0)
        self.assertEqual(result, "- [ ] done")

    def test_toggle_asterisk_bullet(self):
        md = "* [ ] item"
        result = toggle_task_item(md, 0)
        self.assertEqual(result, "* [x] item")

    def test_toggle_invalid_index_raises(self):
        with self.assertRaises(ValueError):
            toggle_task_item("- [ ] ok", 5)

    def test_toggle_non_task_line_raises(self):
        with self.assertRaises(ValueError):
            toggle_task_item("- plain bullet", 0)

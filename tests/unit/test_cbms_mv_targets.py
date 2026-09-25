# -*- coding: utf-8 -*-
import unittest
from references.cbms_mv.cbms_mv_targets import (
    resolve_target_columns,
    get_rule_category,
    get_category_info,
    CBMS_MV_CATEGORIES,
)


class TestCbmsMvTargets(unittest.TestCase):
    def test_resolve_from_custom_target_fields(self):
        fields = ["fid", "sf_longitude", "sf_latitude", "sf_status"]
        result = resolve_target_columns("any_rule", fields, custom_target_fields=["longitude"])
        self.assertEqual(result, ["sf_longitude"])

    def test_resolve_multiple_target_fields(self):
        fields = ["fid", "sf_longitude", "sf_latitude", "ea_geocode", "sf_status"]
        result = resolve_target_columns("any_rule", fields, custom_target_fields=["longitude", "ea_geocode"])
        self.assertEqual(result, ["sf_longitude", "ea_geocode"])

    def test_resolve_preserves_table_order(self):
        fields = ["fid", "ea_geocode", "sf_latitude", "sf_longitude"]
        result = resolve_target_columns("any_rule", fields, custom_target_fields=["longitude", "ea_geocode"])
        self.assertEqual(result, ["ea_geocode", "sf_longitude"])

    def test_resolve_exact_match_fallback(self):
        fields = ["fid", "longitude", "latitude"]
        result = resolve_target_columns("any_rule", fields, custom_target_fields=["longitude"])
        self.assertEqual(result, ["longitude"])

    def test_empty_when_no_match(self):
        fields = ["fid", "building_type", "status"]
        result = resolve_target_columns("any_rule", fields, custom_target_fields=["non_existent_field"])
        self.assertEqual(result, [])


    def test_all_19_algorithms_have_target_fields(self):
        import glob
        import ast

        rule_scripts = [
            f for f in glob.glob("gmd_scripts/cbms_mv/*.py")
            if not f.endswith("__init__.py")
        ]
        self.assertEqual(len(rule_scripts), 19, f"Expected 19 algorithm scripts, found {len(rule_scripts)}")

        for script_path in rule_scripts:
            with open(script_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=script_path)
            target_fields_node = None
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "TARGET_FIELDS":
                            target_fields_node = node.value
                            break
            self.assertIsNotNone(
                target_fields_node,
                f"{script_path} is missing TARGET_FIELDS = [...]"
            )
            self.assertIsInstance(
                target_fields_node,
                ast.List,
                f"{script_path} TARGET_FIELDS is not a list"
            )
            self.assertTrue(
                len(target_fields_node.elts) > 0,
                f"{script_path} TARGET_FIELDS list is empty"
            )

    def test_no_emojis_in_cbmsmv_ui_files(self):
        import re
        emoji_pattern = re.compile(r"[\U00010000-\U0010ffff]|[\u2600-\u26ff]|[\u2700-\u27bf]")
        files = [
            r"references/cbms_mv/cbmsmv_dialog.py",
            r"references/cbms_mv/cbmsmv_review_dock.py",
        ]
        for path in files:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line_no, line in enumerate(lines, 1):
                # allow comments if any, but string literals shouldn't have emoji
                matches = emoji_pattern.findall(line)
                self.assertEqual(
                    matches,
                    [],
                    f"Unexpected emoji {matches} found in {path} at line {line_no}: {line.strip()}"
                )


    def test_get_rule_category(self):
        self.assertEqual(get_rule_category("mv_2027_hp_1a_map_uuid__missing"), "missing")
        self.assertEqual(get_rule_category("mv_2027_hp_1a_longitude__invalid"), "invalid")
        self.assertEqual(get_rule_category("mv_2027_hp_4a_longitude__duplicate"), "duplicate")
        self.assertEqual(get_rule_category("mv_2027_hp_4a_remarks__for_recoding"), "for_recoding")
        self.assertEqual(get_rule_category("mv_2027_hp_4a_remarks__for_checking"), "for_checking")
        self.assertEqual(get_rule_category("mv_2027_hp_4a_section__unexpected"), "unexpected")
        self.assertEqual(get_rule_category("mv_2027_hp_4a_count__outlier"), "outlier")
        self.assertEqual(get_rule_category("mv_2027_hp_4a_boundary__mismatch"), "mismatch")
        self.assertEqual(get_rule_category("mv_legacy_custom_rule"), "other")

    def test_get_category_info(self):
        info_missing = get_category_info("missing")
        self.assertEqual(info_missing["label"], "Missing / Blank")
        self.assertTrue(info_missing["icon"].endswith(".svg"))

        info_duplicate = get_category_info("duplicate")
        self.assertEqual(info_duplicate["label"], "Duplicate Records")
        self.assertTrue(info_duplicate["icon"].endswith(".svg"))

        info_fallback = get_category_info("unknown_custom_category")
        self.assertEqual(info_fallback["label"], "Unknown Custom Category")
        self.assertTrue(info_fallback["icon"].endswith(".svg"))

    def test_all_19_algorithms_categorized(self):
        import glob
        import os

        rule_scripts = [
            f for f in glob.glob("gmd_scripts/cbms_mv/*.py")
            if not f.endswith("__init__.py")
        ]
        self.assertEqual(len(rule_scripts), 19)
        for script_path in rule_scripts:
            val_id = os.path.splitext(os.path.basename(script_path))[0]
            cat = get_rule_category(val_id)
            self.assertIn(
                cat,
                CBMS_MV_CATEGORIES,
                f"Rule {val_id} categorized as '{cat}' which is not in CBMS_MV_CATEGORIES"
            )

    def test_no_float_point_size_in_qfont(self):
        import re
        float_qfont_pattern = re.compile(r"QFont\([^)]*,\s*[0-9]+\.[0-9]+")
        files = [
            r"references/cbms_mv/cbmsmv_dialog.py",
            r"references/cbms_mv/cbmsmv_review_dock.py",
        ]
        for path in files:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line_no, line in enumerate(lines, 1):
                matches = float_qfont_pattern.findall(line)
                self.assertEqual(
                    matches,
                    [],
                    f"Unexpected float pointSize in QFont {matches} found in {path} at line {line_no}: {line.strip()}"
                )


if __name__ == "__main__":
    unittest.main()


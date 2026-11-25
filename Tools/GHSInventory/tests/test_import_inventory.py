"""Regression tests for the offline GHS inventory import contract."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE = Path(__file__).resolve().parents[1] / "import_inventory.py"
HEADERS = "warehouse_id,warehouse_code,location_id,location_code,location_name,warehouse_area_id,location_type,location_status,usage_model,location_row,location_col,location_layer,horizontal_num,passage,double_shelves_position,x_axis,y_axis,z_axis,location_length_m,location_width_m,location_height_m,maximum_tray_num,maximum_volume_cbm,inventory_item_id,sku,quantity,available_quantity,allocation_quantity,freeze_quantity,wait_move_in_quantity,wait_move_out_quantity,inventory_updated_at_utc8,location_updated_at,location_etl_at,scene_mapping_status,ue_scene_target_id,ue_cad_instance_id,ue_slot_level,ue_slot_column".split(",")


def row(location="129", record="1", quantity="2", **overrides):
    result = dict.fromkeys(HEADERS, "")
    result.update(warehouse_id="108", warehouse_code="GHS_CA_US", location_id=location,
                  location_code="GHS-R24-69-02", warehouse_area_id="450", location_type="2",
                  location_status="1", usage_model="1", location_row="69", location_col="24",
                  location_layer="2", horizontal_num="23", location_length_m="1.2192",
                  location_width_m="1.0160", location_height_m="2.1590", maximum_volume_cbm="1.8721",
                  location_updated_at="2026-11-12 16:01:48.0", location_etl_at="2026-11-12 17:02:56.843",
                  scene_mapping_status="unmapped")
    if record:
        result.update(inventory_item_id=record, sku="000123", quantity=quantity,
                      available_quantity=quantity, allocation_quantity="0", freeze_quantity="0",
                      wait_move_in_quantity="0", wait_move_out_quantity="0",
                      inventory_updated_at_utc8="2026-11-25 10:16:51.0")
    result.update(overrides)
    return result


class InventoryImportTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.is_file(), "Offline inventory importer must exist")
        spec = importlib.util.spec_from_file_location("ghs_inventory_importer", MODULE)
        self.importer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.importer)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.csv = self.root / "snapshot.csv"
        self.out = self.root / "inventory"

    def write(self, rows, headers=HEADERS, encoding="utf-8-sig"):
        with self.csv.open("w", newline="", encoding=encoding) as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    def run_import(self, rows):
        self.write(rows)
        self.importer.import_inventory(self.csv, self.out)
        return json.loads((self.out / "index.json").read_text("utf8"))

    def details(self, index, position=0):
        brief = index["locations"][position]
        shard = json.loads((self.out / brief["shard"]).read_text("utf8"))
        self.assertEqual(shard["snapshotId"], index["snapshotId"])
        return shard["locations"][brief["id"]]

    def test_frozen_stock_is_occupied_even_when_all_available_quantities_are_zero(self):
        rows = [row(str(i + 128), str(i + 1), "2", location_code=f"GHS-R24-{i+1:02d}-02",
                    available_quantity="0", freeze_quantity="2") for i in range(25)]
        index = self.run_import(rows)
        self.assertEqual(index["summary"]["occupiedCount"], 25)
        self.assertEqual(index["summary"]["emptyCount"], 0)
        self.assertEqual(index["summary"]["quantity"], 50)
        self.assertEqual(index["summary"]["availableQuantity"], 0)
        self.assertEqual(self.details(index)["state"], "occupied")

    def test_no_record_is_empty_with_null_raw_values_and_no_fabricated_record(self):
        index = self.run_import([row(record="")])
        detail = self.details(index)
        self.assertEqual(detail["state"], "empty")
        self.assertEqual(detail["emptyReason"], "no_inventory_record")
        self.assertEqual(detail["items"], [])
        self.assertEqual(detail["totals"]["quantity"], 0)
        self.assertIsNone(detail["fields"]["x_axis"])
        self.assertIsNone(detail["updatedAtMax"])

    def test_explicit_zero_record_is_empty_and_preserved(self):
        index = self.run_import([row(quantity="0")])
        detail = self.details(index)
        self.assertEqual(detail["emptyReason"], "zero_quantity")
        self.assertEqual(detail["recordCount"], 1)
        self.assertEqual(detail["items"][0]["quantity"], 0)

    def test_multiple_skus_and_repeated_sku_records_are_summed_without_losing_items(self):
        index = self.run_import([row(record="1", quantity="2"), row(record="2", quantity="3"),
                                 row(record="3", quantity="4", sku="OTHER")])
        detail = self.details(index)
        self.assertEqual(detail["totals"]["quantity"], 9)
        self.assertEqual(detail["skuCount"], 2)
        self.assertEqual(detail["recordCount"], 3)
        self.assertEqual(index["summary"]["skuCount"], 2)
        self.assertEqual(detail["items"][0]["sku"], "000123")

    def test_missing_quantity_remains_null_and_marks_unknown_not_empty(self):
        index = self.run_import([row(quantity="", available_quantity="0")])
        detail = self.details(index)
        self.assertEqual(detail["state"], "unknown")
        self.assertIsNone(detail["totals"]["quantity"])
        self.assertIsNone(detail["items"][0]["quantity"])
        self.assertIsNone(index["summary"]["quantity"])

    def test_negative_quantity_cannot_cancel_positive_stock_into_false_empty(self):
        index = self.run_import([row(record="1", quantity="2"), row(record="2", quantity="-2")])
        self.assertEqual(self.details(index)["state"], "unknown")
        self.assertEqual(index["summary"]["unknownCount"], 1)

    def test_missing_available_is_not_fabricated_zero_and_does_not_hide_physical_stock(self):
        index = self.run_import([row(available_quantity="")])
        detail = self.details(index)
        self.assertEqual(detail["state"], "occupied")
        self.assertIsNone(detail["totals"]["availableQuantity"])
        self.assertIsNone(index["summary"]["availableQuantity"])

    def test_invalid_numeric_rejects_import_without_replacing_existing_snapshot(self):
        original = self.run_import([row()])
        bytes_before = (self.out / "index.json").read_bytes()
        for invalid in ("NaN", "Infinity", "abc", "1.5", "9007199254740992"):
            with self.subTest(invalid=invalid):
                self.write([row(quantity=invalid)])
                with self.assertRaises(ValueError):
                    self.importer.import_inventory(self.csv, self.out)
                self.assertEqual((self.out / "index.json").read_bytes(), bytes_before)
        self.assertEqual(original["summary"]["locationCount"], 1)

    def test_duplicate_inventory_is_rejected_even_if_identical(self):
        self.write([row(), row()])
        with self.assertRaisesRegex(ValueError, "duplicate|重复"):
            self.importer.import_inventory(self.csv, self.out)

    def test_same_code_different_location_id_is_rejected(self):
        self.write([row(), row(location="130", record="2")])
        with self.assertRaisesRegex(ValueError, "code|编码"):
            self.importer.import_inventory(self.csv, self.out)

    def test_metadata_conflict_is_rejected(self):
        self.write([row(), row(record="2", location_status="3")])
        with self.assertRaisesRegex(ValueError, "metadata|元数据"):
            self.importer.import_inventory(self.csv, self.out)

    def test_mixed_or_wrong_warehouse_is_rejected(self):
        self.write([row(), row(location="130", record="2", warehouse_id="109")])
        with self.assertRaisesRegex(ValueError, "warehouse|仓库"):
            self.importer.import_inventory(self.csv, self.out)

    def test_orphan_inventory_values_and_mixed_join_are_rejected(self):
        for records in ([dict(row(record=""), quantity="0")], [row(record=""), row()]):
            with self.subTest(records=records):
                self.write(records)
                with self.assertRaises(ValueError):
                    self.importer.import_inventory(self.csv, self.out)

    def test_id_and_sku_strings_are_preserved_and_stable_numeric_shard_is_used(self):
        index = self.run_import([row(location="000129", record="00012")])
        self.assertEqual(index["locations"][0]["id"], "000129")
        self.assertEqual(index["locations"][0]["shard"], "001.json")
        self.assertEqual(self.details(index)["items"][0]["id"], "00012")

    def test_repeated_import_is_byte_identical_and_snapshot_matches_source_bytes(self):
        index = self.run_import([row(location="130", record="2", location_code="GHS-R24-70-02"), row()])
        before = {p.name:p.read_bytes() for p in self.out.glob("*.json")}
        self.importer.import_inventory(self.csv, self.out)
        after = {p.name:p.read_bytes() for p in self.out.glob("*.json")}
        self.assertEqual(before, after)
        self.assertEqual(len(before), 129)
        self.assertEqual(index["snapshotId"], hashlib.sha256(self.csv.read_bytes()).hexdigest())
        self.assertEqual([g["id"] for g in index["locations"]], ["129", "130"])
        self.assertFalse(index["source"]["atomic"])

    def test_browser_scripts_preserve_text_without_allowing_script_breakout(self):
        dangerous = 'SKU</script><script>alert("x")</script>\u2028\u2029END'
        index = self.run_import([row(sku=dangerous)])
        self.assertTrue((self.out / "001.js").is_file(), "CEF-safe script shard must be generated")
        wrapper = (self.out / "001.js").read_text("utf8")
        self.assertTrue(wrapper.startswith("window.GHSInventoryPayload("))
        self.assertTrue(wrapper.endswith(");\n"))
        self.assertNotIn("</script", wrapper.lower())
        self.assertNotIn("\u2028", wrapper)
        self.assertNotIn("\u2029", wrapper)
        payload = json.loads(wrapper[len("window.GHSInventoryPayload("):-3])
        self.assertEqual(payload["kind"], "shard")
        self.assertEqual(payload["shard"], "001.json")
        self.assertEqual(payload["snapshotId"], index["snapshotId"])
        self.assertEqual(payload["locations"]["129"]["items"][0]["sku"], dangerous)
        index_script = (self.out / "index.js").read_text("utf8")
        index_payload = json.loads(index_script[len("window.GHSInventoryPayload("):-3])
        self.assertEqual(index_payload["kind"], "index")
        self.assertEqual(index_payload["summary"], index["summary"])
        summary_script = (self.out / "summary.js").read_text("utf8")
        summary = json.loads(summary_script[len("window.GHSInventorySummary="):-2])
        self.assertEqual(summary["summary"], index["summary"])
        self.assertEqual(summary["snapshotId"], index["snapshotId"])
        self.assertNotIn("locations", summary)

    def test_missing_or_duplicate_header_and_blank_identity_are_rejected(self):
        for malformed in ([row(location="")], [row(inventory_item_id="1", sku="")]):
            self.write(malformed)
            with self.assertRaises(ValueError):
                self.importer.import_inventory(self.csv, self.out)
        self.csv.write_text("warehouse_id,warehouse_id\n108,108\n", encoding="utf8")
        with self.assertRaises(ValueError):
            self.importer.import_inventory(self.csv, self.out)


if __name__ == "__main__":
    unittest.main()

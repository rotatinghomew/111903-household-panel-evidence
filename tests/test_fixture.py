"""检查合成资料可读。"""
import json
from pathlib import Path
import unittest

class FixtureTest(unittest.TestCase):
    def test_sample_is_json_object(self):
        path = Path(__file__).parents[1] / "data" / "sample.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(value, dict)
        self.assertTrue(value)

    def test_store_export_references(self):
        path = Path(__file__).parents[1] / "data" / "two_stores.json"
        export = json.loads(path.read_text(encoding="utf-8"))
        assignments = {record["id"]: record for record in export["assignments"]}
        self.assertEqual(len(assignments), len(export["assignments"]))
        for record in assignments.values():
            self.assertIn(record["participant"], export["participants"])
            self.assertIn(record["task"], export["tasks"])
            self.assertIn(record["arm"], export["study"]["arms"])
        for record in export["observations"]:
            self.assertIn(record["assignment"], assignments)
            self.assertIn(record["device"], export["devices"])
        for record in export["slots"]:
            self.assertIn(record["device"], export["devices"])
            self.assertLessEqual(set(record["tasks"]), export["tasks"].keys())
            if record["participant"] is not None:
                self.assertIn(record["participant"], export["participants"])

if __name__ == "__main__":
    unittest.main()

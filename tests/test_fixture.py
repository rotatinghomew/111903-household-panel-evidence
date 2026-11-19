"""检查合成资料可读。"""
import json
from pathlib import Path
import unittest

class FixtureTest(unittest.TestCase):
    def test_home_followup_keeps_missing_and_unauthorized_observations_separate(self):
        root = Path(__file__).parents[1] / 'data'
        training = json.loads((root / 'training_register.json').read_text(encoding='utf-8'))
        home = json.loads((root / 'home_followup.json').read_text(encoding='utf-8'))
        participants = {row['participant'] for row in training['training_enrolments']}
        visits = {row['id']: row for row in home['visit_plan']}
        observed = {row['id']: row for row in home['observations']}
        self.assertLessEqual({row['participant'] for row in visits.values()}, participants)
        self.assertTrue(visits.keys() - {row['visit'] for row in observed.values()})
        self.assertTrue(any(set(row['consent']) < set(row['required']) for row in visits.values()))
        for observation in observed.values():
            self.assertIn(observation['task'], visits[observation['visit']]['consent'])
        for correction in home['corrections']:
            self.assertGreater(correction['known'], observed[correction['observation']]['recorded'])
        for card in home['home_claims']:
            self.assertLessEqual(set(card['cited']), observed.keys())
        for visit in home['future_sessions']:
            self.assertLessEqual(set(visit['return_slots']), {row['slot'] for row in home['return_slots']})

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

    def test_training_records_and_cards_reference_distinct_evidence(self):
        root = Path(__file__).parents[1] / 'data'
        stores = json.loads((root / 'two_stores.json').read_text(encoding='utf-8'))
        register = json.loads((root / 'training_register.json').read_text(encoding='utf-8'))
        first = {row['id'] for row in stores['observations']}
        trained = {row['id'] for row in register['observations']}
        self.assertFalse(first & trained)
        self.assertTrue(all(set(card['source_observations']) <= first | trained for card in register['issued_cards']))
        self.assertEqual(len({tuple(row['devices']) for row in register['training_enrolments']}), 2)
        self.assertLess(register['issued_cards'][0]['issued_at'], stores['component_notices'][0]['known_at'])

if __name__ == "__main__":
    unittest.main()

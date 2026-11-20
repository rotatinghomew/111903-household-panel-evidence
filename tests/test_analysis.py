"""分析规则测试：首用资格、部件时间线、ITT、更正重核、排期。"""
import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

core = importlib.import_module("household-panel-evidence.core")
store = importlib.import_module("household-panel-evidence.store")
training = importlib.import_module("household-panel-evidence.training")
home = importlib.import_module("household-panel-evidence.home")
schedule = importlib.import_module("household-panel-evidence.schedule")
intervals = importlib.import_module("household-panel-evidence.intervals")

WS = core.load_workspace(ROOT / "data")
EVENTS = core.contact_events(WS)
T = core.parse_time


class ContactHistoryTest(unittest.TestCase):
    def test_demonstration_counts_as_family_contact(self):
        # U16 在 08-06 看过示范：08-09 的预约不再是 grip_open 首用
        self.assertFalse(core.first_use_eligible(EVENTS, "U16", "grip_open", T("2026-08-09T10:00:00+08:00")))
        # 但 read_scale 族仍未接触
        self.assertTrue(core.first_use_eligible(EVENTS, "U16", "read_scale", T("2026-08-09T10:00:00+08:00")))

    def test_observed_demonstration_burns_household_helper(self):
        # CO-00 旁观过握法示范：不能在同动作族充当新人
        self.assertFalse(core.first_use_eligible(EVENTS, "CO-00", "grip_open", T("2026-08-12T10:00:00+08:00")))
        self.assertTrue(core.first_use_eligible(EVENTS, "CO-00", "read_scale", T("2026-08-12T10:00:00+08:00")))

    def test_first_use_is_family_not_model(self):
        # 熟练组 L00 在 08-02 练习过 jar_open：首用按动作族而非型号判定
        self.assertFalse(core.first_use_eligible(EVENTS, "L00", "grip_open", T("2026-08-05T18:30:00+08:00")))


class PartsTimelineTest(unittest.TestCase):
    def test_component_notice_changes_actual_parts(self):
        # J1 登记 latch=old，09:25 起实际为 new
        self.assertEqual(core.device_config_at(WS, "J1", T("2026-08-03T09:20:00+08:00"))["latch"], "old")
        self.assertEqual(core.device_config_at(WS, "J1", T("2026-08-03T09:30:00+08:00"))["latch"], "new")

    def test_known_before_restores_issued_view(self):
        # 发卡时（08-07）换件通知尚未获知，J1 仍按登记认知
        at = T("2026-08-03T09:30:00+08:00")
        issued = T("2026-08-07T11:00:00+08:00")
        self.assertEqual(core.device_config_at(WS, "J1", at, known_before=issued)["latch"], "old")
        self.assertEqual(core.device_config_at(WS, "J1", at)["latch"], "new")


class StoreIttTest(unittest.TestCase):
    def test_itt_keeps_original_assignment(self):
        cells = store.itt_summary(WS, EVENTS)
        # A15 分派臂 new，即使用了 J1 也按原分派计入
        self.assertEqual(cells[("jar_open", "new", "general")]["assisted"], 1)
        self.assertEqual(cells[("jar_open", "new", "general")]["assigned"], 1)

    def test_deviation_listed_separately(self):
        listed = {r["observation"] for r in store.as_treated_listing(WS, EVENTS)}
        self.assertEqual(listed, {"O15"})

    def test_outcome_categories_stay_separate(self):
        cells = store.itt_summary(WS, EVENTS)
        self.assertEqual(cells[("jar_open", "old", "general")]["not_observed"], 1)
        self.assertEqual(cells[("jar_open", "new", "limited_grip")]["failed"], 1)

    def test_first_use_claim_keeps_stratum_gaps(self):
        adjudicated = {a["claim"]["id"]: a for a in store.adjudicate_first_use_claims(WS, EVENTS)}
        cl1 = adjudicated["CL1"]
        self.assertFalse(cl1["fully_supported"])
        by_cell = {(c["task"], c["group"]): c for c in cl1["cells"]}
        # 新臂两层各只有 1 个分派，低于每组每臂最低 2 人
        self.assertEqual(by_cell[("jar_open", "limited_grip")]["assigned"], 1)
        self.assertFalse(by_cell[("jar_open", "limited_grip")]["sufficient"])
        # scale_read 完全没有分派证据
        self.assertEqual(by_cell[("scale_read", "general")]["assigned"], 0)

    def test_card1_must_stop(self):
        reports = {r["card"]["id"]: r for r in store.store_card_reports(WS, EVENTS)}
        card1 = reports["CARD1"]
        self.assertEqual(card1["status"], "stop_new_sales")
        cited = {c["observation"]: c for c in card1["citations"]}
        # O11 实际旧件；O15 更正后为真新件但结果非独立
        self.assertFalse(cited["O11"]["current"]["valid"])
        self.assertFalse(cited["O15"]["current"]["valid"])
        self.assertFalse(cited["O15"]["as_issued"]["valid"])
        # 范围内 O12 的失败被引用遗漏
        self.assertTrue(any("O12" in r for r in card1["reasons"]))


class TrainingTest(unittest.TestCase):
    def test_practice_dose_enforced(self):
        rows = {r["id"]: r for r in training.trained_rows(WS)}
        self.assertFalse(rows["T-L03-1"]["dose_ok"])  # 第 2 期只练了 2 次
        self.assertFalse(rows["T-G03-1"]["dose_ok"])
        self.assertTrue(rows["T-L01-0"]["dose_ok"])

    def test_period1_contrast_and_noninferiority(self):
        cells = training.period1_cells(WS)
        self.assertEqual(cells[("jar_open", "new", "limited_grip")], (5, 6))
        self.assertEqual(cells[("jar_open", "old", "limited_grip")], (5, 6))
        for row in training.trained_contrast(WS):
            self.assertFalse(row["noninferior"])  # 区间下限远低于 -10pp

    def test_period2_pairs_flagged_not_superiority_evidence(self):
        p2 = training.period2_listing(WS)
        self.assertEqual(len(p2["paired"]), 22)  # 24 人减去 2 个练习量不足
        self.assertIn("不得用于宣称新部件更好", p2["carryover_note"])

    def test_card2_kept_with_wording_limits(self):
        reports = {r["card"]["id"]: r for r in training.trained_card_reports(WS)}
        card2 = reports["CARD2"]
        self.assertEqual(card2["status"], "keep")
        cited = {c["observation"]: c for c in card2["citations"]}
        self.assertTrue(cited["T-L01-0"]["current"]["valid"])
        self.assertFalse(cited["T-L01-1"]["current"]["valid"])  # 旧件对照不作新件证据
        self.assertTrue(any("非劣效未确立" in c for c in card2["cautions"]))


class HomeTest(unittest.TestCase):
    def test_roster_separates_missing_and_unauthorized(self):
        summary = home.roster_summary(WS)
        self.assertEqual(summary["observed"], 30)
        self.assertEqual(summary["missing_result"], 14)
        self.assertEqual(summary["not_authorized"], 4)
        rows = {(r["visit"], r["task"]): r["status"] for r in home.roster(WS)}
        self.assertEqual(rows[("FV-L00", "scale_read")], "not_authorized")
        self.assertEqual(rows[("FV-L02", "jar_open")], "missing_result")

    def test_correction_reopens_card_h1(self):
        reports = {r["claim"]["id"]: r for r in home.home_card_reports(WS)}
        card = reports["CARD-H1"]
        self.assertEqual(card["status"], "stop_new_sales")
        cited = {c["observation"]: c for c in card["current"]["cited"]}
        # 更正后 L00 有人提示且垫为 none，引用失效
        self.assertFalse(cited["FH-L00-jar_open"]["valid"])
        # 发出时该引用尚未更正
        issued_cited = {c["observation"]: c for c in card["as_issued"]["cited"]}
        self.assertTrue(issued_cited["FH-L00-jar_open"]["valid"])
        # 联合声明按户核算：L04 成功、L08 失败
        self.assertEqual(card["current"]["with_results"], 2)
        self.assertEqual(card["current"]["success"], 1)
        # 发行时已遗漏 L08 失败户，且 L00 未获整套授权
        self.assertTrue(any("HOME-08" in r for r in card["reasons"]))
        self.assertTrue(any("HOME-00" in r for r in card["reasons"]))

    def test_card_h2_insufficient_households(self):
        reports = {r["claim"]["id"]: r for r in home.home_card_reports(WS)}
        card = reports["CARD-H2"]
        self.assertEqual(card["status"], "stop_new_sales")
        self.assertEqual(card["current"]["with_results"], 1)
        self.assertEqual(card["current"]["missing_result"], 3)

    def test_same_person_is_not_two_households(self):
        # CARD-H1 引用了 3 条观察，但联合核算按户只有 2 户
        reports = {r["claim"]["id"]: r for r in home.home_card_reports(WS)}
        card = reports["CARD-H1"]
        self.assertEqual(len(card["claim"]["cited"]), 3)
        households = {h["household"] for h in card["current"]["households"]}
        self.assertEqual(len(households), len(card["current"]["households"]))

    def test_untouched_scopes_remain_usable(self):
        scopes = {
            (s["claim"]["group"], s["claim"]["device"], s["claim"]["mat"], s["claim"]["claim_type"]): s
            for s in home.supportable_home_scopes(WS)
        }
        key = ("limited_grip", "latch-old", "none", "joint")
        self.assertTrue(scopes[key]["sufficient"])
        self.assertEqual(scopes[key]["success"], 3)


class ScheduleTest(unittest.TestCase):
    def test_confirmed_slots_with_burned_first_use_pending(self):
        review = {r["entry"]: r for r in schedule.first_use_review(WS, EVENTS)}
        self.assertEqual(review["S1"]["status"], "pending_negotiation")
        self.assertEqual(review["S1"]["burned_families"], ["grip_open"])
        self.assertEqual(review["FU1"]["status"], "pending_negotiation")
        self.assertEqual(review["FU1"]["still_first"], ["read_scale"])

    def test_resource_conflicts(self):
        keys = {(c["store"], c["device"]) for c in schedule.resource_conflicts(WS)}
        self.assertEqual(keys, {("east", "J2"), ("west", "J1")})

    def test_candidate_crowding_confirmed_is_invalid(self):
        projections = {p["entry"]: p for p in schedule.candidate_projection(WS, EVENTS)}
        self.assertEqual(projections["S2"]["status"], "invalid")
        self.assertEqual(projections["HS1"]["status"], "invalid")
        self.assertEqual(projections["S3"]["status"], "negotiate")
        # S2 需要两个动作族的首用新人，现有人手覆盖不了
        self.assertTrue(any("需新招募" in n for n in projections["S2"]["notes"]))

    def test_home_gaps_not_fillable_in_store(self):
        claims = {g["claim"] for g in schedule.unfillable_in_store(WS)}
        self.assertEqual(claims, {"CARD-H1", "CARD-H2"})

    def test_open_gaps_keep_store_cells(self):
        gaps = schedule.open_gaps(WS)
        store_gaps = {(g["task"], g["group"]) for g in gaps if g["kind"] == "store_first_use"}
        self.assertIn(("scale_read", "general"), store_gaps)
        self.assertIn(("jar_open", "limited_grip"), store_gaps)


class IntervalsTest(unittest.TestCase):
    def test_wilson_bounds(self):
        lo, hi = intervals.wilson(5, 6, 0.95)
        self.assertAlmostEqual(lo, 0.436, places=2)
        self.assertAlmostEqual(hi, 0.970, places=2)

    def test_newcombe_difference(self):
        lo, hi = intervals.newcombe(5, 6, 5, 6, 0.95)
        self.assertLess(lo, -0.10)  # 非劣界 -10pp 未闭合
        self.assertGreater(hi, 0.10)


if __name__ == "__main__":
    unittest.main()

"""家庭回访：名册分类、更正生效、家庭说明卡复核。

- 名册区分“有授权但未得到结果”与“未获相应授权”，分别报告；
  练习不够或没按期回访不算失败，也不能靠剔除困难家庭抬高成功率。
- 有人提示（coached）的完成不算无提示独立；防滑垫以更正后的实际配置为准；
  超出约定回访窗口的观察不计入。
- 联合（joint）声明按“同一户、同一次回访、整套动作”核算，
  不能把来自不同家庭的两个成功率拼成整套成功；同一人两次观察不算两户。
- 更正口头提示或垫配置后，重核已发行的套餐与抽出的独立声明；
  未被动到的配置与动作保持可用。
"""
from __future__ import annotations

from .core import (
    Workspace,
    device_components,
    parse_time,
    participant_group,
)
from .intervals import wilson


def corrected_observations(ws: Workspace, known_before=None) -> dict:
    """应用更正后的有效观察视图；known_before 用于还原发卡时的认知。"""
    obs = {o["id"]: dict(o) for o in ws.home.get("observations", [])}
    corrections = sorted(
        ws.home.get("corrections", []), key=lambda c: parse_time(c["known"])
    )
    for corr in corrections:
        if known_before is not None and parse_time(corr["known"]) > known_before:
            continue
        target = obs.get(corr["observation"])
        if target is None:
            continue
        target.update(corr["changes"])
        target.setdefault("corrected_fields", [])
        target["corrected_fields"] = sorted(
            set(target["corrected_fields"]) | set(corr["changes"])
        )
    return obs


def roster(ws: Workspace) -> list[dict]:
    """回访名册：每个计划回访 × 每个要求动作一行。"""
    obs = corrected_observations(ws)
    by_visit_task = {(o["visit"], o["task"]) for o in obs.values()}
    rows = []
    for v in ws.home.get("visit_plan", []):
        for task in v["required"]:
            if task not in v["consent"]:
                status = "not_authorized"  # 未获相应授权
            elif (v["id"], task) not in by_visit_task:
                status = "missing_result"  # 有授权但未得到结果
            else:
                status = "observed"
            rows.append(
                {
                    "visit": v["id"],
                    "household": v["household"],
                    "participant": v["participant"],
                    "task": task,
                    "status": status,
                }
            )
    return rows


def roster_summary(ws: Workspace) -> dict:
    rows = roster(ws)
    out = {"observed": 0, "missing_result": 0, "not_authorized": 0}
    for r in rows:
        out[r["status"]] += 1
    out["planned"] = len(rows)
    return out


def household_view(ws: Workspace, known_before=None) -> list[dict]:
    """按户归集的有效回访视图（已应用截至 known_before 的更正）。"""
    obs = corrected_observations(ws, known_before)
    by_visit_task = {(o["visit"], o["task"]): o for o in obs.values()}
    views = []
    for v in ws.home.get("visit_plan", []):
        pid = v["participant"]
        comps = device_components(ws, v["device"]) or {}
        tasks = {}
        for task in v["required"]:
            o = by_visit_task.get((v["id"], task))
            entry = {"authorized": task in v["consent"], "observed": o is not None}
            if o is not None:
                in_window = v["date_from"] <= o["occurred"][:10] <= v["date_through"]
                entry.update(
                    {
                        "independent": bool(o["independent"]) and not o["coached"],
                        "raw_independent": bool(o["independent"]),
                        "coached": bool(o["coached"]),
                        "mat": o["mat"],
                        "in_window": in_window,
                        "corrected": "corrected_fields" in o,
                    }
                )
            tasks[task] = entry
        authorized = [t for t in v["required"] if tasks[t]["authorized"]]
        joint = None
        if len(authorized) == len(v["required"]) and all(
            tasks[t]["observed"] for t in v["required"]
        ):
            joint = all(
                tasks[t]["independent"] and tasks[t]["in_window"] for t in v["required"]
            )
        views.append(
            {
                "visit": v["id"],
                "household": v["household"],
                "participant": pid,
                "group": participant_group(ws, pid),
                "device": v["device"],
                "components": comps,
                "planned_mat": v["mat"],
                "tasks": tasks,
                "joint_success": joint,
            }
        )
    return views


def _claim_components(ws: Workspace, claim: dict) -> dict:
    return device_components(ws, claim["device"]) or {}


def adjudicate_home_claim(ws: Workspace, claim: dict, known_before=None) -> dict:
    """家庭声明复核：按户核算，授权/结果/垫配置分列。

    claim_type=joint 要求同一户同一次回访整套动作全部无提示独立；
    separate 只核声明列出的动作。
    """
    views = household_view(ws, known_before)
    study = ws.stores["study"]
    min_n = study["min_per_group_arm"]  # 每户一人，户为分析单位
    conf = study["confidence"]
    claim_comps = _claim_components(ws, claim)
    tasks = claim["tasks"]
    households = []
    for v in views:
        if v["group"] != claim["group"]:
            continue
        if any(v["components"].get(c) != claim_comps.get(c) for c in ("latch", "display")):
            continue
        # 范围以约定配置划定：计划垫不同的回访不属于本声明的核算
        if v["planned_mat"] != claim["mat"]:
            continue
        auth = all(v["tasks"][t]["authorized"] for t in tasks)
        observed = [t for t in tasks if v["tasks"][t]["observed"]]
        has_results = len(observed) == len(tasks)
        mat_ok = has_results and all(v["tasks"][t]["mat"] == claim["mat"] for t in tasks)
        success = bool(
            has_results
            and mat_ok
            and all(
                v["tasks"][t]["independent"] and v["tasks"][t]["in_window"] for t in tasks
            )
        )
        if not auth:
            category = "not_authorized"
        elif not has_results:
            category = "missing_result"
        elif not mat_ok:
            category = "config_mismatch"
        else:
            category = "success" if success else "failure"
        households.append(
            {
                "household": v["household"],
                "visit": v["visit"],
                "category": category,
                "success": success,
            }
        )
    with_results = [h for h in households if h["category"] in ("success", "failure")]
    k = sum(1 for h in with_results if h["success"])
    n = len(with_results)
    obs = corrected_observations(ws, known_before)
    visits = {v["id"]: v for v in ws.home.get("visit_plan", [])}
    category_by_visit = {h["visit"]: h["category"] for h in households}
    cited = []
    for oid in claim.get("cited", []):
        o = obs.get(oid)
        check = _home_citation(ws, claim, o, visits)
        entry = {"observation": oid, **check}
        if o is not None:
            entry["household"] = visits[o["visit"]]["household"]
            entry["household_category"] = category_by_visit.get(o["visit"])
        cited.append(entry)
    return {
        "claim": claim,
        "households": households,
        "with_results": n,
        "success": k,
        "rate": (k / n) if n else None,
        "ci": wilson(k, n, conf),
        "sufficient": n >= min_n,
        "min_n": min_n,
        "missing_result": sum(1 for h in households if h["category"] == "missing_result"),
        "not_authorized": sum(1 for h in households if h["category"] == "not_authorized"),
        "config_mismatch": sum(1 for h in households if h["category"] == "config_mismatch"),
        "cited": cited,
    }


def _home_citation(ws: Workspace, claim: dict, o: dict | None, visits: dict) -> dict:
    if o is None:
        return {"valid": False, "reasons": ["引用的观察不存在"]}
    reasons = []
    v = visits[o["visit"]]
    if participant_group(ws, v["participant"]) != claim["group"]:
        reasons.append("分层不符")
    if o["task"] not in claim["tasks"]:
        reasons.append("动作不在声明范围")
    if o["task"] not in v["consent"]:
        reasons.append("该动作未获授权")
    comps = device_components(ws, v["device"]) or {}
    claim_comps = _claim_components(ws, claim)
    if any(comps.get(c) != claim_comps.get(c) for c in ("latch", "display")):
        reasons.append("样机部件与声明不符")
    if o["mat"] != claim["mat"]:
        reasons.append(f"防滑垫实际为 {o['mat']}，与声明 {claim['mat']} 不符")
    if o["coached"]:
        reasons.append("当次有人提示，非无提示独立")
    if not o["independent"]:
        reasons.append("未独立完成")
    if not (v["date_from"] <= o["occurred"][:10] <= v["date_through"]):
        reasons.append("超出约定回访窗口")
    return {"valid": not reasons, "reasons": reasons}


def _coverage_reasons(claim: dict, adj: dict) -> list[str]:
    """引用相对范围的覆盖核查：遗漏已观察住户、跨户拼合联合声明。"""
    reasons = []
    cited_households = {
        c["household"] for c in adj["cited"] if c["valid"] and c.get("household")
    }
    observed_households = {
        h["household"] for h in adj["households"] if h["category"] in ("success", "failure")
    }
    omitted = sorted(observed_households - cited_households)
    if omitted:
        reasons.append(f"引用未覆盖范围内全部已观察住户（遗漏 {'、'.join(omitted)}）")
    if claim["claim_type"] == "joint":
        unauthorized = sorted(
            {
                c["household"]
                for c in adj["cited"]
                if c.get("household") and c.get("household_category") == "not_authorized"
            }
        )
        if unauthorized:
            reasons.append(
                f"联合声明引用未获整套授权的住户（{'、'.join(unauthorized)}），不可跨户拼合"
            )
    return reasons


def home_card_reports(ws: Workspace) -> list[dict]:
    """家庭说明卡复核：保留发出时依据，按当前更正重核，给出处置。"""
    reports = []
    for claim in ws.home.get("home_claims", []):
        issued_at = parse_time(claim["issued"])
        as_issued = adjudicate_home_claim(ws, claim, known_before=issued_at)
        current = adjudicate_home_claim(ws, claim)
        reasons = []
        cautions = []
        if any(not c["valid"] for c in current["cited"]):
            reasons.append("更正后引用证据失效")
        if not current["sufficient"]:
            reasons.append(
                f"有授权且有结果的户数不足（{current['with_results']}/{current['min_n']}）"
            )
        if not as_issued["sufficient"]:
            reasons.append(
                f"发行时按户核算证据已不足（{as_issued['with_results']}/{as_issued['min_n']}）"
            )
        reasons += [f"发行时：{r}" for r in _coverage_reasons(claim, as_issued)]
        reasons += [f"当前：{r}" for r in _coverage_reasons(claim, current)]
        if current["with_results"] and current["success"] < current["with_results"]:
            cautions.append("范围内存在未独立完成的住户，承诺不能按全体成功表述")
        reports.append(
            {
                "claim": claim,
                "as_issued": as_issued,
                "current": current,
                "status": "keep" if not reasons else "stop_new_sales",
                "reasons": reasons,
                "cautions": cautions,
            }
        )
    return reports


def supportable_home_scopes(ws: Workspace) -> list[dict]:
    """枚举现有回访覆盖的 (分层 × 样机 × 垫 × 声明形态)，标出证据达标的范围。"""
    views = household_view(ws)
    combos = sorted(
        {(v["group"], v["device"], v["planned_mat"]) for v in views}
    )
    scopes = []
    for group, device, mat in combos:
        for claim_type, tasks in (
            ("joint", ["jar_open", "scale_read"]),
            ("separate", ["jar_open"]),
            ("separate", ["scale_read"]),
        ):
            claim = {
                "id": f"scope:{group}:{device}:{mat}:{claim_type}:{'+'.join(tasks)}",
                "group": group,
                "device": device,
                "mat": mat,
                "claim_type": claim_type,
                "tasks": tasks,
                "cited": [],
            }
            adj = adjudicate_home_claim(ws, claim)
            if adj["with_results"] or adj["missing_result"] or adj["not_authorized"]:
                scopes.append(adj)
    return scopes

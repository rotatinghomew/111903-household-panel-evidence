"""门店首用试验：按原分派（ITT）评估，实际部件与分派/登记不符的另列。

- 独立完成率按原分派臂归集，实操换组不事后改分派；
- 拒绝观察、没有完成记录、实际操作失败分列，互不合并；
- 实际部件以换件通知生效时刻重算，与登记或分派不一致的行单独列出，
  不能用分派估计为未充分观察的新部件背书。
"""
from __future__ import annotations

from .core import (
    OUTCOME_CATEGORIES,
    TASK_COMPONENTS,
    Workspace,
    allowed_families,
    contact_events,
    device_components,
    device_config_at,
    expected_devices,
    first_use_eligible,
    parse_time,
    participant_group,
    task_family,
)
from .intervals import wilson


def assignment_rows(ws: Workspace, events: list | None = None, known_before=None) -> list[dict]:
    """每个分派一行：原分派、同意核查、实际部件、首用资格。"""
    if events is None:
        events = contact_events(ws)
    obs_by_assignment = {}
    for obs in ws.stores.get("observations", []):
        obs_by_assignment.setdefault(obs["assignment"], obs)
    rows = []
    for a in ws.stores.get("assignments", []):
        pid = a["participant"]
        task = a["task"]
        family = task_family(ws, task)
        obs = obs_by_assignment.get(a["id"])
        row = {
            "assignment": a["id"],
            "participant": pid,
            "store": a["store"],
            "task": task,
            "family": family,
            "arm": a["arm"],
            "group": participant_group(ws, pid),
            "consent_ok": family in allowed_families(ws, pid),
            "observed": obs is not None,
            "outcome": obs["outcome"] if obs else "not_observed",
            "seconds": obs.get("seconds") if obs else None,
            "observation": obs["id"] if obs else None,
            "device": obs["device"] if obs else None,
        }
        if obs:
            at = parse_time(obs["at"])
            actual = device_config_at(ws, obs["device"], at, known_before=known_before)
            registered = device_components(ws, obs["device"]) or {}
            relevant = TASK_COMPONENTS.get(task, ())
            row.update(
                {
                    "at": at,
                    "actual_config": actual,
                    "registered_config": registered,
                    # 实际部件与设备登记不一致（换件通知改写了登记）
                    "registry_mismatch": any(
                        actual.get(c) != registered.get(c) for c in actual
                    ),
                    # 实际部件与分派臂不一致（只核对该动作依赖的部件）
                    "assignment_mismatch": any(
                        c == "latch" and actual.get("latch") != a["arm"] for c in relevant
                    ),
                    # 现场用的设备不是该分派臂的登记设备（实操换组/换机）
                    "device_deviation": obs["device"] not in expected_devices(ws, a["arm"]),
                    "first_use": first_use_eligible(events, pid, family, at),
                }
            )
        rows.append(row)
    return rows


def itt_summary(ws: Workspace, events: list | None = None) -> dict:
    """按 (任务, 原分派臂, 分层) 归集的结果计数；结果类别分列。"""
    cells: dict = {}
    for row in assignment_rows(ws, events):
        key = (row["task"], row["arm"], row["group"])
        cell = cells.setdefault(
            key, {c: 0 for c in OUTCOME_CATEGORIES} | {"assigned": 0}
        )
        cell["assigned"] += 1
        outcome = row["outcome"] if row["outcome"] in OUTCOME_CATEGORIES else "not_observed"
        cell[outcome] += 1
    return cells


def as_treated_listing(ws: Workspace, events: list | None = None) -> list[dict]:
    """实际部件与登记或分派不一致、或现场换机的观察，另列不并入分派估计。"""
    listed = []
    for row in assignment_rows(ws, events):
        if not row["observed"]:
            continue
        if row["registry_mismatch"] or row["assignment_mismatch"] or row["device_deviation"]:
            listed.append(row)
    return listed


def _claim_config(claim: dict) -> dict:
    return {"latch": claim.get("latch"), "display": claim.get("display")}


def _matches_claim(config: dict, claim_config: dict, task: str) -> bool:
    """只核对该动作依赖的部件：未变化的操作条件上的证据才可沿用。"""
    for c in TASK_COMPONENTS.get(task, ()):
        want = claim_config.get(c)
        if want is not None and config.get(c) != want:
            return False
    return True


def claim_cells_first_use(
    ws: Workspace, claim: dict, events: list | None = None, known_before=None
) -> list[dict]:
    """首用声明的 (动作 × 分层) 单元：独立完成率、区间与证据充分性。"""
    if events is None:
        events = contact_events(ws)
    rows = assignment_rows(ws, events, known_before=known_before)
    study = ws.stores["study"]
    min_n = study["min_per_group_arm"]
    conf = study["confidence"]
    claim_config = _claim_config(claim)
    cells = []
    for task in claim["tasks"]:
        for group in claim["groups"]:
            pool = []
            for row in rows:
                if row["task"] != task or row["group"] != group or not row["consent_ok"]:
                    continue
                if row["observed"]:
                    if not row["first_use"]:
                        continue
                    match = _matches_claim(row["actual_config"], claim_config, task)
                else:
                    # 未观察行按原分派臂归入分母（ITT），不补造实际部件
                    match = all(
                        row["arm"] == claim_config.get(c) if c == "latch" else True
                        for c in TASK_COMPONENTS.get(task, ())
                        if claim_config.get(c) is not None
                    )
                if match:
                    pool.append(row)
            assigned = len(pool)
            indep = sum(1 for r in pool if r["outcome"] == "independent")
            cells.append(
                {
                    "task": task,
                    "group": group,
                    "assigned": assigned,
                    "independent": indep,
                    "outcomes": {
                        c: sum(1 for r in pool if r["outcome"] == c)
                        for c in OUTCOME_CATEGORIES
                    },
                    "rate": (indep / assigned) if assigned else None,
                    "ci": wilson(indep, assigned, conf),
                    "sufficient": assigned >= min_n,
                    "min_n": min_n,
                    "assignments": [r["assignment"] for r in pool],
                }
            )
    return cells


def adjudicate_first_use_claims(ws: Workspace, events: list | None = None) -> list[dict]:
    """复核门店提交的首用声明：可支持范围只含证据充分的完整单元。"""
    if events is None:
        events = contact_events(ws)
    out = []
    for claim in ws.stores.get("claim_requests", []):
        if claim.get("use") != "first":
            continue
        cells = claim_cells_first_use(ws, claim, events)
        out.append(
            {
                "claim": claim,
                "cells": cells,
                "fully_supported": all(c["sufficient"] for c in cells),
                "gaps": [c for c in cells if not c["sufficient"]],
            }
        )
    return out


def _citation_check(
    ws: Workspace, claim: dict, card: dict, obs: dict | None, events: list, known_before
) -> dict:
    """逐条核对卡片引用的观察：部件、结果、分层、同意、首用。"""
    if obs is None:
        return {"valid": False, "reasons": ["引用的观察不存在"]}
    reasons = []
    cutoff = known_before
    view = [e for e in events if cutoff is None or e["known"] <= cutoff]
    assignments = {a["id"]: a for a in ws.stores.get("assignments", [])}
    a = assignments.get(obs.get("assignment"))
    if a is None:
        return {"valid": False, "reasons": ["引用观察没有对应分派"]}
    pid = a["participant"]
    if participant_group(ws, pid) not in card["groups"]:
        reasons.append(f"参与者分层 {participant_group(ws, pid)} 不在卡片范围")
    task = a["task"]
    if task not in card["tasks"]:
        reasons.append(f"动作 {task} 不在卡片范围")
    family = task_family(ws, task)
    if family not in allowed_families(ws, pid):
        reasons.append("该动作族不在同意范围内")
    at = parse_time(obs["at"])
    actual = device_config_at(ws, obs["device"], at, known_before=cutoff)
    claim_config = _claim_config(claim)
    for c in TASK_COMPONENTS.get(task, ()):
        want = claim_config.get(c)
        if want is not None and actual.get(c) != want:
            reasons.append(f"实际部件 {c}={actual.get(c)} 与声明 {want} 不符")
    if obs["outcome"] != "independent":
        reasons.append(f"结果为 {obs['outcome']}，非独立完成")
    if not first_use_eligible(view, pid, family, at):
        reasons.append("观察时已非该动作族首用")
    return {"valid": not reasons, "reasons": reasons}


def store_card_reports(ws: Workspace, events: list | None = None) -> list[dict]:
    """首用类已发卡复核：保留发出时依据，按当前真实部件与接触史重核。"""
    if events is None:
        events = contact_events(ws)
    claims = {c["id"]: c for c in ws.stores.get("claim_requests", [])}
    obs_index = {o["id"]: o for o in ws.stores.get("observations", [])}
    reports = []
    for card in ws.training.get("issued_cards", []):
        claim = claims.get(card["claim"])
        if claim is None or claim.get("use") != "first":
            continue
        issued_at = parse_time(card["issued_at"])
        citations = []
        for oid in card["source_observations"]:
            obs = obs_index.get(oid)
            citations.append(
                {
                    "observation": oid,
                    "as_issued": _citation_check(ws, claim, card, obs, events, issued_at),
                    "current": _citation_check(ws, claim, card, obs, events, None),
                }
            )
        cells = claim_cells_first_use(ws, claim, events)
        sufficient = all(c["sufficient"] for c in cells)
        citations_ok = all(c["current"]["valid"] for c in citations)
        reasons = []
        if not citations_ok:
            reasons.append("引用证据在当前核定下不成立")
        if not sufficient:
            reasons.append("声明范围内存在证据不足的层")
        # 覆盖核查：声明范围内已观察的分派不得被引用选择性遗漏
        obs_by_assignment = {
            o["assignment"]: o for o in ws.stores.get("observations", [])
        }
        cited_ids = set(card["source_observations"])
        for cell in cells:
            for a_id in cell["assignments"]:
                obs = obs_by_assignment.get(a_id)
                if obs and obs["id"] not in cited_ids:
                    reasons.append(
                        f"引用遗漏范围内已观察分派（{obs['id']} 结果 {obs['outcome']}）"
                    )
        cautions = []
        for cell in cells:
            if cell["assigned"] and cell["independent"] < cell["assigned"]:
                cautions.append(
                    f"{cell['group']} {cell['task']} 首用独立 "
                    f"{cell['independent']}/{cell['assigned']}，不能表述为全体可独立"
                )
        reports.append(
            {
                "card": card,
                "claim": claim,
                "citations": citations,
                "cells": cells,
                "status": "keep" if not reasons else "stop_new_sales",
                "reasons": reasons,
                "cautions": cautions,
            }
        )
    return reports

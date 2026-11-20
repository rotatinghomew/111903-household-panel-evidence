"""熟练交叉试验：规定练习量核验、第一期对照、第二期迁移标记。

- 只有确实完成规定练习量（trained_min_repetitions）的正式观察才进入熟练分析；
- 第一期为同类人群的组间对照，可解释新部件效果；
- 第二期存在从旧款带来的动作迁移，若允许使用的资料无法把迁移与
  新部件效果分开，配对差不得用于宣称新部件更好，只作描述性列示。
"""
from __future__ import annotations

from .core import (
    TASK_COMPONENTS,
    Workspace,
    device_components,
    participant_group,
)
from .intervals import newcombe, wilson


def practice_dose(ws: Workspace) -> dict:
    """(参与者, 动作, 阶段) 的练习次数。"""
    dose: dict = {}
    for row in ws.training.get("practice", []):
        key = (row["participant"], row["task"], row["period"])
        dose[key] = dose.get(key, 0) + 1
    return dose


def trained_rows(ws: Workspace) -> list[dict]:
    """熟练组正式观察，附练习量核验；保留个人内的阶段次序与重复计数。"""
    min_reps = ws.stores["study"]["trained_min_repetitions"]
    dose = practice_dose(ws)
    rows = []
    for obs in ws.training.get("observations", []):
        pid = obs["participant"]
        d = dose.get((pid, obs["task"], obs["period"]), 0)
        comps = device_components(ws, obs["device"]) or {}
        rows.append(
            {
                "id": obs["id"],
                "participant": pid,
                "task": obs["task"],
                "period": obs["period"],
                "device": obs["device"],
                "components": comps,
                "latch": comps.get("latch"),
                "group": participant_group(ws, pid),
                "outcome": obs["outcome"],
                "seconds": obs.get("seconds"),
                "dose": d,
                "dose_ok": d >= min_reps,
            }
        )
    return rows


def period1_cells(ws: Workspace) -> dict:
    """第一期（无迁移）按 (动作, latch, 分层) 的独立/总数。"""
    cells: dict = {}
    for r in trained_rows(ws):
        if r["period"] != 1 or not r["dose_ok"]:
            continue
        key = (r["task"], r["latch"], r["group"])
        k, n = cells.get(key, (0, 0))
        cells[key] = (k + (1 if r["outcome"] == "independent" else 0), n + 1)
    return cells


def trained_contrast(ws: Workspace) -> list[dict]:
    """第一期新-旧对照：率差区间与非劣效判定（下限须高于 -margin）。"""
    study = ws.stores["study"]
    conf = study["confidence"]
    margin = study["noninferiority_margin_pp"] / 100.0
    cells = period1_cells(ws)
    out = []
    for group in study["target_groups"]:
        new = cells.get(("jar_open", "new", group), (0, 0))
        old = cells.get(("jar_open", "old", group), (0, 0))
        if new[1] and old[1]:
            lo, hi = newcombe(new[0], new[1], old[0], old[1], conf)
            diff = new[0] / new[1] - old[0] / old[1]
            noninferior = lo > -margin
        else:
            lo = hi = diff = None
            noninferior = False
        out.append(
            {
                "group": group,
                "new": new,
                "old": old,
                "new_ci": wilson(new[0], new[1], conf),
                "old_ci": wilson(old[0], old[1], conf),
                "diff": diff,
                "diff_ci": (lo, hi),
                "noninferior": noninferior,
                "margin": margin,
            }
        )
    return out


def period2_listing(ws: Workspace) -> dict:
    """第二期观察：迁移不可分离，配对差只列示、不用于宣称新部件更优。"""
    rows = trained_rows(ws)
    second = [r for r in rows if r["period"] == 2]
    eligible = [r for r in second if r["dose_ok"]]
    excluded = [r for r in second if not r["dose_ok"]]
    first_ok = {r["participant"]: r for r in rows if r["period"] == 1 and r["dose_ok"]}
    paired = []
    for r in eligible:
        base = first_ok.get(r["participant"])
        if base is None:
            continue
        outcomes = {base["latch"]: base["outcome"], r["latch"]: r["outcome"]}
        if "new" in outcomes and "old" in outcomes:
            paired.append(
                {
                    "participant": r["participant"],
                    "sequence": f"{base['latch']}→{r['latch']}",
                    "new": outcomes["new"],
                    "old": outcomes["old"],
                    "diff": (outcomes["new"] == "independent")
                    - (outcomes["old"] == "independent"),
                }
            )
    return {
        "eligible": eligible,
        "excluded": excluded,
        "paired": paired,
        "carryover_note": "第二期受旧款动作迁移影响，配对差不得用于宣称新部件更好",
    }


def adjudicate_trained_claims(ws: Workspace) -> list[dict]:
    """熟练声明复核：只用第一期、练习量达标、部件匹配的观察。"""
    study = ws.stores["study"]
    min_n = study["min_per_group_arm"]
    conf = study["confidence"]
    rows = [r for r in trained_rows(ws) if r["dose_ok"] and r["period"] == 1]
    out = []
    for claim in ws.stores.get("claim_requests", []):
        if claim.get("use") != "trained":
            continue
        cells = []
        for task in claim["tasks"]:
            for group in claim["groups"]:
                pool = [
                    r
                    for r in rows
                    if r["task"] == task
                    and r["group"] == group
                    and all(
                        r["components"].get(c) == claim.get(c)
                        for c in TASK_COMPONENTS.get(task, ())
                        if claim.get(c) is not None
                    )
                ]
                n = len(pool)
                k = sum(1 for r in pool if r["outcome"] == "independent")
                cells.append(
                    {
                        "task": task,
                        "group": group,
                        "n": n,
                        "independent": k,
                        "rate": (k / n) if n else None,
                        "ci": wilson(k, n, conf),
                        "sufficient": n >= min_n,
                        "min_n": min_n,
                        "observations": [r["id"] for r in pool],
                    }
                )
        out.append(
            {
                "claim": claim,
                "cells": cells,
                "fully_supported": all(c["sufficient"] for c in cells),
                "gaps": [c for c in cells if not c["sufficient"]],
            }
        )
    return out


def _trained_citation(ws: Workspace, claim: dict, card: dict, obs_id: str) -> dict:
    obs = next((o for o in ws.training.get("observations", []) if o["id"] == obs_id), None)
    if obs is None:
        return {"valid": False, "reasons": ["引用的观察不存在"]}
    reasons = []
    pid = obs["participant"]
    if participant_group(ws, pid) not in card["groups"]:
        reasons.append(f"参与者分层 {participant_group(ws, pid)} 不在卡片范围")
    if obs["task"] not in card["tasks"]:
        reasons.append(f"动作 {obs['task']} 不在卡片范围")
    comps = device_components(ws, obs["device"]) or {}
    for c in TASK_COMPONENTS.get(obs["task"], ()):
        want = claim.get(c)
        if want is not None and comps.get(c) != want:
            reasons.append(f"部件 {c}={comps.get(c)} 与声明 {want} 不符")
    min_reps = ws.stores["study"]["trained_min_repetitions"]
    dose = practice_dose(ws).get((pid, obs["task"], obs["period"]), 0)
    if dose < min_reps:
        reasons.append(f"练习量 {dose} 未达规定 {min_reps}")
    if obs["outcome"] != "independent":
        reasons.append(f"结果为 {obs['outcome']}，非独立完成")
    return {"valid": not reasons, "reasons": reasons}


def trained_card_reports(ws: Workspace) -> list[dict]:
    """熟练类已发卡复核：范围以当前全部合格证据重核，对照结论单独说明。"""
    claims = {c["id"]: c for c in ws.stores.get("claim_requests", [])}
    adjudicated = {a["claim"]["id"]: a for a in adjudicate_trained_claims(ws)}
    contrast = trained_contrast(ws)
    reports = []
    for card in ws.training.get("issued_cards", []):
        claim = claims.get(card["claim"])
        if claim is None or claim.get("use") != "trained":
            continue
        citations = [
            {"observation": oid, "current": _trained_citation(ws, claim, card, oid)}
            for oid in card["source_observations"]
        ]
        adj = adjudicated[claim["id"]]
        sufficient = adj["fully_supported"]
        reasons = []
        if not sufficient:
            reasons.append("声明范围内存在证据不足的层")
        cautions = []
        for c in citations:
            if not c["current"]["valid"]:
                cautions.append(
                    f"引用 {c['observation']} 不作本声明证据（{'; '.join(c['current']['reasons'])}）"
                )
        for cell in adj["cells"]:
            if cell["n"] and cell["independent"] < cell["n"]:
                cautions.append(
                    f"{cell['group']} {cell['task']} 熟练后仍有 "
                    f"{cell['n'] - cell['independent']}/{cell['n']} 未独立，不能表述为全体可独立"
                )
        for row in contrast:
            if not row["noninferior"]:
                cautions.append(f"{row['group']} 新-旧非劣效未确立，不得宣称优于旧款")
        reports.append(
            {
                "card": card,
                "claim": claim,
                "citations": citations,
                "cells": adj["cells"],
                "status": "keep" if not reasons else "stop_new_sales",
                "reasons": reasons,
                "cautions": cautions,
                "contrast": contrast,
            }
        )
    return reports

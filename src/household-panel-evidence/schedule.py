"""下一轮排期：资源冲突、首用资格核销、候选安排的缺口对照。

- 已确认活动保留时段、设备与约定顺序；候选安排挤占已确认活动即无效。
- 首用名额是消耗性机会：补报接触使志愿者失去资格的，已确认位置列为
  待协商——不算补足缺口，也不回到可任意分配的位置。
- 同一受试者不能填两条同动作族、彼此要求首次接触的对照。
- 候选安排按“补哪些仍开放的证据空白、消耗哪些尚未接触的机会”对照；
  家庭环境类声明即使多做店内试验也得不到证据。
"""
from __future__ import annotations

from .core import (
    TASK_COMPONENTS,
    Workspace,
    allowed_families,
    contact_events,
    device_components,
    first_use_eligible,
    parse_time,
    participant_group,
    task_family,
)
from .home import adjudicate_home_claim, home_card_reports
from .store import adjudicate_first_use_claims
from .training import adjudicate_trained_claims, trained_contrast


def calendar_entries(ws: Workspace) -> list[dict]:
    """门店预约、家庭回访位置与未来场次统一成日历条目。"""
    entries = []
    for s in ws.stores.get("slots", []):
        entries.append(
            {
                "kind": "store_slot",
                "id": s["id"],
                "store": s["store"],
                "at": parse_time(s["at"]),
                "device": s["device"],
                "participants": [s["participant"]] if s.get("participant") else [],
                "tasks": list(s.get("tasks", [])),
                "status": s["status"],
                "requirement": s.get("requirement"),
                "mat": None,
            }
        )
    sessions = {s["session"]: s for s in ws.home.get("future_sessions", [])}
    for r in ws.home.get("return_slots", []):
        session = next(
            (s for s in sessions.values() if r["slot"] in s.get("return_slots", [])), None
        )
        entries.append(
            {
                "kind": "return_slot",
                "id": r["slot"],
                "store": r["store"],
                "at": parse_time(r["at"]),
                "device": session["device"] if session else None,
                "session": session["session"] if session else None,
                "participants": [r["participant"]],
                "tasks": [],
                "status": r["state"],
                "requirement": "first",
                "mat": session.get("mat") if session else None,
            }
        )
    for s in sessions.values():
        entries.append(
            {
                "kind": "session",
                "id": s["session"],
                "store": s["store"],
                "at": parse_time(s["at"]),
                "device": s["device"],
                "participants": list(s.get("participants", [])),
                "tasks": [],
                "status": "planned",
                "requirement": None,
                "mat": s.get("mat"),
            }
        )
    return entries


def resource_conflicts(ws: Workspace) -> list[dict]:
    """同店同一时段的同台设备不可重复用（门店预约与未来场次争用样机）。

    回访位置依附于所属场次的设备配置，不单独占用门店样机资源。
    """
    by_key: dict = {}
    for e in calendar_entries(ws):
        if e["device"] is None or e["kind"] == "return_slot":
            continue
        key = (e["store"], e["at"], e["device"])
        by_key.setdefault(key, []).append(e)
    return [
        {"store": k[0], "at": k[1], "device": k[2], "entries": v}
        for k, v in sorted(by_key.items(), key=lambda kv: kv[0])
        if len(v) > 1
    ]


def first_use_review(ws: Workspace, events: list | None = None) -> list[dict]:
    """核销要求首用的位置：失去资格的已确认位置列为待协商。"""
    if events is None:
        events = contact_events(ws)
    review = []
    for e in calendar_entries(ws):
        if e["requirement"] != "first" or not e["participants"]:
            continue
        for pid in e["participants"]:
            if e["tasks"]:
                fams = {task_family(ws, t) for t in e["tasks"]}
            else:
                fams = allowed_families(ws, pid)
            burned = sorted(
                f for f in fams if not first_use_eligible(events, pid, f, e["at"])
            )
            kept = sorted(fams - set(burned))
            if burned and e["status"] == "confirmed":
                status = "pending_negotiation"  # 待协商：不算补足，也不回到可分配池
            elif burned:
                status = "ineligible"
            else:
                status = "eligible"
            review.append(
                {
                    "entry": e["id"],
                    "participant": pid,
                    "burned_families": burned,
                    "still_first": kept,
                    "entry_status": e["status"],
                    "status": status,
                }
            )
    return review


def shared_first_use_conflicts(ws: Workspace) -> list[dict]:
    """同一受试者出现在多条同动作族、都要求首次接触的位置上。"""
    by_pair: dict = {}
    for e in calendar_entries(ws):
        if e["requirement"] != "first":
            continue
        for pid in e["participants"]:
            fams = (
                {task_family(ws, t) for t in e["tasks"]}
                if e["tasks"]
                else allowed_families(ws, pid)
            )
            for f in fams:
                by_pair.setdefault((pid, f), []).append(e["id"])
    return [
        {"participant": pid, "family": fam, "entries": ids}
        for (pid, fam), ids in sorted(by_pair.items())
        if len(ids) > 1
    ]


def open_gaps(ws: Workspace) -> list[dict]:
    """仍开放的证据空白：首用单元、熟练对照、家庭声明范围。"""
    gaps = []
    for adj in adjudicate_first_use_claims(ws):
        claim = adj["claim"]
        for cell in adj["gaps"]:
            gaps.append(
                {
                    "kind": "store_first_use",
                    "claim": claim["id"],
                    "task": cell["task"],
                    "group": cell["group"],
                    "have": cell["assigned"],
                    "need": cell["min_n"],
                    "config": {"latch": claim.get("latch"), "display": claim.get("display")},
                    "note": "首用名额为消耗性机会，不能用熟练者补齐",
                }
            )
    for adj in adjudicate_trained_claims(ws):
        for cell in adj["gaps"]:
            gaps.append(
                {
                    "kind": "trained",
                    "claim": adj["claim"]["id"],
                    "task": cell["task"],
                    "group": cell["group"],
                    "have": cell["n"],
                    "need": cell["min_n"],
                    "note": "需完成规定练习量的熟练观察",
                }
            )
    for row in trained_contrast(ws):
        if not row["noninferior"]:
            gaps.append(
                {
                    "kind": "trained_comparison",
                    "group": row["group"],
                    "have": None,
                    "need": None,
                    "note": "新-旧率差区间下限未高于非劣界，比较结论未闭合；第二期迁移不可用于宣称更优",
                }
            )
    for rep in home_card_reports(ws):
        claim = rep["claim"]
        if rep["status"] == "keep":
            continue
        cur = rep["current"]
        deficits = []
        if not cur["sufficient"]:
            deficits.append(f"有结果户数 {cur['with_results']}/{cur['min_n']}")
        if cur["success"] < cur["with_results"]:
            deficits.append(f"成功 {cur['success']}/{cur['with_results']} 户")
        if any(not c["valid"] for c in cur["cited"]):
            deficits.append("引用失效")
        gaps.append(
            {
                "kind": "home",
                "claim": claim["id"],
                "group": claim["group"],
                "device": claim["device"],
                "mat": claim["mat"],
                "tasks": list(claim["tasks"]),
                "claim_type": claim["claim_type"],
                "have": cur["with_results"],
                "need": cur["min_n"],
                "note": "；".join(deficits) + "；只能由家庭回访补足，店内试验无法提供家庭环境证据",
            }
        )
    return gaps


def unfillable_in_store(ws: Workspace) -> list[dict]:
    """即使多做一次店内试验也得不到证据的声明范围。"""
    return [g for g in open_gaps(ws) if g["kind"] == "home"]


def _entry_families(ws: Workspace, entry: dict, pid: str) -> set:
    if entry["tasks"]:
        return {task_family(ws, t) for t in entry["tasks"]}
    return allowed_families(ws, pid)


def candidate_projection(ws: Workspace, events: list | None = None) -> list[dict]:
    """候选安排对照：补哪些空白、消耗哪些首用机会、是否有效。

    状态：valid=可按提案执行；negotiate=资源冲突待协商；invalid=挤占已确认
    活动（或所属场次挤占已确认），不能按预期人头计为有效。
    """
    if events is None:
        events = contact_events(ws)
    entries = calendar_entries(ws)
    by_id = {e["id"]: e for e in entries}
    device_users = [e for e in entries if e["kind"] != "return_slot"]
    confirmed_keys = {
        (e["store"], e["at"], e["device"]) for e in device_users if e["status"] == "confirmed"
    }
    conflict_keys = {
        (c["store"], c["at"], c["device"]) for c in resource_conflicts(ws)
    }
    gaps = open_gaps(ws)
    pool = unassigned_pool(ws, events)
    candidates = [e for e in entries if e["status"] in ("candidate", "planned")]
    candidates.sort(key=lambda e: e["at"])
    consumed: dict = {}
    projections = []
    for e in candidates:
        key = (e["store"], e["at"], e["device"])
        proj = {
            "entry": e["id"],
            "kind": e["kind"],
            "status": "valid",
            "conflicts": [],
            "fills": [],
            "consumes": [],
            "notes": [],
        }
        if e["kind"] == "return_slot" and e.get("session"):
            session = by_id.get(e["session"])
            if session is not None:
                skey = (session["store"], session["at"], session["device"])
                if skey in confirmed_keys:
                    proj["status"] = "invalid"
                    proj["conflicts"].append(
                        f"所属场次 {session['id']} 挤占已确认活动的时段与设备"
                    )
                elif skey in conflict_keys:
                    proj["status"] = "negotiate"
                    proj["conflicts"].append(f"所属场次 {session['id']} 资源冲突待协商")
        elif key in confirmed_keys:
            proj["status"] = "invalid"
            proj["conflicts"].append("挤占已确认活动的时段与设备，不能按预期人头计为有效")
        elif key in conflict_keys:
            proj["status"] = "negotiate"
            proj["conflicts"].append("与同资源的其他安排冲突，待协商")
        comps = device_components(ws, e["device"]) or {}
        participant_groups = [participant_group(ws, p) for p in e["participants"]]
        for pid in e["participants"]:
            for f in sorted(_entry_families(ws, e, pid)):
                if not first_use_eligible(events, pid, f, e["at"]):
                    proj["notes"].append(f"{pid} 已接触 {f}，不能充当该族新人")
                elif (pid, f) in consumed:
                    proj["notes"].append(
                        f"{pid} 的 {f} 首用机会已在 {consumed[(pid, f)]} 消耗"
                    )
                else:
                    proj["consumes"].append(f"{pid} 的 {f} 首用机会")
                    consumed[(pid, f)] = e["id"]
        if e["kind"] == "store_slot" and not e["participants"] and e["tasks"]:
            needed = {task_family(ws, t) for t in e["tasks"]}
            able = [
                p["participant"]
                for p in pool
                if needed <= set(p["first_use_families"])
            ]
            if able:
                proj["notes"].append(f"可动用已登记未分派人手：{'、'.join(able)}")
            else:
                proj["notes"].append(
                    "已登记未分派人手无人能覆盖该位置全部动作族首用，需新招募"
                )
        for g in gaps:
            if g["kind"] == "store_first_use" and e["kind"] == "store_slot":
                if g["task"] not in e["tasks"]:
                    continue
                relevant = TASK_COMPONENTS.get(g["task"], ())
                if all(comps.get(c) == g["config"].get(c) for c in relevant):
                    who = participant_groups[0] if participant_groups else None
                    if who is None:
                        proj["fills"].append(
                            f"{g['claim']}:{g['task']}:{g['group']}（取决于招募到的分层）"
                        )
                    elif who == g["group"]:
                        proj["fills"].append(f"{g['claim']}:{g['task']}:{g['group']}")
                    else:
                        proj["notes"].append(
                            f"{g['claim']}:{g['task']} 需要 {g['group']}，现有参与者为 {who}，"
                            "对照不能落到不同能力人群"
                        )
            if g["kind"] == "home" and e["kind"] in ("return_slot", "session"):
                g_comps = device_components(ws, g["device"]) or {}
                if comps.get("latch") != g_comps.get("latch"):
                    continue
                if e["mat"] is not None and g["mat"] is not None and e["mat"] != g["mat"]:
                    continue
                for pid, who in zip(e["participants"], participant_groups):
                    if who != g["group"]:
                        continue
                    fams = _entry_families(ws, e, pid)
                    needed = {task_family(ws, t) for t in g["tasks"]}
                    if needed <= fams:
                        proj["fills"].append(
                            f"{g['claim']}（{g['group']} {g['device']} 垫={g['mat']}）"
                            f"可能由 {pid} 补足一户，待执行与回访确认"
                        )
        if not proj["fills"]:
            proj["notes"].append("不补任何仍开放的证据空白")
        projections.append(proj)
    return projections


def unassigned_pool(ws: Workspace, events: list | None = None) -> list[dict]:
    """已登记未分派的门店受试者：候选位置可动用的人手及其首用资格。"""
    if events is None:
        events = contact_events(ws)
    assigned = {a["participant"] for a in ws.stores.get("assignments", [])}
    pool = []
    for pid in ws.stores.get("participants", {}):
        if pid in assigned:
            continue
        fams = allowed_families(ws, pid)
        pool.append(
            {
                "participant": pid,
                "group": participant_group(ws, pid),
                "allowed": sorted(fams),
                "first_use_families": sorted(
                    f
                    for f in fams
                    if all(e["participant"] != pid or e["family"] != f for e in events)
                ),
            }
        )
    return pool

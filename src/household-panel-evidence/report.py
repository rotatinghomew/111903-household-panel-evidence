"""汇总各模块结论，渲染体验组可读的中文报告。"""
from __future__ import annotations

import math
from datetime import datetime

from .core import Workspace, contact_events
from .home import (
    corrected_observations,
    home_card_reports,
    roster_summary,
    supportable_home_scopes,
)
from .schedule import (
    candidate_projection,
    first_use_review,
    open_gaps,
    resource_conflicts,
    shared_first_use_conflicts,
    unassigned_pool,
    unfillable_in_store,
)
from .store import (
    adjudicate_first_use_claims,
    as_treated_listing,
    assignment_rows,
    itt_summary,
    store_card_reports,
)
from .training import (
    adjudicate_trained_claims,
    period2_listing,
    trained_card_reports,
    trained_contrast,
)


def full_report(ws: Workspace) -> dict:
    events = contact_events(ws)
    itt = [
        {"task": k[0], "arm": k[1], "group": k[2], **v}
        for k, v in sorted(itt_summary(ws, events).items())
    ]
    return {
        "store": {
            "assignments": assignment_rows(ws, events),
            "itt": itt,
            "as_treated": as_treated_listing(ws, events),
            "claims": adjudicate_first_use_claims(ws, events),
            "cards": store_card_reports(ws, events),
        },
        "trained": {
            "contrast": trained_contrast(ws),
            "period2": period2_listing(ws),
            "claims": adjudicate_trained_claims(ws),
            "cards": trained_card_reports(ws),
        },
        "home": {
            "roster": roster_summary(ws),
            "corrected": [
                {"id": oid, "fields": o["corrected_fields"]}
                for oid, o in corrected_observations(ws).items()
                if "corrected_fields" in o
            ],
            "cards": home_card_reports(ws),
            "scopes": supportable_home_scopes(ws),
        },
        "schedule": {
            "first_use_review": first_use_review(ws, events),
            "shared_first_use": shared_first_use_conflicts(ws),
            "conflicts": resource_conflicts(ws),
            "gaps": open_gaps(ws),
            "unfillable_in_store": unfillable_in_store(ws),
            "candidates": candidate_projection(ws, events),
            "pool": unassigned_pool(ws, events),
        },
    }


def to_jsonable(value):
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _ci(ci) -> str:
    lo, hi = ci
    if lo is None or (isinstance(lo, float) and math.isnan(lo)):
        return "—"
    return f"[{lo * 100:.1f}%, {hi * 100:.1f}%]"


def _kn(kn) -> str:
    return f"{kn[0]}/{kn[1]}"


def _render_store(lines, store):
    lines.append("== 门店首用试验（按原分派评估，实操换组不改分派）==")
    for row in store["assignments"]:
        outcome = row["outcome"]
        extra = ""
        if row["observed"]:
            flags = []
            if row["device_deviation"]:
                flags.append("现场设备非分派臂登记设备")
            if row["registry_mismatch"]:
                flags.append(
                    f"实际部件 {row['actual_config']} 与登记 {row['registered_config']} 不符"
                )
            if row["assignment_mismatch"]:
                flags.append("实际部件与分派臂不符")
            if not row["first_use"]:
                flags.append("观察时已非首用")
            if not row["consent_ok"]:
                flags.append("该动作族不在同意范围")
            extra = ("；" + "；".join(flags)) if flags else ""
        lines.append(
            f"  {row['assignment']} {row['participant']}({row['group']}) "
            f"{row['task']} 分派臂={row['arm']} → {outcome}{extra}"
        )
    if store["as_treated"]:
        lines.append("  另列（实际部件/设备与登记或分派不一致，不并入分派估计）：")
        for row in store["as_treated"]:
            lines.append(
                f"    {row['observation']}({row['assignment']}) 设备 {row['device']} "
                f"实际 {row['actual_config']} 结果 {row['outcome']}"
            )
    lines.append("  按原分派的结果分布（拒绝/无记录/失败分列）：")
    for cell in store["itt"]:
        lines.append(
            f"    {cell['task']} 臂={cell['arm']} {cell['group']}: 分派 {cell['assigned']} 人；"
            f"独立 {cell['independent']} 协助 {cell['assisted']} 失败 {cell['failed']} "
            f"无记录 {cell['not_observed']} 拒绝 {cell['refused']}"
        )
    lines.append("  首用声明复核：")
    for adj in store["claims"]:
        claim = adj["claim"]
        lines.append(
            f"  {claim['id']} 动作={'+'.join(claim['tasks'])} latch={claim.get('latch')} "
            f"用途=首用 分层={'+'.join(claim['groups'])}"
        )
        for cell in adj["cells"]:
            mark = "达标" if cell["sufficient"] else f"缺口（{cell['assigned']}/{cell['min_n']}）"
            lines.append(
                f"    {cell['task']} {cell['group']}: 独立 {cell['independent']}/{cell['assigned']} "
                f"{_pct(cell['rate'])} {_ci(cell['ci'])} {mark} 结果分布={cell['outcomes']}"
            )
        if not adj["fully_supported"]:
            lines.append("    → 无可展示的完整承诺；缺口保留，不以总体均值或其他动作补")
    for rep in store["cards"]:
        card = rep["card"]
        lines.append(
            f"  卡片 {card['id']}（{card['claim']}，{card['issued_at']} 发出）→ "
            f"{'继续可用' if rep['status'] == 'keep' else '停止用于新销售'}"
        )
        for c in rep["citations"]:
            lines.append(
                f"    引用 {c['observation']}: 发出时={'成立' if c['as_issued']['valid'] else '不成立'}"
                f"（{'; '.join(c['as_issued']['reasons']) or '—'}） "
                f"当前={'成立' if c['current']['valid'] else '不成立'}"
                f"（{'; '.join(c['current']['reasons']) or '—'}）"
            )
        for r in rep["reasons"]:
            lines.append(f"    原因：{r}")
        for r in rep.get("cautions", []):
            lines.append(f"    措辞限制：{r}")


def _render_trained(lines, trained):
    lines.append("== 熟练交叉试验（规定练习量 + 第一期对照）==")
    p2 = trained["period2"]
    if p2["excluded"]:
        for r in p2["excluded"]:
            lines.append(
                f"  练习量不足剔除：{r['id']}（{r['participant']} 第{r['period']}期 "
                f"{r['dose']} 次 < 规定）"
            )
    for row in trained["contrast"]:
        lines.append(
            f"  {row['group']}: 第一期 新 {_kn(row['new'])} {_ci(row['new_ci'])} vs "
            f"旧 {_kn(row['old'])} {_ci(row['old_ci'])}；率差 {_pct(row['diff'])} "
            f"{_ci(row['diff_ci'])} → 非劣效{'成立' if row['noninferior'] else '未确立'}"
        )
    lines.append(f"  第二期：{p2['carryover_note']}（合格 {len(p2['eligible'])} 条，配对 {len(p2['paired'])} 人）")
    for adj in trained["claims"]:
        claim = adj["claim"]
        for cell in adj["cells"]:
            mark = "达标" if cell["sufficient"] else f"缺口（{cell['n']}/{cell['min_n']}）"
            lines.append(
                f"  {claim['id']} {cell['task']} {cell['group']}: 独立 "
                f"{cell['independent']}/{cell['n']} {_pct(cell['rate'])} {_ci(cell['ci'])} {mark}"
            )
    for rep in trained["cards"]:
        card = rep["card"]
        lines.append(
            f"  卡片 {card['id']}（{card['claim']}）→ "
            f"{'继续可用' if rep['status'] == 'keep' else '停止用于新销售'}"
        )
        for c in rep["citations"]:
            lines.append(
                f"    引用 {c['observation']}: {'成立' if c['current']['valid'] else '不成立'}"
                f"（{'; '.join(c['current']['reasons']) or '—'}）"
            )
        for r in rep["reasons"]:
            lines.append(f"    原因：{r}")
        for r in rep.get("cautions", []):
            lines.append(f"    措辞限制：{r}")


def _render_home(lines, home):
    r = home["roster"]
    lines.append("== 家庭回访（按户核算，授权与结果分列）==")
    lines.append(
        f"  名册：计划动作 {r['planned']} 项；已观察 {r['observed']}；"
        f"有授权未得结果 {r['missing_result']}；未获相应授权 {r['not_authorized']}"
    )
    for c in home["corrected"]:
        lines.append(f"  更正生效：{c['id']} 字段 {','.join(c['fields'])}")
    for rep in home["cards"]:
        claim = rep["claim"]
        cur = rep["current"]
        issued = rep["as_issued"]
        lines.append(
            f"  卡片 {claim['id']}（{claim['claim_type']} {'+'.join(claim['tasks'])} "
            f"{claim['device']} 垫={claim['mat']} {claim['group']}）→ "
            f"{'继续可用' if rep['status'] == 'keep' else '停止用于新销售'}"
        )
        lines.append(
            f"    发出时依据：{issued['success']}/{issued['with_results']} 户 "
            f"{_pct(issued['rate'])}；当前：{cur['success']}/{cur['with_results']} 户 "
            f"{_pct(cur['rate'])} {_ci(cur['ci'])}；"
            f"有授权未得结果 {cur['missing_result']} 户；未获授权 {cur['not_authorized']} 户；"
            f"配置不符 {cur['config_mismatch']} 户"
        )
        for c in cur["cited"]:
            lines.append(
                f"    引用 {c['observation']}: {'成立' if c['valid'] else '不成立'}"
                f"（{'; '.join(c['reasons']) or '—'}）"
            )
        for reason in rep["reasons"]:
            lines.append(f"    原因：{reason}")
        for caution in rep.get("cautions", []):
            lines.append(f"    措辞限制：{caution}")
    lines.append("  现有回访可支撑的范围（证据量达标）：")
    for s in home["scopes"]:
        if s["sufficient"]:
            warn = "；存在失败户，按实际率表述" if s["success"] < s["with_results"] else ""
            lines.append(
                f"    {s['claim']['group']} {s['claim']['device']} 垫={s['claim']['mat']} "
                f"{s['claim']['claim_type']}({'+'.join(s['claim']['tasks'])}): "
                f"{s['success']}/{s['with_results']} 户 {_pct(s['rate'])} {_ci(s['ci'])}{warn}"
            )


def _gap_label(g: dict) -> str:
    if g["kind"] == "store_first_use":
        return f"{g['claim']} {g['task']} {g['group']}"
    if g["kind"] == "trained":
        return f"{g['claim']} {g['task']} {g['group']}"
    if g["kind"] == "trained_comparison":
        return f"熟练对照 {g['group']}"
    if g["kind"] == "home":
        return f"{g['claim']} {g['group']} {g['device']} 垫={g['mat']} ({'+'.join(g['tasks'])})"
    return g.get("claim") or g["kind"]


def _gap_have(g: dict) -> str:
    return "—" if g.get("have") is None else f"{g['have']}/{g['need']}"


_CANDIDATE_STATUS = {
    "valid": "可按提案执行",
    "negotiate": "待协商",
    "invalid": "无效（挤占已确认）",
}


def _render_schedule(lines, sch):
    lines.append("== 下一轮排期（首用名额为消耗性机会）==")
    for item in sch["first_use_review"]:
        if item["status"] != "eligible":
            lines.append(
                f"  待协商：{item['entry']} {item['participant']} 已接触 "
                f"{'+'.join(item['burned_families'])}（保留首用：{'+'.join(item['still_first']) or '无'}）"
                f"——位置不回到可分配池，需换人或重新协商"
            )
    for c in sch["conflicts"]:
        ids = "+".join(e["id"] for e in c["entries"])
        lines.append(f"  资源冲突：{c['store']} {c['at'].isoformat()} {c['device']} 被 {ids} 同时占用")
    for s in sch["shared_first_use"]:
        lines.append(
            f"  首用冲突：{s['participant']} 的 {s['family']} 被 {'+'.join(s['entries'])} 同时要求首次接触"
        )
    lines.append("  仍开放的证据空白：")
    for g in sch["gaps"]:
        lines.append(f"    [{g['kind']}] {_gap_label(g)}: 现有 {_gap_have(g)}；{g['note']}")
    if sch["unfillable_in_store"]:
        lines.append("  店内试验无法补足的声明（需家庭回访）：")
        for g in sch["unfillable_in_store"]:
            lines.append(f"    {_gap_label(g)}")
    lines.append("  候选安排对照：")
    for p in sch["candidates"]:
        lines.append(
            f"    {p['entry']}（{p['kind']}）{_CANDIDATE_STATUS[p['status']]}"
        )
        for x in p["conflicts"]:
            lines.append(f"      冲突：{x}")
        for x in p["fills"]:
            lines.append(f"      可补：{x}")
        for x in p["consumes"]:
            lines.append(f"      消耗：{x}")
        for x in p["notes"]:
            lines.append(f"      注意：{x}")
    if sch["pool"]:
        lines.append("  已登记未分派人手：")
        for p in sch["pool"]:
            lines.append(
                f"    {p['participant']}（{p['group']}）同意 {'+'.join(p['allowed'])}；"
                f"仍具首用资格 {'+'.join(p['first_use_families']) or '无'}"
            )


_RENDERERS = {
    "store": _render_store,
    "trained": _render_trained,
    "home": _render_home,
    "schedule": _render_schedule,
}


def render_text(report: dict, command: str = "report") -> str:
    lines: list[str] = []
    if command == "gaps":
        lines.append("== 仍开放的证据空白 ==")
        for g in report["schedule"]["gaps"]:
            lines.append(f"  [{g['kind']}] {_gap_label(g)}: 现有 {_gap_have(g)}；{g['note']}")
        return "\n".join(lines)
    keys = list(_RENDERERS) if command == "report" else [command]
    for i, key in enumerate(keys):
        if i:
            lines.append("")
        _RENDERERS[key](lines, report[key])
    return "\n".join(lines)

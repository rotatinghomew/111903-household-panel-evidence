"""载入工作区资料，并提供接触史、部件时间线等共同基础。

数据文件（默认 data/ 下）：
- two_stores.json        门店首用试验：分派、观察、部件与接触通知、预约
- training_register.json 熟练交叉试验、练习记录与已发行卡片台账
- home_followup.json     家庭回访计划与观察、更正、家庭说明卡、下一轮候选

贯穿各模块的两条规则：
1. 首用按“动作族”判定：示范、旁观、训练后退出都算已接触该族，
   与是否见过某一型号无关。
2. 部件以“实际生效时间”为准：换件通知按 occurred_at 生效，
   known_at 只决定体验组何时获知（用于还原发卡时的认知）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# 每个动作实际依赖的部件。换件只影响依赖它的动作；
# 其余动作的证据可沿用到“未变化的操作条件”，但同外观不等于同一干预。
TASK_COMPONENTS = {
    "jar_open": ("latch",),
    "scale_read": ("display",),
}

# 结果类别：拒绝观察、没有完成记录、实际操作失败是三回事，不得合并。
OUTCOME_CATEGORIES = ("independent", "assisted", "failed", "not_observed", "refused")

# 出现这些结果说明参与者确实接触过该动作族（首用资格随之消耗）。
CONTACT_OUTCOMES = ("independent", "assisted", "failed")

STORE_FILE = "two_stores.json"
TRAINING_FILE = "training_register.json"
HOME_FILE = "home_followup.json"


@dataclass
class Workspace:
    stores: dict
    training: dict
    home: dict


def load_workspace(data_dir: str | Path = "data") -> Workspace:
    root = Path(data_dir)

    def read(name: str) -> dict:
        return json.loads((root / name).read_text(encoding="utf-8"))

    return Workspace(
        stores=read(STORE_FILE), training=read(TRAINING_FILE), home=read(HOME_FILE)
    )


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text)


def task_family(ws: Workspace, task: str) -> str:
    return ws.stores["tasks"][task]["family"]


def participant_group(ws: Workspace, pid: str) -> str | None:
    """能力分层：门店名册、熟练组名册、家庭候选名册依次查找。"""
    if pid in ws.stores.get("participants", {}):
        return ws.stores["participants"][pid]
    for row in ws.training.get("participants", []):
        if row["participant"] == pid:
            return row["group"]
    for row in ws.home.get("household_candidates", []):
        if row["participant"] == pid:
            return row["group"]
    return None


def allowed_families(ws: Workspace, pid: str) -> set[str]:
    """观察同意范围（按动作族）。撤回未来参与不抹去吃已允许的历史观察。"""
    for row in ws.stores.get("observation_permissions", []):
        if row["participant"] == pid:
            return set(row["allowed_families"])
    for row in ws.training.get("participants", []):
        if row["participant"] == pid:
            return set(row["allowed_families"])
    for row in ws.home.get("household_candidates", []):
        if row["participant"] == pid:
            return set(row["allowed"])
    return set()


def contact_events(ws: Workspace) -> list[dict]:
    """全部可追踪接触，按动作族归集。

    来源：门店正式观察、门店接触通知（示范也算）、熟练组练习与正式观察、
    家庭回访观察、家庭补报的旁观接触。known 记录体验组获知时间，
    用于按发卡时点还原“当时可知”的接触史。
    """
    events: list[dict] = []

    def add(pid, family, at, kind, source, known=None):
        events.append(
            {
                "participant": pid,
                "family": family,
                "at": parse_time(at),
                "kind": kind,
                "source": source,
                "known": parse_time(known) if known else parse_time(at),
            }
        )

    assignments = {a["id"]: a for a in ws.stores.get("assignments", [])}
    for obs in ws.stores.get("observations", []):
        if obs.get("outcome") not in CONTACT_OUTCOMES:
            continue
        a = assignments[obs["assignment"]]
        add(a["participant"], task_family(ws, a["task"]), obs["at"], "attempt", obs["id"])
    for notice in ws.stores.get("contact_notices", []):
        add(
            notice["participant"],
            notice["family"],
            notice["occurred_at"],
            notice["kind"],
            notice["id"],
            notice.get("known_at"),
        )
    for row in ws.training.get("practice", []):
        add(
            row["participant"],
            task_family(ws, row["task"]),
            row["at"],
            "practice",
            f"practice:{row['participant']}:{row['period']}:{row['attempt']}",
        )
    for obs in ws.training.get("observations", []):
        add(obs["participant"], task_family(ws, obs["task"]), obs["at"], "trained_attempt", obs["id"])
    visits = {v["id"]: v for v in ws.home.get("visit_plan", [])}
    for obs in ws.home.get("observations", []):
        visit = visits[obs["visit"]]
        add(
            visit["participant"],
            task_family(ws, obs["task"]),
            obs["occurred"],
            "home_attempt",
            obs["id"],
            obs.get("recorded"),
        )
    for row in ws.home.get("additional_contacts", []):
        add(
            row["participant"],
            row["family"],
            row["occurred"],
            row["kind"],
            f"additional:{row['participant']}:{row['family']}",
            row.get("known"),
        )
    events.sort(key=lambda e: e["at"])
    return events


def first_use_eligible(events: list[dict], pid: str, family: str, when: datetime) -> bool:
    """when 之前无任何该动作族接触才算首用。"""
    return all(
        not (e["participant"] == pid and e["family"] == family and e["at"] < when)
        for e in events
    )


def device_components(ws: Workspace, device: str) -> dict | None:
    """登记部件（门店设备或熟练组设备两个命名空间都查）。"""
    if device in ws.stores.get("devices", {}):
        return dict(ws.stores["devices"][device])
    if device in ws.training.get("devices", {}):
        return dict(ws.training["devices"][device])
    return None


def device_config_at(
    ws: Workspace, device: str, when: datetime, known_before: datetime | None = None
) -> dict:
    """设备在 when 时刻的实际部件 = 登记部件 + 已生效换件通知。

    known_before 截断“体验组何时获知”：用于还原卡片发出时所依据的部件认知；
    发现实际换件早于登记时，当前核定（known_before=None）按真实部件重算。
    """
    config = device_components(ws, device) or {}
    notices = [n for n in ws.stores.get("component_notices", []) if n["device"] == device]
    notices.sort(key=lambda n: parse_time(n["occurred_at"]))
    for n in notices:
        if parse_time(n["occurred_at"]) > when:
            continue
        if known_before is not None and parse_time(n["known_at"]) > known_before:
            continue
        for key, value in n.items():
            if key not in ("id", "device", "occurred_at", "known_at"):
                config[key] = value
    return config


def expected_devices(ws: Workspace, arm: str) -> list[str]:
    """分派臂对应的登记设备（本研究臂名与 latch 同名：old/new）。"""
    return [
        d for d, comps in ws.stores.get("devices", {}).items() if comps.get("latch") == arm
    ]

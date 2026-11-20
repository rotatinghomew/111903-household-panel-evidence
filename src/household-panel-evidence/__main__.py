"""命令行入口：复核声明、查看证据缺口、比较下一轮候选安排。"""
from __future__ import annotations

import argparse
import json
import sys

from .core import load_workspace
from .report import full_report, render_text, to_jsonable


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="household-panel-evidence",
        description="体验组证据复核与补测排期工具（本地、离线）",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="report",
        choices=["report", "store", "trained", "home", "schedule", "gaps"],
        help="report=完整报告；store=门店首用；trained=熟练交叉；home=家庭回访；schedule=排期；gaps=证据空白",
    )
    parser.add_argument("--data-dir", default="data", help="数据目录（默认 data/）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)
    ws = load_workspace(args.data_dir)
    report = full_report(ws)
    if args.json:
        json.dump(to_jsonable(report), sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(render_text(report, args.command))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

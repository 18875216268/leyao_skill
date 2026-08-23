#!/usr/bin/env python3
"""本机工具动态发现：不维护注册清单，引导 AI 自主查本机已装技能。

原则（用户拍板）：工具不硬集成、不预注册——BRF 在工具域无匹配时，
扫描 ~/.workbuddy/skills/ 下含 scripts 的技能，按问题关键词过滤，
返回「可用工具 + 契约文档路径」，AI 读取 SKILL.md 后自主调用。

CLI：
  python tools_discovery.py list                  # 列出全部本机工具技能
  python tools_discovery.py find "<问题>"          # 按关键词找相关工具
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent          # brf/scripts/sources

def _skills_dir() -> Path | None:
    home = Path.home()
    cand = home / ".workbuddy" / "skills"
    return cand if cand.is_dir() else None


def scan_tools():
    """扫描本机技能目录：含 SKILL.md 且含 scripts 目录的技能视为可用工具。"""
    skills = _skills_dir()
    if skills is None:
        return []
    out = []
    for sub in sorted(skills.iterdir()):
        if not sub.is_dir():
            continue
        if (sub / "SKILL.md").exists() and (sub / "scripts").is_dir():
            out.append({
                "name": sub.name,
                "path": str(sub),
                "docs": str(sub / "SKILL.md"),
                "scripts": str(sub / "scripts"),
            })
    return out


try:
    from common import clean_q as _clean_q
    from common import relevance_2char
except ImportError:
    from scripts.common import clean_q as _clean_q
    from scripts.common import relevance_2char


def _relevant(tool, q):
    """工具相关性：问题关键词与技能名 2 字滑窗交集（common.relevance_2char）。"""
    if not q:
        return True
    return relevance_2char(q, tool.get("name") or "")


def find_tools(question: str):
    """按问题关键词发现相关本机工具，返回引导。"""
    q = _clean_q(question or "")
    tools = [t for t in scan_tools() if _relevant(t, q)]
    if not tools:
        return {"ok": False, "reason": "no_tool_found", "question": question,
                "hint": "本机 skills 目录未发现相关工具（含 scripts 的技能）"}
    lines = [f"{t['name']}（契约：{t['docs']}）" for t in tools]
    return {
        "ok": True, "source": "local-tools", "discovered": len(tools),
        "answer": ("本机发现可用工具（AI 自主调用）：" + "；".join(lines) +
                   "。读取对应 SKILL.md 契约后自行调用其 scripts；凭证/登录走工具自身（approval）"),
        "tools": tools,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="本机工具动态发现（引导 AI 自主查工具）")
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("list", help="列出全部本机工具技能")
    f = s.add_parser("find", help="按问题关键词发现相关工具")
    f.add_argument("question")
    args = p.parse_args(argv)
    out = {"ok": True, "tools": scan_tools()} if args.cmd == "list" else find_tools(args.question)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 4


if __name__ == "__main__":
    raise SystemExit(main())

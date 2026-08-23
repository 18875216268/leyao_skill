"""CLI 适配器：委托外部脚本执行查询（如乐药云智库桥接）。

领域无关：资产声明
  source        脚本路径（相对 knowledge-hub 根 或 绝对路径）
  command_map   need_type → 命令模板列表，{q} 为问题占位
示例：
  leyou-search: {"adapter":"cli", "source":"scripts/sources/leyou_bridge.py",
                 "command_map": {"tool": ["search", "{q}"]}}
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .base import Adapter

HUB_DIR = Path(__file__).resolve().parent.parent.parent


def run_script(script, *args):
    """运行 python 脚本并解析 JSON：整体优先，失败逐行。"""
    try:
        r = subprocess.run([sys.executable, str(script), *args],
                           capture_output=True, text=True, timeout=360)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": "EXEC_FAIL", "detail": str(e)}
    text = r.stdout or ""
    out = None
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        for line in reversed(text.strip().splitlines()):
            try:
                out = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if out is None:
        return {"ok": False, "error": "UNPARSEABLE", "exit_code": r.returncode,
                "stdout": text[:400]}
    out["exit_code"] = r.returncode
    return out


class CliAdapter(Adapter):
    id = "cli"

    def match(self, asset):
        return asset.get("adapter") == "cli" or asset.get("mode") == "cli"

    def query(self, asset, need_type, question, **kwargs):
        script = Path(asset.get("source") or "")
        if not script.is_absolute():
            script = HUB_DIR / script
        if not script.exists():
            return {"ok": False, "reason": "dependency_missing", "detail": str(script),
                    "selected": asset.get("asset_id")}
        cmd_map = asset.get("command_map") or {}
        template = cmd_map.get(need_type) or cmd_map.get("*") or ["search", "{q}"]
        out = _run(script, template, question)
        if not out.get("ok"):
            return out
        hits = out.get("list") or out.get("hits") or out.get("items")
        if not hits:
            # answer 型结果（引导/单值，如 BI 取数入口）：直接返回可用
            if out.get("answer"):
                return {
                    "ok": True, "need_type": need_type,
                    "answer": str(out["answer"]),
                    "source": asset.get("asset_id"), "category": asset.get("category"),
                    "trust": asset.get("trust"), "confidence": 0.8,
                    "version": "manual", "raw": out,
                }
            return {"ok": False, "reason": "no_match", "selected": asset.get("asset_id"),
                    "need_type": need_type, "question": question}
        return {
            "ok": True, "need_type": need_type,
            "answer": _format(out, template),
            "source": asset.get("asset_id"), "category": asset.get("category"),
            "trust": asset.get("trust"), "confidence": 0.8,
            "version": "manual",
            "hits": [{"name": str(h.get("name") or "").replace("<em>", "").replace("</em>", ""),
                      "slug": h.get("slug")} for h in hits[:5]],
            "raw": out,
        }


def _run(script, template, question):
    args = [p.replace("{q}", question or "") for p in template]
    return run_script(script, *args)


def _format(out, template):
    """把脚本输出整理为可读 answer（列表优先取 name/slug，去高亮）。"""
    hits = out.get("list") or out.get("hits") or out.get("items")
    if isinstance(hits, list) and hits:
        parts = []
        for h in hits:
            name = str(h.get("name") or h.get("term") or "").replace("<em>", "").replace("</em>", "")
            slug = h.get("slug")
            parts.append(f"{name}（{slug}）" if slug else name)
        return "；".join(parts[:5]) or "无结果"
    return str(out.get("answer") or out.get("message") or "完成")

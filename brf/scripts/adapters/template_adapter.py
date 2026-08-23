"""模板适配器：返回模板类资产的可用模板清单。

领域无关：资产声明 source 指向模板目录/文件（相对插件根或绝对路径）；
找不到时向上遍历查找含 *.template.json 的 templates 目录（插件可移动）。
"""
from __future__ import annotations

from pathlib import Path

from .base import Adapter

HUB_DIR = Path(__file__).resolve().parent.parent.parent


def _resolve_templates(rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute() and p.exists():
        return p
    cand = HUB_DIR / p
    if cand.exists():
        return cand
    for anc in HUB_DIR.parents:
        t = anc / "templates"
        if t.is_dir() and list(t.glob("*.template.json")):
            return t
    return cand


class TemplateAdapter(Adapter):
    id = "template"

    def match(self, asset):
        return asset.get("adapter") == "template" or asset.get("category") == "template"

    def query(self, asset, need_type, question, **kwargs):
        path = _resolve_templates(str(asset.get("source") or ""))
        if not path.exists():
            return {"ok": False, "reason": "template_missing", "detail": str(path),
                    "selected": asset.get("asset_id")}
        files = sorted(p.name for p in (path.rglob("*") if path.is_dir() else [path]))
        return {
            "ok": True, "need_type": need_type,
            "answer": "可用模板：" + "、".join(files[:10]) if files else "模板目录为空",
            "source": asset.get("asset_id"), "category": asset.get("category"),
            "trust": asset.get("trust"), "confidence": 0.9,
            "version": "manual", "templates": files[:10],
        }

"""池适配器：读云端记忆三库（items[] 结构，tier=inject/session）。

领域无关：source 为云端 pool 端点 URL（CORS 开放）；查询按 need_type 映射
category/kind/tier 参数，返回 items[] 候选（authority 优先排序由 resolve 层处理）。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .base import Adapter

# 绕过系统代理（Python 进程内显式设置，防止 HTTP_PROXY 导致 403）
os.environ["NO_PROXY"] = "*"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(opener)

POOL_URL = "https://lyzsk.cfdaili.top/api/pool"

STOPWORDS = ["怎么", "什么", "如何", "是", "的", "计算", "算", "定义", "公式",
             "有哪些", "多少", "请", "查", "一下", "?", "？", "为", "了", "吗", "呢",
             "哪里", "哪儿", "哪些", "哪个"]


def extract_keyword(question):
    q = (question or "")
    for s in STOPWORDS:
        q = q.replace(s, "")
    return (q.strip() or question or "").strip()[:24]

# need_type → 查询参数（category 对齐 pool 的 CATEGORIES）
NEED_MAP = {
    "term": {"category": "term", "kind": "fact"},
    "caliber": {"category": "caliber", "kind": "fact"},
    "process": {"category": "method", "kind": "procedure"},
    "template": {"category": "template", "kind": "procedure"},
    "data": {"kind": "fact"},
    "tool": {"kind": "procedure"},
}
# 口径诉求只查注入库（authority 权威）
CALIBER_TIER = "inject"


def _fetch(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 knowledge-hub/0.3"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


class PoolAdapter(Adapter):
    id = "pool"

    def match(self, asset):
        return asset.get("adapter") == "pool" or (not asset.get("adapter") and asset.get("mode") == "pool")

    def query(self, asset, need_type, problem, source=None, leyou=None):
        q = (problem or "").strip()
        params = {"limit": 3}
        mapping = NEED_MAP.get(need_type, {})
        params.update(mapping)
        # tier 判定：资产声明 pool_tier 优先；缺省按 need_type（caliber 只认注入库 authority）
        tier = asset.get("pool_tier") or (CALIBER_TIER if need_type == "caliber" else "session")
        params["tier"] = tier
        if q:
            params["q"] = extract_keyword(q)
        url = POOL_URL + "?" + urllib.parse.urlencode(params)
        data = _fetch(url)
        items = (data or {}).get("items") or []
        if not items:
            return {"ok": False, "reason": "no_match", "selected": asset.get("asset_id"),
                    "need_type": need_type, "question": problem}
        tier = params["tier"]
        lines = []
        hits = []
        for it in items:
            title = it.get("title", "")
            content = it.get("content", "")
            trust = it.get("trust") or ("authority" if tier == "inject" else "reference")
            lines.append(f"[{trust}] {title}: {content[:150]}")
            hits.append({
                "name": title, "definition": content,
                "trust": trust, "source": it.get("tier", tier),
                "pool_id": it.get("id"),
            })
        return {
            "ok": True, "need_type": need_type,
            "answer": "\n".join(lines[:5]),
            "source": f"pool-{tier}", "category": params.get("category", "experience"),
            "trust": "authority" if tier == "inject" else "reference",
            "confidence": 0.9 if tier == "inject" else 0.8,
            "keyword": params.get("q", ""), "hits": hits, "tier": tier,
        }


adapter = PoolAdapter()

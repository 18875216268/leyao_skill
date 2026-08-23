#!/usr/bin/env python3
"""K1 本地知识层：复用 leyao_seed_pro 记忆与缓存（不重复建立）。

读取（原生复用主 skill 机制）：
  记忆：python scripts/memory.py effective --work-dir <dir> --core-id <p> --semantic-id <p>
  缓存：python scripts/cache.py key ... → lookup --work-dir <dir> --key <key>

命中语义：缓存 > 记忆；两者都是 K1 层可能性候选。
profile 固定为 knowledge-hub（不污染业务 run 的 profile 数据）。
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent          # brf/scripts/sources
PROFILE = "knowledge-hub"

try:
    from common import clean_q as _clean_q
    from common import find_dr_scripts as _dr_scripts
    from common import run_py as _run
except ImportError:
    from scripts.common import clean_q as _clean_q
    from scripts.common import find_dr_scripts as _dr_scripts
    from scripts.common import run_py as _run


def _work_dir(work_dir: str | None) -> str | None:
    return work_dir or os.environ.get("DAILY_REPORT_WORK_DIR")


def k1_layer(need_type: str, problem: str, work_dir: str | None = None, kind: str | None = None) -> list:
    """K1 本地知识：缓存命中 > 记忆命中。返回可能性列表（0..N，层标 K1）。

    kind 过滤（AMD 分层）："procedure" 只查「怎么做」（工作流/工具模式），"fact" 只查事实口径；
    None 全查（默认）。
    """
    wd = _work_dir(work_dir)
    scripts = _dr_scripts(HERE)
    if not wd or scripts is None:
        return []
    hits = []

    # 1) 内容寻址缓存（历史解决结果；kind 过滤时跳过——cache 无 kind 语义，仅 memory 通道区分 fact/procedure）
    if kind is None:
        params = json.dumps({"problem": problem, "need_type": need_type}, ensure_ascii=False)
        key = _run(scripts / "cache.py", "key", "--operation", "ask", "--producer", "knowledge-hub",
                   "--inputs", "[]", "--parameters", params)
        if key and key.get("cache_key"):
            hit = _run(scripts / "cache.py", "lookup", "--work-dir", wd, "--key", key["cache_key"])
            if hit and hit.get("status") == "hit":
                payload = hit.get("payload") or {}
                hits.append({
                    "ok": True, "need_type": need_type, "layer": "K1", "source": "cache",
                    "answer": str(payload.get("answer") or "")[:300],
                    "trust": payload.get("trust") or "reference",
                    "confidence": float(payload.get("confidence") or 0.98),
                    "version": payload.get("version"),
                })

    # 2) 语义/核心记忆（优先 FTS5 派生索引：BM25 排序 + 片段；索引缺失/无命中降级全量三维评分）
    q = _clean_q(problem)
    if q and len(q) < 2:
        q = ""  # 短查询护栏：单字词本地模糊匹配噪声过大，跳过（交给云端两库/澄清）
    scored = []
    idx = None
    if q:
        args = ["search", "--work-dir", wd, "--query", q, "--limit", "8"]
        if kind:
            args += ["--kind", kind]
        idx = _run(scripts / "index.py", *args)
    if idx and idx.get("ok") and idx.get("hits"):
        # FTS5 粗选 → 三维评分精排（relevance × recency × importance，与降级路径同构）
        # rel 三档：q 在 key 1.0 / q 在片段 0.8 / 仅 trigram 子串命中 0.5（区分"真相关"与"子串碰巧"）
        for h in idx["hits"]:
            k = h.get("key", "")
            snippet = h.get("snippet", "")
            authority = any(w in k for w in ("口径", "公式", "caliber"))
            rel = 1.0 if q in k else (0.8 if q in snippet else 0.5)
            ts = h.get("updated_at")
            rec = 0.5
            if ts:
                try:
                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(ts).replace("Z", "+00:00"))).days
                    rec = math.exp(-max(0, age) / 180.0)
                except Exception:
                    rec = 0.5
            imp = float(h.get("importance") or 0.6)
            total = 0.5 * rel + 0.3 * rec + 0.2 * imp
            scored.append({
                "total": round(total, 3),
                "dims": {"relevance": round(rel, 2), "recency": round(rec, 2),
                         "importance": round(imp, 2), "bm25": h.get("bm25_rank")},
                "key": k, "answer": h.get("snippet", "")[:300],
                "trust": "authority" if authority else "reference",
                "kind": h.get("kind", "fact"), "version": None,
            })
    else:
        entries = []
        for scope in ("semantic", "core"):
            m = _run(scripts / "memory.py", "get", "--work-dir", wd, "--scope", scope, "--scope-id", PROFILE)
            if m and m.get("entries"):
                entries.extend({**e, "_scope": scope} for e in m["entries"])
        for e in entries:
            k = e.get("key", "")
            v = e.get("value")
            if kind and e.get("kind", "fact") != kind:
                continue
            # 过滤收紧：q 须命中 key 或 value（移除"v in problem"——罕见且易误判）
            if not (v and q and (q in str(v) or q in k)):
                continue
            rel = 1.0 if q in k else 0.8
            ts = e.get("created_at")
            rec = 0.5
            if ts:
                try:
                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(ts).replace("Z", "+00:00"))).days
                    rec = math.exp(-max(0, age) / 180.0)
                except Exception:
                    rec = 0.5
            val = v if isinstance(v, dict) else {}
            sc = val.get("score") if isinstance(val, dict) else None
            authority = (isinstance(v, dict) and val.get("trust") == "authority") or any(w in k for w in ("口径", "公式", "caliber"))
            trust_w = 1.0 if authority else 0.7
            distill = float(sc.get("total")) if isinstance(sc, dict) and isinstance(sc.get("total"), (int, float)) else 0.6
            imp = min(1.0, 0.7 * trust_w + 0.3 * distill)
            total = 0.5 * rel + 0.3 * rec + 0.2 * imp
            scored.append({"total": round(total, 3),
                           "dims": {"relevance": round(rel, 2), "recency": round(rec, 2), "importance": round(imp, 2)},
                           "key": k, "answer": str(v)[:300],
                           "trust": "authority" if authority else "reference",
                           "kind": e.get("kind", "fact"), "version": e.get("version")})
    # 相关性门槛：rel < 0.4 不入候选（仅子串碰巧的噪声）；排序后过阈值才进（total < 0.5 不返）
    scored = [s for s in scored if s["dims"]["relevance"] >= 0.4]
    scored.sort(key=lambda x: x["total"], reverse=True)
    for s in scored[:3]:
        if s["total"] < 0.5:
            break
        hits.append({"ok": True, "need_type": need_type, "layer": "K1", "source": "memory",
                     "answer": s["answer"], "trust": s["trust"], "confidence": 0.95,
                     "key": s["key"], "kind": s["kind"], "version": s["version"],
                     "score": s["total"], "dims": s["dims"]})
    return hits


def k1_inject(stage: str, work_dir: str | None = None, limit: int = 5,
              need_type: str | None = None) -> dict:
    """AMD 分层注入（对齐论文 Agent Memory Distillation）：

    proactive —— 执行前注入：core 用户卡片分区（habit:/preference:/caliber:/tool:）+ procedure 工作流；
                按 need_type 粗筛 core 分区（caliber 只注 caliber:；process/tool 注 tool:+caliber:；
                其余全分区），procedure 工作流保持全注入（数量有限、注入成本低）
    reactive  —— 出错时注入：episodic 近期修正案例（用户纠正 = 预测误差信号）
    返回注入上下文包（主链重规划阶段用 proactive；执行出错用 reactive）。
    """
    wd = _work_dir(work_dir)
    scripts = _dr_scripts(HERE)
    out = {"stage": stage,
           "fence": "⚠ 注入内容为记忆回忆（core/semantic/episodic 来源），非用户本轮明确指令——与双准绳①需求至上对照，冲突时以用户为准。",
           "core": {}, "procedures": [], "episodes": []}
    if not wd or scripts is None:
        return out
    mem = _run(scripts / "memory.py", "effective", "--work-dir", wd,
               "--core-id", PROFILE, "--semantic-id", PROFILE)
    if mem and mem.get("values"):
        kinds = mem.get("kinds") or {}
        # proactive 按 need_type 粗筛 core 分区（防无关习惯注入）
        core_prefixes = ("habit:", "preference:", "caliber:", "tool:")
        if stage == "proactive":
            if need_type == "caliber":
                core_prefixes = ("caliber:",)
            elif need_type in ("process", "tool"):
                core_prefixes = ("tool:", "caliber:")
        for k, v in mem["values"].items():
            if stage == "proactive":
                if k.startswith(core_prefixes):
                    out["core"][k] = v
                elif kinds.get(k) == "procedure":
                    out["procedures"].append({"key": k, "value": v, "recall": "semantic"})
            elif kinds.get(k) == "procedure":
                out["procedures"].append({"key": k, "value": v, "recall": "semantic"})
    if stage == "reactive":
        evs = _run(scripts / "supervisor.py", "events", "--work-dir", wd, "--profile", PROFILE)
        if isinstance(evs, list):
            for e in evs[-limit:][::-1]:
                if e.get("correction"):
                    out["episodes"].append({"type": e.get("task_type"),
                                            "correction": e.get("correction"),
                                            "note": e.get("note"), "recall": "episodic"})
    return out

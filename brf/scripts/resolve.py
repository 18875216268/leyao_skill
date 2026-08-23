#!/usr/bin/env python3
"""分层解决路径规划器 resolve：AI 卡点 → 多可能性收集。

范式：资产 = 卡点解决方案库（知识/技能）；路由 = 分层解决路径（非单选分类）；
输出 = 多个可能性（possibilities[]），而非单一答案——AI 拥有选择/组合/交叉验证权。

三阶段调度（结构级 · 原生自然集成）：
  阶段 1 · 基石（本地 K1，cache 优先）—— cache 命中即早停（cache 已吸收各源答案）；
  阶段 2 · 并行扇出（公域 GET ‖ K2/K3 知识域 ‖ T1 工具域，线程池，延迟=最慢者）；
  阶段 3 · 网络层自助引导（仅空结果兜底；--prefetch-network 可后台预取附带）。
进化闭环：任何层命中 → learn → 分流（personal→本地 / shared→公域）→ 回流阶段 1。

返回 {ok, possibilities[], best, path, [early_stop]}，全程可审计。
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

try:
    from .registry import get_asset
    from .infer import infer_need_type
    from .adapters import get_adapter
    from .sources.k1_memory import k1_layer
    from .common import clean_q
except ImportError:
    from registry import get_asset
    from infer import infer_need_type
    from adapters import get_adapter
    from sources.k1_memory import k1_layer
    from common import clean_q

KNOWLEDGE_CATEGORIES = {"knowledge", "method", "data", "template"}
TOOL_CATEGORIES = {"tool"}
TRUST_ORDER = {"authority": 0, "reference": 1, "candidate": 2}
MAX_POSSIBILITIES = 5
STAGE2_WORKERS = 3  # 并行扇出上限（公域/知识/工具三路）


def _layer_of(asset):
    """资产所属解决域：tool → 工具域；其余 → 知识域。"""
    return "tool" if asset.get("category") in TOOL_CATEGORIES else "knowledge"


def _try_assets(registry, asset_ids, need_type, problem, source=None, leyou=None,
                collect=False, max_hits=MAX_POSSIBILITIES, skip_pool=False):
    """按候选顺序尝试一组资产：collect=True 收集全部 ok（多可能性），否则返回首个。

    skip_pool=True 跳过 pool 资产（其查询已由 pool_layer 统一覆盖，避免重复云端 GET）。
    """
    hits = []
    for aid in asset_ids:
        asset = get_asset(registry, aid)
        if asset is None:
            continue
        if skip_pool and asset.get("adapter") == "pool":
            continue
        adapter = get_adapter(asset)
        if adapter is None:
            continue
        out = adapter.query(asset, need_type, problem, source=source, leyou=leyou)
        if out and out.get("ok"):
            out["layer"] = _layer_of(asset)
            if not collect:
                return out
            hits.append(out)
            if len(hits) >= max_hits:
                break
    return hits if collect else None


def knowledge_layer(registry, need_type, problem, source=None, leyou=None,
                    max_hits=MAX_POSSIBILITIES, skip_pool=False):
    """知识域（K2/K3）：信任分级 + 子类提示排序，收集全部命中候选（多可能性）。"""
    assets = [a for a in registry.get("assets", [])
              if a.get("category") in KNOWLEDGE_CATEGORIES and need_type in a.get("covers_need", [])]
    sub_hint = {"term": "term", "caliber": "caliber", "template": "report", "process": "analysis"}
    assets.sort(key=lambda a: (TRUST_ORDER.get(a.get("trust"), 3),
                               0 if a.get("sub_category") == sub_hint.get(need_type) else 1,
                               registry["assets"].index(a)))
    ids = [a["asset_id"] for a in assets]
    return _try_assets(registry, ids, need_type, problem, source, leyou,
                       collect=True, max_hits=max_hits, skip_pool=skip_pool)


def _relevant(out, q):
    """搜索类相关性判定（有 hits）：结果名命中问题关键词——整串、4 字片段或 2+ 字关键词。

    answer 型结果（无 hits，如 BI 取数引导）不在此判定，由 tool_layer 按
    covers_need 诉求匹配接管（防无关诉求被入口引导误接）。
    """
    hits = out.get("hits") or []
    if not hits:
        return False
    qq = q.replace(" ", "")
    words = [w for w in q.replace("  ", " ").split(" ") if len(w) >= 2]
    for h in hits:
        name = str(h.get("name") or "").replace("<em>", "").replace("</em>", "")
        if qq and qq in name:
            return True
        for i in range(max(0, len(qq) - 3)):
            if qq[i:i + 4] in name:
                return True
        for w in words:
            if w and w in name:
                return True
    return False


def tool_layer(registry, need_type, problem, leyou=None):
    """工具域（T1/T2）：注册工具逐个尝试 → 无匹配则本机工具动态发现（引导 AI 自主查）。

    搜索类（leyou）需相关性命中；发现类（local-tools）按问题关键词扫描本机技能目录，
    返回可用工具 + 契约路径引导，AI 自主选择调用（不维护工具注册清单）。
    """
    q = _clean(problem)
    if need_type == "caliber" and "计算" not in q and "方式" not in q:
        q = f"{q} 计算方式"
    assets = [a for a in registry.get("assets", [])
              if a.get("category") in TOOL_CATEGORIES and "tool" in a.get("covers_need", [])]
    for aid in [a["asset_id"] for a in assets]:
        asset = get_asset(registry, aid)
        if asset is None:
            continue
        adapter = get_adapter(asset)
        if adapter is None:
            continue
        out = adapter.query(asset, "tool", q, leyou=leyou)
        if not (out and out.get("ok")):
            continue
        if _relevant(out, q):
            out["planned_query"] = q
            return out
        if not (out.get("hits") or out.get("list") or out.get("items")) \
                and need_type in asset.get("covers_need", []):
            out["planned_query"] = q
            return out
    # 本机工具动态发现（不预注册清单，引导 AI 自主查 ~/.workbuddy/skills/）
    if need_type in ("data", "tool"):
        found = _discover_tools(problem)
        if found:
            found["planned_query"] = q
            return found
    return None


def _discover_tools(problem):
    """扫描本机技能目录，按问题关键词返回可用工具引导（AI 自主调用）。"""
    try:
        from sources.tools_discovery import find_tools
    except ImportError:
        from scripts.sources.tools_discovery import find_tools
    out = find_tools(problem)
    if not (out and out.get("ok")):
        return None
    out["layer"] = "tool"
    return out


def _clean(problem):
    """提取搜索关键词：剥离意图/语气词。"""
    q = (problem or "").strip()
    for s in ("怎么做", "怎么分析", "怎么算", "如何", "怎么", "是什么", "什么", "是", "的", "了", "吗", "呢", "请", "一下", "查", "搜", "找", "看看", "有哪些", "多少", "？", "?"):
        q = q.replace(s, "")
    return q.strip() or (problem or "").strip()


def pool_layer(need_type: str, problem: str) -> list:
    """K2.5 公共知识池：查群体经验（容错——网络/池不可用静默跳过，不阻塞主流程）。

    查询宽松：只按问题关键词全文匹配（池条目分类可能与 need_type 不同，
    如 caliber 条目被 term 诉求命中），分类不作硬过滤。
    按 tier 分两路并行：inject（用户注入 authority 优先）+ session（进化沉淀 reference），
    trust 排序由 _rank 统一处理（authority 排前）。
    需求信号（hit_count）由 Worker 端 GET 命中自动累加，本层不重复上报。
    """
    try:
        from sources.pool_client import query
    except ImportError:
        from scripts.sources.pool_client import query
    q = _clean(problem)  # 剥离意图词后匹配（原问句含"怎么算"等会 LIKE 落空）

    def _query_tier(tier: str) -> list:
        out = query(q=q, limit=3, tier=tier)
        items = (out or {}).get("items") or []
        return [{
            "ok": True, "need_type": need_type, "layer": "K2.5",
            "source": f"pool-{tier}",
            "answer": f"[公共知识池·{it.get('trust')}] {it.get('title')}：{it.get('content')}",
            "trust": it.get("trust") or ("authority" if tier == "inject" else "reference"),
            "confidence": 0.9 if tier == "inject" else 0.8,
            "hit_count": it.get("hit_count"), "adopt_count": it.get("adopt_count"),
            "pool_id": it.get("id"), "tier": tier,
        } for it in items]

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_inject = ex.submit(_query_tier, "inject")
        f_session = ex.submit(_query_tier, "session")
        hits = f_inject.result() + f_session.result()
    return hits


def _rank(possibilities):
    """多可能性排序：trust 等级优先，其次 confidence；返回排序后列表。"""
    return sorted(possibilities,
                  key=lambda p: (TRUST_ORDER.get(p.get("trust"), 3),
                                 -float(p.get("confidence") or 0)))


def _stage1_local(need_type: str, problem: str, work_dir: str | None = None):
    """阶段 1 · 基石：本地 K1（cache 优先），容错静默。

    返回 (hits, cache_hit)：cache_hit 表示本地快路径命中（本地 cache）可安全早停；
    早停门（dissatisfied/expand）在 resolve 层统一判定，保证"命中早停但掌握全面"。
    """
    k1 = k1_layer(need_type, problem, work_dir=work_dir,
                  kind="procedure" if need_type in ("process", "tool") else None)
    hits = k1
    cache_hit = any(h.get("source") == "cache" for h in k1)
    return hits, cache_hit


def _safe(fn):
    """并行路容错：单路异常不影响其他路（返回 None，调用方降级）。"""
    try:
        return fn()
    except Exception:
        return None


def _stage2_parallel(registry, need_type: str, problem: str, source=None, leyou=None):
    """阶段 2 · 并行扇出：公域 GET ‖ K2/K3 知识域 ‖ T1 工具域（线程池，延迟=最慢者）。

    三路互不依赖：公域高质量源并入快路径补读；知识域收集权威口径；工具域注册+动态发现。
    任一失败（网络/超时）不影响其余——单路降级，整体不阻塞。
    pool 先跑（快路径，2 路 tier 查询）：命中则知识域跳过 pool 资产重复查询（省 4 次串行 GET）；
    未命中（池无结果）才由知识域按资产级兜底（宽松查询更易命中，兜底极少触发）。
    """
    pool_hits = _safe(lambda: pool_layer(need_type, problem)) or []
    with ThreadPoolExecutor(max_workers=STAGE2_WORKERS) as ex:
        f_know = ex.submit(_safe, lambda: knowledge_layer(
            registry, need_type, problem, source, leyou, skip_pool=bool(pool_hits)))
        f_tool = ex.submit(_safe, lambda: tool_layer(registry, need_type, problem, leyou))
        khits = f_know.result() or []
        tout = f_tool.result()
    return pool_hits, khits, tout


def _dissatisfied(problem: str, need_type: str, work_dir: str | None) -> bool:
    """隐式不满信号：近期（7 天）同指纹提问 ≥2 次 → 判定用户可能不满。

    确定性规则（非 AI 猜测）：读 BRF 提问运行日志 work-dir/brf/ask-log.jsonl
    （append-only，每次提问必记），统计同指纹（clean_q 后主词）条目数。
    ≥2 次判定不满 → 调用方跳过 cache 早停重新解决（防"反复问 = 反复拿同一个
    不满意答案"）。无 work_dir（离线/单测）不判定，静默返回 False。
    """
    if not work_dir:
        return False
    try:
        log = Path(work_dir) / "brf" / "ask-log.jsonl"
        if not log.exists():
            return False
        fp = (clean_q(problem) or problem)[:24]
        if not fp:
            return False
        now = datetime.now().astimezone()
        hits = 0
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("fingerprint") != fp:
                continue
            try:
                ts = datetime.fromisoformat(rec.get("ts", ""))
            except Exception:
                hits += 1          # 无时间戳的旧记录视为近期
            else:
                if now - ts <= timedelta(days=7):
                    hits += 1
            if hits >= 2:
                return True
    except Exception:
        return False
    return False


def resolve(registry, problem, source=None, leyou=None, allow_network=False,
            need_type=None, work_dir=None, expand=False, prefetch_network=False):
    """卡点 → 三阶段调度（多可能性收集）：

    阶段 1 本地 K1（cache 命中即早停——cache 已吸收各源；--expand 强制全收集）；
    阶段 2 公域 GET ‖ K2/K3 知识域 ‖ T1 工具域并行扇出；
    阶段 3 网络层自助引导（仅空结果；--prefetch-network 弱命中可附带）。
    """
    if need_type is None:
        need_type = infer_need_type(problem)
    path = []
    possibilities = []

    # ── 阶段 1：本地 K1（基石 · cache 优先）──
    k1, cache_hit = _stage1_local(need_type, problem, work_dir)
    path.append({"layer": "K1", "stage": 1, "need_type": need_type,
                 "ok": bool(k1), "count": len(k1),
                 "sources": [p.get("source") for p in k1]})
    possibilities.extend(k1)

    # 早停门：cache 命中（已吸收各源最新解决结果）且未 --expand
    # 隐式不满信号（近期同指纹重复提问）→ 跳过早停重新解决（防固化不满意答案）
    if cache_hit and not expand:
        if _dissatisfied(problem, need_type, work_dir):
            path.append({"layer": "K1", "stage": 1, "need_type": need_type,
                         "note": "dissatisfied：近期同指纹重复提问（隐式不满），跳过 cache 早停重新解决"})
        else:
            ranked = _rank(_dedup(possibilities))
            path.append({"layer": "early_stop", "stage": 1, "reason": "cache_hit",
                         "note": "本地 cache 命中（已吸收各源），早停省时省成本；--expand 可强制全收集"})
            return {"ok": True, "need_type": need_type, "problem": problem,
                    "possibilities": ranked, "best": ranked[0],
                    "path": path, "resolved": True, "early_stop": True}

    # ── 阶段 2：公域 GET ‖ 知识域 ‖ 工具域（并行扇出 · 延迟=最慢者）──
    pool_hits, khits, tout = _stage2_parallel(registry, need_type, problem, source, leyou)
    path.append({"layer": "pool", "stage": 2, "need_type": need_type,
                 "ok": bool(pool_hits), "count": len(pool_hits), "sources": ["pool"]})
    path.append({"layer": "knowledge", "stage": 2, "need_type": need_type,
                 "ok": bool(khits), "count": len(khits),
                 "sources": [o.get("source") for o in khits]})
    path.append({"layer": "tool", "stage": 2, "need_type": need_type,
                 "ok": bool(tout), "source": (tout or {}).get("source"),
                 "planned_query": (tout or {}).get("planned_query")})
    possibilities.extend(pool_hits)
    possibilities.extend(khits)
    if tout:
        possibilities.append(tout)

    # ── 阶段 3：网络层 AI 自助引导（仅空结果兜底；prefetch 弱命中可附带）──
    guidance = ("自助规划（多渠道，非单一联网）：判断缺口类型（知识/技能/数据/方法）→ "
                "选渠道（GitHub / AI 官方 skill 市场 / CSDN / 必应等权威源，领域优先）→ "
                "评估候选（权威/热度/适配）→ 下载安装（approval）→ 验证 → 注册资产或沉淀记忆。"
                "详见 references/network-guidance.md")
    if not possibilities:
        if allow_network:
            path.append({"layer": "network", "stage": 3, "need_type": need_type, "ok": False,
                         "note": "AI 自助联网规划（BRF 不直接联网执行）"})
            return {"ok": False, "reason": "network_required", "need_type": need_type,
                    "problem": problem, "path": path, "possibilities": [],
                    "hint": guidance, "guidance_doc": "references/network-guidance.md"}
        return {"ok": False, "reason": "unresolved", "need_type": need_type,
                "problem": problem, "path": path, "possibilities": [],
                "suggest": ("知识域与工具域均未解决：可申请 AI 自助联网规划（--allow-network，"
                            "多渠道：GitHub/CSDN/官方 skill 站/必应等权威源）或向用户确认")}

    ranked = _rank(_dedup(possibilities))
    out = {
        "ok": True, "need_type": need_type, "problem": problem,
        "possibilities": ranked, "best": ranked[0],
        "path": path, "resolved": True,
    }
    if prefetch_network:
        path.append({"layer": "network", "stage": 3, "need_type": need_type, "ok": False,
                     "note": "后台预取（--prefetch-network）：可 AI 自助联网增强"})
        out["hint"] = guidance
        out["guidance_doc"] = "references/network-guidance.md"
    return out


def _dedup(possibilities):
    """候选去重：按答案指纹（跨源，如 ops-glossary/ops-metrics 同表同口径），保留顺序在前者。"""
    seen = set()
    out = []
    for p in possibilities:
        fp = str(p.get("answer"))[:40]
        if fp in seen:
            continue
        seen.add(fp)
        out.append(p)
    return out

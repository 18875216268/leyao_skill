#!/usr/bin/env python3
"""进化引擎 KnowledgeGovernor：知识治理——蒸馏 → 四维评分 → 验证门禁 → 帕累托筛选 → 处置。

定位（用户确认）：BRF = 自我进化学习框架，本模块是「价值判断引擎」，
机器化「去其糟粕，取其精华」：
  蒸馏      轨迹 → 三类资产（workflow 成功路径 / lesson 失败教训 / skill 可执行步骤）
  评分      四维：质量 × 价值(命中/采纳) × 时效 × 来源
  验证门禁  内容可执行性 / 信任级（不合格不入库，Voyager 自验证启示）
  帕累托    与现有同主题多维比较：全维度被压制→淘汰；某维更优→上位/整合（EvoSkill 启示）
  处置      active / deprecated（+版本，绝不真删知识——与 cache_governor 的"可重建真删"语义分离）

与 cache_governor 的关系（模式共用、实例分开）：
  缓存治理 = 资源视角（可重建 → 真删 evict）
  进化引擎 = 价值视角（不可重建 → 降级 deprecated + 版本存档）
"""
from __future__ import annotations

import json

try:
    from common import clean_q
except ImportError:
    from scripts.common import clean_q

DISTILL_TYPES = ("workflow", "lesson", "skill")
CATEGORY_MAP = {"term": "term", "caliber": "caliber", "process": "method",
                "template": "template", "tool": "experience", "data": "experience"}
TYPE_MAP = {"caliber": "lesson", "process": "workflow", "tool": "skill",
            "term": "lesson", "template": "workflow", "data": "skill"}
SOURCE_WEIGHT = {"authority": 1.0, "reference": 0.7, "candidate": 0.4}

# 五维评分：质量 × 价值(命中/采纳) × 时效 × 来源 × 通用性(可迁移)
W = {"quality": 0.35, "value": 0.25, "freshness": 0.15, "source": 0.15, "general": 0.10}
DIMS = ("quality", "value", "freshness", "source", "general")

# 个人/公共分流（确定性规则，AI 可解释；单一真源——classify_scope 与 generalizability 共用）
PERSONAL_MARKERS = ("我习惯", "我喜欢", "我的偏好", "我通常", "我一般", "我每次", "个人")
EVENT_MARKERS = ("昨天", "上周", "这次", "刚才", "前天", "那天")
GENERIC_TYPES = {"term", "caliber", "method", "template", "process"}  # 定义/口径/方法/模板/流程天然可迁移


def norm_key(problem: str, limit: int = 24) -> str:
    """规范化记忆 key：剥离意图词，取主词。"""
    q = clean_q(problem or "")
    return (q or (problem or "")[:limit])[:limit]


def distill(problem: str, answer: str, source: str, need_type: str | None = None, distilled: str | None = None) -> dict:
    """蒸馏：轨迹 → 结构化条目候选（workflow/lesson/skill 三类资产）。

    L0 快速通道（默认）：content = "问题 → 答案"（轨迹快照，零额外负担）
    L1 深度蒸馏（按需）：AI 提供 distilled（提炼后的精华：去噪/泛化/结构化步骤）
        → content 用提炼版 + refined 标记（质量分升级、结构验证启用）
    """
    nt = need_type or "term"
    content = f"{problem} → {distilled}" if distilled else f"{problem} → {answer}"
    return {
        "category": CATEGORY_MAP.get(nt, "experience"),
        "distill_type": TYPE_MAP.get(nt, "lesson"),
        "title": norm_key(problem),
        "content": content,
        "source": source,
        "need_type": nt,
        "refined": bool(distilled),
    }


def classify_scope(problem: str, answer: str, need_type: str | None = None) -> str:
    """个人/公共分流（确定性规则，非 LLM 猜测）：

    personal —— 个体行为模式（我习惯/我喜欢…）或一次性事件（昨天/上周…）
                 → 只进本地 K1（个人习惯蒸馏），不上传公共池
    shared   —— 术语/口径/方法/模板/流程 或 无个体语境 → 本地 + 公共池（群体经验）
    """
    text = f"{problem or ''} {answer or ''}"
    if any(m in text for m in PERSONAL_MARKERS):
        return "personal"
    if any(m in text for m in EVENT_MARKERS):
        return "personal"
    if need_type in GENERIC_TYPES:
        return "shared"
    return "shared"  # 默认共享：业务知识大部分可复用


def generalizability(candidate: dict, need_type: str | None = None) -> float:
    """通用性/可迁移性分：公共经验必须可脱离原场景复用（Voyager 只沉淀可泛化资产）。"""
    text = candidate.get("content") or ""
    if any(m in text for m in PERSONAL_MARKERS) or any(m in text for m in EVENT_MARKERS):
        return 0.15  # 个体/事件语境 → 不可迁移
    if need_type in GENERIC_TYPES:
        return 0.9   # 定义/口径/方法/模板/流程 → 天然可迁移
    length = len(text)
    if 15 <= length <= 200:
        return 0.7
    return 0.5


def quality_score(candidate: dict) -> float:
    """质量分（启发式）：内容完整度 + 结构度 + 提炼度。

    refined（AI 深度提炼过）→ 质量更可信，加分；无 LLM 调用，零额外负担。
    """
    content = candidate.get("content") or ""
    length = min(len(content), 200) / 200.0
    has_arrow = "→" in content
    base = min(1.0, 0.4 + length * 0.4 + (0.1 if has_arrow else 0))
    return min(1.0, base + (0.15 if candidate.get("refined") else 0))


def score(candidate: dict, trust: str, hit_count: int = 0,
          adopt_count: int = 0, age_days: float = 0) -> dict:
    """五维评分：质量×wq + 价值×wv + 时效×wf + 来源×ws + 通用性×wg。"""
    value = min(1.0, hit_count * 0.2 + adopt_count * 0.3)
    freshness = max(0.0, 1.0 - age_days / 365.0)
    source = SOURCE_WEIGHT.get(trust, 0.5)
    gen = generalizability(candidate, candidate.get("need_type"))
    dims = {"quality": quality_score(candidate), "value": value,
            "freshness": freshness, "source": source, "general": gen}
    total = sum(dims[d] * W[d] for d in DIMS)
    return {**dims, "total": round(total, 3)}


def verify(candidate: dict, trust: str, need_type: str | None = None) -> tuple[bool, str]:
    """验证门禁：内容可用性 + 信任级 +（L1）结构完整性。

    L1 深度蒸馏（refined 时）对 workflow/skill 类做确定性结构检查——Voyager 自验证的
    轻量确定性版（零 LLM，不给 AI 增加负担）：
      workflow（process/template）：须含步骤序列标识（→ / 1. / 步骤），保证可复现；
      skill（tool/data）：须含执行痕迹（命令/脚本/调用词），保证可执行；
    candidate.verified=True 表示 AI 已自验证可执行，跳过结构检查（信任 AI 声明）。
    """
    content = candidate.get("content") or ""
    if len(content) < 8:
        return False, "内容过短，无法验证"
    if trust not in ("authority", "reference"):
        return False, "信任级不足（需 authority/reference）"
    nt = need_type or candidate.get("need_type")
    if candidate.get("refined") and not candidate.get("verified") and nt in ("process", "template", "tool", "data"):
        if nt in ("process", "template"):
            if not (content.count("→") >= 2 or "1." in content or "步骤" in content):
                return False, "结构不完整：workflow 类须含可执行步骤序列（→ 步骤链 / 1. / 步骤）"
        elif not any(k in content for k in ("python", "脚本", "运行", "调用", "命令", "执行")):
            return False, "结构不完整：skill 类须含执行痕迹（命令/脚本）"
    return True, "验证通过"


def pareto(new: dict, existing: list[dict]) -> str:
    """帕累托筛选：与现有同主题条目多维比较。

    accept —— 新条目某维度更优（或无比对对象）
    merge  —— 部分重叠且互有优势（增量并入，version+1）
    reject —— 全维度被现有压制（自动去劣）
    """
    if not existing:
        return "accept"
    new_dims = [new.get(d, 0) for d in DIMS]
    for e in existing:
        e_dims = [e.get(d, 0) for d in DIMS]
        strictly_better = all(n > o for n, o in zip(new_dims, e_dims))
        strictly_worse = all(n <= o for n, o in zip(new_dims, e_dims))
        if strictly_worse:
            return "reject"
        if strictly_better:
            return "accept"
    # 互有胜负（部分重叠）→ 整合
    return "merge"


def disposition(decision: str, version: int = 1) -> dict:
    """处置：active / deprecated（+版本）。知识永不真删——降级 + 版本存档。"""
    return {"decision": decision, "status": "active" if decision in ("accept", "merge") else "deprecated",
            "version": version + 1 if decision == "merge" else version}


def evolve(problem: str, answer: str, source: str, need_type: str | None = None,
           trust: str = "reference", hit_count: int = 0, adopt_count: int = 0,
           age_days: float = 0, existing: list[dict] | None = None,
           scope: str | None = None, distilled: str | None = None,
           verified: bool = False) -> dict:
    """进化管线入口：分流 → 蒸馏 → 评分 → 验证 → 帕累托 → 处置。

    scope: personal/shared/None（None=auto 按内容特征推断，见 classify_scope）
    distilled: L1 深度蒸馏——AI 提炼后的精华（去噪/泛化/结构化步骤），None 走 L0 快速通道
    verified:   AI 声明已自验证可执行（跳过结构完整性检查）
    """
    cand = distill(problem, answer, source, need_type, distilled)
    cand["verified"] = verified
    ok, msg = verify(cand, trust, need_type)
    if not ok:
        return {"ok": False, "reason": "verify_failed", "detail": msg, "candidate": cand}
    scope_eff = scope if scope in ("personal", "shared") else classify_scope(problem, answer, need_type)
    sc = score(cand, trust, hit_count, adopt_count, age_days)
    decision = pareto(sc, existing or [])
    disp = disposition(decision)
    return {"ok": True, "candidate": cand, "score": sc, "decision": decision,
            "status": disp["status"], "version": disp["version"],
            "scope": scope_eff, "general": sc["general"], "refined": cand["refined"]}


if __name__ == "__main__":
    demo = evolve("成本优势率怎么算", "低于合理P4*0.99购进的订单金额/总订单金额",
                  "ops-metrics", "caliber", "authority")
    print(json.dumps(demo, ensure_ascii=False, indent=2))

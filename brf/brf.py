#!/usr/bin/env python3
"""BRF 插件统一入口：leyao_seed_pro 与 BRF 子系统的唯一衔接点。

设计原则（插件式）：
- 主 skill 只认识本入口与固定 JSON 协议（protocol 1.0），不感知 BRF 内部实现；
- BRF 内部（registry/adapters/sources/resolve）完全自治，可独立修改而不影响主 skill；
- 衔接收敛：主 skill 只在「卡点调度」「计算门口径校验」两处调用本入口。

用法（由主 skill 调度，须在 brf/ 目录运行或传绝对路径）：
  python brf.py status
  python brf.py ask --problem "成本优势率怎么算" [--work-dir <主skill work-dir>]
  python brf.py resolve --problem "..." [--need-type caliber] [--allow-network] [--work-dir]

协议（输出固定字段）：
  ok / plugin / protocol / problem / need_type / possibilities[] / best /
  path[] / resolved / work_dir
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "scripts"))

from registry import load_registry          # noqa: E402
from infer import infer_need_type            # noqa: E402
from resolve import resolve as _resolve      # noqa: E402
from common import find_dr_scripts, clean_q  # noqa: E402

PROTOCOL = "1.0"
REGISTRY = HERE / "registry.json"


def _load():
    return load_registry(str(REGISTRY))


def _dr_scripts(here: Path | None = None) -> Path | None:
    """向上遍历定位主 skill scripts（统一 common.find_dr_scripts）。"""
    return find_dr_scripts(here or HERE)


def _wrap(out: dict, problem: str, need_type: str, work_dir: str | None) -> dict:
    """统一协议包装：多可能性字段透传（resolve 已收集），兼容单结果兜底。

    失败语义透传：reason / hint / suggest / guidance_doc（未解决时引导 AI 自助规划）。
    """
    wrapped = {
        "ok": bool(out.get("ok")),
        "plugin": "brf",
        "protocol": PROTOCOL,
        "problem": problem,
        "need_type": need_type,
        "possibilities": out.get("possibilities") or ([out] if out.get("ok") else []),
        "best": out.get("best") or (out if out.get("ok") else None),
        "path": out.get("path") or [],
        "resolved": bool(out.get("ok")),
        "work_dir": work_dir,
    }
    for key in ("reason", "hint", "suggest", "guidance_doc", "early_stop"):
        if out.get(key):
            wrapped[key] = out[key]
    return wrapped


def status() -> dict:
    reg = _load()
    return {
        "ok": True,
        "plugin": "brf",
        "protocol": PROTOCOL,
        "registry": reg.get("registry_version"),
        "assets": len(reg.get("assets", [])),
        "categories": [c["id"] for c in reg.get("categories", [])],
    }


def register_capability(work_dir: str) -> dict:
    """把 BRF 能力注册到主 skill work-dir（复用 capabilities.py 契约，供第 5 步 select）。

    能力契约字段对齐 capabilities.py：id/purpose/capabilities/inputs/outputs/scores/
    side_effects/network_required/read_only/verification/fallback。
    """
    import subprocess
    import tempfile

    scripts = _dr_scripts()
    if scripts is None:
        return {"ok": False, "error": "MAIN_SKILL_SCRIPTS_NOT_FOUND",
                "detail": "向上遍历未找到含 capabilities.py 的主 skill scripts"}
    cap = {
        "id": "brf-knowledge",
        "purpose": "卡点解决：知识域（K1 记忆/缓存、K2 运营库在线、K3 云智库）+ 工具域多可能性方案",
        "capabilities": ["term", "caliber", "process", "template", "tool", "data"],
        "inputs": ["problem", "need_type"],
        "outputs": ["possibilities", "best", "path"],
        "scores": {"accuracy": 0.9, "speed": 0.8, "format_fidelity": 0.9, "auditability": 0.95},
        "side_effects": ["network", "login"],
        "network_required": True,
        "read_only": True,
        "verification": ["python brf/brf.py status"],
        "fallback": "用户确认或人工查证",
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(cap, f, ensure_ascii=False)
        tmp = f.name
    try:
        r = subprocess.run([sys.executable, str(scripts / "capabilities.py"), "register",
                            "--work-dir", work_dir, "--file", tmp],
                           capture_output=True, text=True, timeout=30)
        payload = json.loads((r.stdout or "").strip() or "null") if r.returncode == 0 else None
        return {"ok": r.returncode == 0, "capability": "brf-knowledge",
                "registered": bool(payload), "detail": (r.stderr or "").strip()[:200]}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return {"ok": False, "error": "REGISTER_FAIL", "detail": str(e)}
    finally:
        Path(tmp).unlink(missing_ok=True)


def _record_ask(problem: str, work_dir: str | None) -> None:
    """提问运行日志（不满检测数据基础）：append-only 写 work-dir/brf/ask-log.jsonl。

    每行 {ts, fingerprint, problem}——每次提问必记（同问题可重复，供 resolve 的
    cache 早停做「隐式不满判定」：近期同指纹 ≥2 次 → 跳过早停重新解决）。
    用插件自有运行日志而非 supervisor record：record 按内容哈希去重（同问题只留
    1 条），无法计数重复提问；ask-log 与 cache 同级属 BRF 运行数据，不触碰 episodic。
    容错：无 work-dir 或写入失败均静默跳过，不阻塞主流程。
    """
    if not work_dir:
        return
    try:
        wd = Path(work_dir)
        log_dir = wd / "brf"
        log_dir.mkdir(parents=True, exist_ok=True)
        fp = (clean_q(problem) or (problem or ""))[:24]
        with (log_dir / "ask-log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().astimezone().isoformat(),
                                "fingerprint": fp, "problem": (problem or "")[:120]},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass


def ask(problem: str, work_dir: str | None = None, source: str | None = None,
        leyou: str | None = None) -> dict:
    """卡点解决：自动推断意图 → resolve 多可能性（三阶段调度）。"""
    _record_ask(problem, work_dir)
    reg = _load()
    need_type = infer_need_type(problem)
    out = _resolve(reg, problem, source=source, leyou=leyou,
                   need_type=need_type, work_dir=work_dir)
    return _wrap(out, problem, need_type, work_dir)


def resolve(problem: str, need_type: str | None = None, allow_network: bool = False,
            work_dir: str | None = None, source: str | None = None,
            leyou: str | None = None, expand: bool = False,
            prefetch_network: bool = False) -> dict:
    _record_ask(problem, work_dir)
    reg = _load()
    nt = need_type or infer_need_type(problem)
    out = _resolve(reg, problem, source=source, leyou=leyou,
                   allow_network=allow_network, need_type=nt, work_dir=work_dir,
                   expand=expand, prefetch_network=prefetch_network)
    return _wrap(out, problem, nt, work_dir)


def learn(problem: str, answer: str, need_type: str | None = None, source: str = "ask",
          trust: str = "reference", risk: str = "low", scope: str | None = None,
          work_dir: str | None = None, distilled: str | None = None,
          verified: bool = False, pool_id: str | None = None) -> dict:
    """进化沉淀自动触发（进化引擎 KnowledgeGovernor）：

    解决成功后调用：
      1. supervisor record  —— 卡点解决事件（轨迹证据）
      2. cache store        —— 结果缓存（内容寻址）
      3. evolve 管线        —— 分流 → 蒸馏 → 五维评分 → 验证门禁 → 帕累托筛选
         ├ 通过 + L1/L2（risk≠high）→ 自动沉淀（decide who=auto）→ memory.put
         └ L3（risk=high）→ propose 待用户审批（安全不变量保留）
      分层蒸馏：distilled=None 走 L0 快速通道（零额外负担）；distilled 提供走
      L1 深度蒸馏（AI 提炼精华 + workflow/skill 结构完整性验证），verified 声明已自验证。
    借鉴闭环（pool_id 非空 = 答案来自公共池）：record_adopt 上报价值信号 → 拿回
    hit/adopt 喂 evolve value 维度（奖励激活）→ 本地沉淀带 pool_id 来源 → 不回传上传
    （防"借鉴→再上传"循环）。
    复用主 skill 机制（proposal 审批机制保留，审批主体自动化），BRF 零自研记忆/缓存。
    """
    scripts = _dr_scripts()
    wd = work_dir or os.environ.get("DAILY_REPORT_WORK_DIR")
    if scripts is None:
        return {"ok": False, "error": "MAIN_SKILL_SCRIPTS_NOT_FOUND"}
    if not wd:
        return {"ok": False, "error": "WORK_DIR_REQUIRED",
                "hint": "需 --work-dir 或 DAILY_REPORT_WORK_DIR（K1/进化复用主 skill 记忆）"}
    nt = need_type or infer_need_type(problem)
    profile = "knowledge-hub"

    def run(*args, with_wd=True):
        cmd = [sys.executable, str(scripts / args[0]), *args[1:]]
        if with_wd:
            cmd += ["--work-dir", wd]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return json.loads((r.stdout or "").strip() or "null")
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return None

    # 0) 借鉴反馈：pool_id 非空 → 上报采纳（价值信号）并拿回 hit/adopt 供 evolve value 维度
    adopt_feedback = None
    if pool_id:
        try:
            from sources.pool_client import record_adopt
        except ImportError:
            from scripts.sources.pool_client import record_adopt
        adopt_feedback = record_adopt(pool_id)

    # 1) 事件（evidence 来源）
    ev = run("supervisor.py", "record", "--profile", profile, "--type", nt,
             "--note", f"BRF 卡点解决: {problem[:80]} → {source}", "--run-id", "", "--task-id", "")
    eid = (ev or {}).get("event_id")
    # 2) 结果缓存（内容寻址；cache.py key 无 --work-dir；inputs 为文件引用列表，查询语义入 parameters）
    params = json.dumps({"problem": problem, "need_type": nt}, ensure_ascii=False)
    cache_key = (run("cache.py", "key", "--operation", "ask", "--producer", "knowledge-hub",
                     "--inputs", "[]", "--parameters", params, with_wd=False) or {}).get("cache_key")
    cached = None
    if cache_key:
        cached = run("cache.py", "store", "--namespace", "knowledge-hub", "--key", cache_key,
                     "--producer", "knowledge-hub", "--inputs", "[]",
                     "--parameters", params,
                     "--payload", json.dumps({"answer": answer, "trust": trust, "source": source,
                                               "pool_id": pool_id}, ensure_ascii=False))
    # 3) 进化引擎：分流 → 蒸馏 → 评分 → 验证 → 帕累托
    try:
        from scripts.evolve import evolve as _evolve, norm_key as _norm_key
    except ImportError:
        from evolve import evolve as _evolve, norm_key as _norm_key
    # 3.1) 读取 semantic 已有同主题条目 → 帕累托比对对象（此前 existing 恒空，帕累托从未生效；
    #      需五维 dims 的旧条目（score 只存 total）自动跳过，不参与比对）
    existing = []
    try:
        sem = run("memory.py", "get", "--scope", "semantic", "--scope-id", profile)
        if sem and sem.get("entries"):
            _k = _norm_key(problem)
            for e in sem["entries"]:
                v = e.get("value") or {}
                sc = v.get("score")
                if e.get("key") == _k and isinstance(sc, dict) and all(
                        d in sc for d in ("quality", "value", "freshness", "source", "general")):
                    existing.append({d: sc[d] for d in ("quality", "value", "freshness", "source", "general")})
    except Exception:
        existing = []
    evo = _evolve(problem, answer, source, nt, trust, scope=scope,
                  hit_count=int((adopt_feedback or {}).get("hit_count") or 0),
                  adopt_count=int((adopt_feedback or {}).get("adopt_count") or 0),
                  distilled=distilled, verified=verified, existing=existing)
    # 4) 语义沉淀：L1/L2 自动（who=auto），L3 提案待用户
    prop = None
    settled = None
    pool_upload = None
    if eid and evo.get("ok"):
        key = evo["candidate"]["title"]
        if risk != "high":
            p = run("supervisor.py", "propose", "--profile", profile,
                    "--target", f"semantic:{profile}", "--change", key,
                    "--risk", "low", "--evidence", eid)
            pid = (p or {}).get("proposal_id")
            if pid:
                # 幂等：同问题重复 learn → record 内容哈希稳定 → 同 eid → 同 proposal；
                # 已 approved 则跳过重复审批（避免 "proposal not pending" 噪音），直接复用沉淀
                ap = None
                if (p or {}).get("status") == "proposed":
                    ap = run("supervisor.py", "approve", pid, "--who", "auto")
                m = run("memory.py", "put", "--scope", "semantic", "--scope-id", profile,
                        "--key", key, "--value", json.dumps({"answer": answer, "source": source,
                                                              "score": {k: evo["score"][k] for k in
                                                                        ("total", "quality", "value", "freshness", "source", "general")},
                                                              "decision": evo["decision"],
                                                              "scope": evo["scope"],
                                                              "pool_id": pool_id}, ensure_ascii=False),
                        "--source", source, "--evidence", eid, "--proposal-id", pid,
                        "--kind", "procedure" if nt in ("process", "tool", "template") else "fact")
                settled = {"proposal": pid, "approved_by": "auto" if ap else "reused",
                           "memory": bool(m and m.get("entries")),
                           "auto_count": (ap or {}).get("auto_count"),
                           "suggest_review": (ap or {}).get("suggest_review")}
                # 5) 同步上传公共知识池：仅 shared 且非池来源（personal 只进本地；
                #    池来源的知识已存在公共池，回传会造成重复/循环）
                if evo.get("scope") == "shared" and not pool_id:
                    try:
                        from sources.pool_client import submit as _pool_submit
                    except ImportError:
                        from scripts.sources.pool_client import submit as _pool_submit
                    pu = _pool_submit(key, answer, category=evo["candidate"]["category"],
                                      distill_type=evo["candidate"]["distill_type"],
                                      trust=trust, quality_score=evo["score"]["quality"],
                                      kind="procedure" if nt in ("process", "tool", "template") else "fact")
                    pool_upload = {"ok": bool(pu and pu.get("ok")),
                                   "action": (pu or {}).get("action") or _pool_skip_reason(pu),
                                   "id": (pu or {}).get("id"), "detail": (pu or {}).get("error")}
                elif pool_id:
                    pool_upload = {"ok": True, "action": "skipped:borrowed",
                                   "id": pool_id, "detail": "池来源知识（借鉴沉淀），不回传上传"}
                else:
                    pool_upload = {"ok": True, "action": "skipped:personal",
                                   "id": None, "detail": "个人语境（习惯/事件），仅本地沉淀"}
        else:
            prop = run("supervisor.py", "propose", "--profile", profile,
                       "--target", f"semantic:{profile}", "--change", key,
                       "--risk", "high", "--evidence", eid)
    # 6) 蒸馏决策日志（审计：帕累托过程可追溯；BRF 自有运行日志，与 ask-log 同级，不触碰记忆区）
    try:
        log_dir = Path(wd) / "brf"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "distill-log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(), "problem": problem,
                "title": evo.get("candidate", {}).get("title") if evo.get("ok") else _norm_key(problem),
                "distill_type": evo.get("distill_type"), "decision": evo.get("decision"),
                "status": evo.get("status"), "scope": evo.get("scope"),
                "score": evo.get("score"), "existing_count": len(existing),
                "refined": evo.get("refined")}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return {"ok": bool(eid), "learned": True,
            "event_id": eid, "cache_key": cache_key, "cache_status": (cached or {}).get("status"),
            "evolve": {k: evo.get(k) for k in ("distill_type", "decision", "status", "score", "scope", "general")},
            "settled": settled, "pool_upload": pool_upload,
            "pool_feedback": adopt_feedback,
            "proposal_id": (prop or {}).get("proposal_id"),
            "proposal_status": (prop or {}).get("status"),
            "hint": "L1/L2 已自动沉淀（auto 审批）；L3 提案待用户决定"}


def _pool_skip_reason(pu: dict | None) -> str | None:
    """池层拦截语义翻译：DOMINATED/REVIEW/QUALIFICATION 等 → skipped:xxx（AI 可读，非失败）。"""
    err = (pu or {}).get("error")
    if not err or pu.get("ok"):
        return None
    return f"skipped:{err}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="BRF 插件统一入口（主 skill 唯一衔接点）")
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("status", help="插件状态（注册表/资产/分类）")
    a = s.add_parser("ask", help="卡点解决（自动推断意图）")
    a.add_argument("--problem", required=True, help="卡点问题描述（用户原话/不确定名词）")
    a.add_argument("--work-dir", default=None, help="主 skill work-dir（K1 记忆/缓存接入）")
    a.add_argument("--source", default=None, help="覆盖知识类数据源（默认为公共池 pool 端点）")
    a.add_argument("--leyou", default=None, help="leyou_cloud.py 路径")
    r = s.add_parser("resolve", help="显式指定诉求类型的分层解决")
    r.add_argument("--problem", required=True)
    r.add_argument("--need-type", default=None,
                   choices=["term", "caliber", "tool", "data", "template", "process"])
    r.add_argument("--allow-network", action="store_true", help="允许网络层建议（approval）")
    r.add_argument("--expand", action="store_true",
                   help="强制全收集（跳过 cache 早停，阶段 1/2 全层收集多可能性）")
    r.add_argument("--prefetch-network", action="store_true",
                   help="弱命中时后台预取网络引导（附带 hint，不阻塞主返回）")
    r.add_argument("--work-dir", default=None)
    r.add_argument("--source", default=None)
    r.add_argument("--leyou", default=None)
    rc = s.add_parser("register-capability", help="把 BRF 能力注册到外部 work-dir（供主执行链第 5 步 select）")
    rc.add_argument("--work-dir", required=True, help="主 skill 外部 work-dir")
    lr = s.add_parser("learn", help="进化沉淀自动触发：事件+缓存+提案（用户审批后 memory.put）")
    lr.add_argument("--problem", required=True)
    lr.add_argument("--answer", required=True)
    lr.add_argument("--need-type", default=None, choices=["term", "caliber", "tool", "data", "template", "process"])
    lr.add_argument("--source", default="ask")
    lr.add_argument("--trust", default="reference", choices=["authority", "reference", "candidate"])
    lr.add_argument("--risk", default="low", choices=["low", "medium", "high"])
    lr.add_argument("--scope", default=None, choices=["personal", "shared", "auto"],
                    help="沉淀分流：personal（仅本地，个人习惯）/ shared（本地+公共池）/ auto（默认按内容特征推断）")
    lr.add_argument("--distilled", default=None,
                    help="L1 深度蒸馏：AI 提炼后的精华（去噪/泛化/结构化步骤）。workflow/skill 等高复用资产建议提供；term/caliber 快查省略走 L0 快速通道")
    lr.add_argument("--verified", action="store_true",
                    help="AI 声明已自验证可执行（跳过结构完整性检查）")
    lr.add_argument("--pool-id", default=None,
                    help="答案来自公共池条目的 id（借鉴）：record_adopt 上报采纳 + value 维度激活 + 沉淀带来源，不回传上传")
    lr.add_argument("--work-dir", default=None)
    args = p.parse_args(argv)

    if args.cmd == "status":
        out = status()
    elif args.cmd == "ask":
        out = ask(args.problem, args.work_dir, args.source, args.leyou)
    elif args.cmd == "resolve":
        out = resolve(args.problem, args.need_type, args.allow_network,
                      args.work_dir, args.source, args.leyou,
                      expand=args.expand, prefetch_network=args.prefetch_network)
    elif args.cmd == "register-capability":
        out = register_capability(args.work_dir)
    else:
        out = learn(args.problem, args.answer, args.need_type, args.source,
                    args.trust, args.risk, args.scope, args.work_dir,
                    distilled=args.distilled, verified=args.verified,
                    pool_id=args.pool_id)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())

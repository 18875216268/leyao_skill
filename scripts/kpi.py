#!/usr/bin/env python3
"""KPI 评估循环：量化「越用越准」+ 发现待优化卡点。

数据源全部来自既有运行数据（零新埋点）：
  - work-dir/brf/ask-log.jsonl   提问记录（ts/fingerprint/problem，append-only）
  - 主 skill semantic 记忆        learn 沉淀量（经 memory.py get）
  - 云端公共池                    hit/adopt 趋势（可选，--with-cloud 才查，容错静默）

输出：KPI 报告（JSON + 可读文本）+ 待优化清单（重复提问 Top = 隐式不满信号）。
周期性触发（空闲时，与 consolidate 同模式）：`python scripts/kpi.py --work-dir <dir> [--with-cloud]`
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def _read_ask_log(work_dir: str) -> list[dict]:
    """读提问日志（容错：文件不存在/坏行跳过）。"""
    log = Path(work_dir) / "brf" / "ask-log.jsonl"
    if not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            if rec.get("problem"):
                out.append(rec)
        except Exception:
            continue
    return out


def _semantic_count(work_dir: str) -> dict:
    """learn 沉淀量：读主 skill semantic 记忆（经 memory.py get，容错）。"""
    import subprocess
    try:
        r = subprocess.run(
            [sys.executable, "scripts/memory.py", "get", "--work-dir", work_dir,
             "--scope", "semantic", "--scope-id", "knowledge-hub"],
            capture_output=True, text=True, timeout=30)
        data = json.loads((r.stdout or "").strip() or "{}")
        entries = data.get("entries") or []
        kinds = Counter()
        for e in entries:
            v = e.get("value") or {}
            kinds[v.get("kind", "fact")] += 1
        return {"total": len(entries), "kinds": dict(kinds)}
    except Exception:
        return {"total": 0, "kinds": {}}


def _cloud_trend() -> dict:
    """云端池 hit/adopt 总量（可选，容错静默）。"""
    try:
        sys.path.insert(0, "brf")
        from scripts.sources.pool_client import query as pool_query
        out = pool_query(limit=1)
        if out and out.get("items"):
            return {"reachable": True, "hint": "池可达（hit/adopt 逐条在条目上，总量需 D1 查询）"}
        return {"reachable": True, "hint": "池可达"}
    except Exception:
        return {"reachable": False, "hint": "网络不可达，跳过云端指标"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="KPI 评估循环（量化越用越准 + 待优化清单）")
    p.add_argument("--work-dir", required=True, help="主 skill work-dir")
    p.add_argument("--days", type=int, default=30, help="统计窗口天数（默认 30）")
    p.add_argument("--with-cloud", action="store_true", help="附带云端池可达性检查（网络）")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    args = p.parse_args(argv)

    logs = _read_ask_log(args.work_dir)
    now = datetime.now().astimezone()
    window_start = now - timedelta(days=args.days)

    # 按天统计活跃度
    daily = Counter()
    recent = []
    for rec in logs:
        try:
            ts = datetime.fromisoformat(rec.get("ts", ""))
        except Exception:
            continue
        if ts >= window_start:
            daily[ts.date().isoformat()] += 1
            recent.append(rec)

    # 重复提问（同指纹 ≥2 次 = 隐式不满信号 → 待优化卡点）
    fp_counts = Counter(r.get("fingerprint", "") for r in recent if r.get("fingerprint"))
    repeated = {fp: n for fp, n in fp_counts.items() if n >= 2}
    top_repeated = sorted(repeated.items(), key=lambda x: -x[1])[:10]
    problems_by_fp = {}
    for r in recent:
        fp = r.get("fingerprint", "")
        if fp in repeated and fp not in problems_by_fp:
            problems_by_fp[fp] = r.get("problem", "")

    sem = _semantic_count(args.work_dir)
    cloud = _cloud_trend() if args.with_cloud else {}

    report = {
        "window_days": args.days,
        "asks_total_window": len(recent),
        "asks_daily": dict(sorted(daily.items())),
        "repeated_questions": len(repeated),          # 隐式不满信号数
        "repeated_rate": round(len(repeated) / max(len(recent), 1) * 100, 1),
        "top_repeated": [{"fingerprint": fp, "count": n,
                          "problem": problems_by_fp.get(fp, "")[:60]}
                         for fp, n in top_repeated],
        "semantic_settled": sem,                      # learn 沉淀量（越用越准的证据）
        "cloud": cloud,
        "generated_at": now.isoformat(),
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    # 可读报告
    print(f"=== KPI 评估（窗口 {args.days} 天）===")
    print(f"提问量: {len(recent)}（日均 {len(recent)/max(args.days,1):.1f}）")
    print(f"沉淀量: semantic {sem.get('total', 0)} 条（{sem.get('kinds', {})}）")
    print(f"重复提问（隐式不满）: {len(repeated)} 个指纹（率 {report['repeated_rate']}%）")
    if top_repeated:
        print("\n=== 待优化卡点（重复提问 Top，建议优先补口径/方法）===")
        for fp, n in top_repeated:
            print(f"  [{n}次] {problems_by_fp.get(fp, fp)[:50]}")
    if not logs:
        print("（无提问记录——首次使用，KPI 从积累后开始有意义）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

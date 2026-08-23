#!/usr/bin/env python3
"""ACS 统一查询入口 ask()：卡点 → 分层解决路径（知识层→工具层→网络层）。

范式：资产 = 卡点解决方案库；路由 = 分层降级（认知类先看运营知识库，
不足则用云智库工具辅助获取，仍无则申请联网）。need_type 自动推断（可覆盖）。
"""
from __future__ import annotations
import argparse, json, sys

try:
    from .registry import load_registry
    from .resolve import resolve
except ImportError:
    from registry import load_registry
    from resolve import resolve

DEFAULT_REGISTRY = "registry.json"
NEED_TYPES = ["term", "caliber", "tool", "data", "template", "process"]


def ask(registry, need_type, question, source=None, leyou=None):
    """兼容入口：分层解决路径（need_type 作为层内策略提示，可 None 自动推断）。"""
    if need_type is not None and need_type not in NEED_TYPES:
        return {"ok": False, "reason": "unknown_need_type", "need_type": need_type}
    return resolve(registry, question, source=source, leyou=leyou, need_type=need_type)


def main(argv=None):
    p = argparse.ArgumentParser(description="ACS 卡点解决 ask()（分层路径：知识→工具→网络）")
    p.add_argument("--registry", default=DEFAULT_REGISTRY)
    p.add_argument("--need-type", choices=NEED_TYPES, default=None,
                   help="层内策略提示；缺省自动推断意图")
    p.add_argument("--question", required=True)
    p.add_argument("--source", default=None, help="覆盖知识类数据源（默认为公共池 pool 端点）")
    p.add_argument("--leyou", default=None, help="leyou_cloud.py 路径")
    p.add_argument("--allow-network", action="store_true", help="允许申请联网兜底（需 approval）")
    args = p.parse_args(argv)
    try:
        reg = load_registry(args.registry)
        out = ask(reg, args.need_type, args.question, source=args.source, leyou=args.leyou)
        if not out.get("ok") and out.get("reason") == "unresolved" and args.allow_network:
            out = resolve(reg, args.question, source=args.source, leyou=args.leyou,
                          allow_network=True, need_type=args.need_type)
        out["need_type_inferred"] = args.need_type is None
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("ok") else (5 if out.get("reason") in ("network_error", "network_required") else 3)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""ACS 资产注册表：读取 / 校验 / 查询 / 注册。"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

CATEGORIES = {"knowledge", "tool", "method", "data", "template"}
NEED_TYPES = {"term", "caliber", "tool", "data", "template", "process"}
TRUSTS = {"authority", "reference", "candidate"}
REQUIRED = ["asset_id", "category", "name", "trust", "read_only", "covers_need"]
ADAPTER_REQUIRED = {
    "cli": ["source", "mode"],        # 桥接执行：脚本 + 模式
    "template": ["source"],           # 模板：模板目录
}


def load_registry(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_asset(registry, asset_id):
    for a in registry.get("assets", []):
        if a.get("asset_id") == asset_id:
            return a
    return None


def list_assets(registry):
    return registry.get("assets", [])


def validate_entry(entry):
    missing = [k for k in REQUIRED if k not in entry]
    extra = ADAPTER_REQUIRED.get(entry.get("adapter") or "") or []
    missing += [k for k in extra if k not in entry]
    if missing:
        return False, f"missing fields: {missing}"
    if entry["category"] not in CATEGORIES:
        return False, f"unknown category: {entry['category']}"
    if entry.get("trust") not in TRUSTS:
        return False, f"unknown trust: {entry.get('trust')}"
    bad_need = [n for n in entry.get("covers_need", []) if n not in NEED_TYPES]
    if bad_need:
        return False, f"unknown covers_need: {bad_need}"
    return True, "ok"


def validate_registry(registry):
    errors = []
    seen = set()
    for i, a in enumerate(registry.get("assets", [])):
        aid = a.get("asset_id")
        if aid in seen:
            errors.append(f"assets[{i}] duplicate asset_id: {aid}")
        seen.add(aid)
        ok, msg = validate_entry(a)
        if not ok:
            errors.append(f"assets[{i}] {aid}: {msg}")
    return (len(errors) == 0), errors


def register_asset(registry_path, entry):
    reg = load_registry(registry_path)
    if get_asset(reg, entry.get("asset_id")):
        raise ValueError(f"duplicate asset_id: {entry['asset_id']}")
    reg.setdefault("assets", []).append(entry)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    return entry


def main(argv=None):
    p = argparse.ArgumentParser(description="ACS 资产注册表工具")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("list"); a.add_argument("--registry", required=True)
    a = sub.add_parser("get"); a.add_argument("--registry", required=True); a.add_argument("--asset-id", required=True)
    a = sub.add_parser("validate"); a.add_argument("--registry", required=True)
    a = sub.add_parser("register"); a.add_argument("--registry", required=True); a.add_argument("--file", required=True)
    args = p.parse_args(argv)
    try:
        if args.cmd == "list":
            for a in list_assets(load_registry(args.registry)):
                print(f"{a['asset_id']:<16} {a['category']:<10} trust={a['trust']:<10} covers={','.join(a['covers_need'])}")
        elif args.cmd == "get":
            a = get_asset(load_registry(args.registry), args.asset_id)
            print(json.dumps(a, ensure_ascii=False, indent=2) if a else f"error: not found {args.asset_id}")
        elif args.cmd == "validate":
            ok, errors = validate_registry(load_registry(args.registry))
            print("PASSED" if ok else "FAILED")
            for e in errors:
                print(" -", e)
            return 0 if ok else 2
        elif args.cmd == "register":
            entry = json.loads(Path(args.file).read_text(encoding="utf-8"))
            ok, msg = validate_entry(entry)
            if not ok:
                raise ValueError(msg)
            e = register_asset(args.registry, entry)
            print("registered:", e["asset_id"])
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

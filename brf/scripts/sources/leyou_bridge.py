#!/usr/bin/env python3
"""乐药云智库桥接（ACS 能力域客户端）：凭证自动登录 + 命令透传。

职责（零侵入 leyou_cloud.py / leyou_firebase_login.py，全部 subprocess 委托）：
1. 凭证自动登录：ensure_login() 复用 leyou_firebase_login 的多凭证策略
   （本地优先 → 数据库凭证依次尝试 → 失效删库 → 全失效才要求扫码）；
2. 命令透传：search / summary / detail / categories / children / collect 等只读操作；
3. ask() 协议：need_type=tool → search 透传，返回统一结构化响应
   {ok, need_type, answer, source, category, trust, confidence, version}。

CLI（输出严格 JSON，退出码 0 成功 / 3 需登录 / 4 依赖缺失 / 2 参数错误）：
  python leyou_bridge.py status [--scan]
  python leyou_bridge.py search <关键词> [--scan]
  python leyou_bridge.py summary <slug>
  python leyou_bridge.py detail <slug>
  python leyou_bridge.py categories
  python leyou_bridge.py children <slug> [--recursive]
  python leyou_bridge.py ask <问题> [--scan]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # brf/scripts/sources
LEYOU_DIR = HERE / "leyou"                      # 云智库原生集成（随插件走，单一来源）


def _find_script(name: str, override=None) -> Path | None:
    """定位脚本：调用方指定 → 插件内 sources/leyou/（原生集成）→ CWD。

    云智库已原生集成进 BRF，不再依赖外部「乐药云智库_Skill封装/」目录。
    """
    for cand in ([Path(override)] if override else []) + [LEYOU_DIR / name, Path(name)]:
        try:
            if cand and cand.exists():
                return cand
        except OSError:
            continue
    return None


def _run_py(script, *args):
    """运行 python 脚本并解析 JSON：先整体解析（兼容 pretty-print），失败再逐行找最后一个 JSON 行（兼容流式）。"""
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


def ensure_login(scan: bool = False) -> dict:
    """凭证自动登录：本地优先 → 数据库兜底 → 失效删库 → 全失效（scan=False 时）返回 LOGIN_REQUIRED。"""
    login = _find_script("leyou_firebase_login.py")
    if login is None:
        return {"ok": False, "error": "DEPENDENCY_MISSING",
                "detail": "leyou_firebase_login.py 未找到（应位于 scripts/sources/leyou/）"}
    args = ["auto"] if scan else ["auto", "--no-scan"]
    return _run_py(login, *args)


def run_cmd(*args, scan: bool = False, leyou=None) -> dict:
    """凭证就绪后透传 leyou_cloud.py 命令（search/summary/detail/...）。"""
    cloud = _find_script("leyou_cloud.py", leyou)
    if cloud is None:
        return {"ok": False, "error": "DEPENDENCY_MISSING",
                "detail": "leyou_cloud.py 未找到（应位于 scripts/sources/leyou/）"}
    lg = ensure_login(scan=scan)
    if not lg.get("ok"):
        return lg
    return _run_py(cloud, *args, "--compact")


def _strip_em(name):
    """去掉搜索结果的 <em> 高亮标签。"""
    return (name or "").replace("<em>", "").replace("</em>", "")


def query(asset, need_type, question, leyou=None, scan: bool = False) -> dict:
    """ask() 协议：need_type=tool → search 透传，返回统一响应。"""
    if need_type != "tool":
        return {"ok": False, "reason": "unsupported_need_type", "need_type": need_type}
    if not question:
        return {"ok": False, "reason": "empty_question"}
    out = run_cmd("search", question, scan=scan, leyou=leyou)
    if not out.get("ok"):
        return out
    hits = (out.get("list") or [])[:5]
    answer = "；".join(f"{_strip_em(h.get('name'))}（{h.get('slug')}）" for h in hits) or "无结果"
    return {
        "ok": True,
        "need_type": need_type,
        "answer": answer,
        "source": asset.get("asset_id", "leyou-search"),
        "category": asset.get("category", "tool"),
        "trust": asset.get("trust", "reference"),
        "confidence": 0.8,
        "version": "manual",
        "total": out.get("total"),
        "hits": [{"name": _strip_em(h.get("name")), "slug": h.get("slug"), "type": h.get("type")} for h in hits],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="乐药云智库桥接（凭证自动登录 + 命令透传）")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status", help="凭证自动登录并输出登录态")
    s.add_argument("--scan", action="store_true", help="全失效时直接调起扫码登录")
    q = sub.add_parser("search", help="关键字搜索")
    q.add_argument("keyword"); q.add_argument("--scan", action="store_true")
    q.add_argument("--page", type=int, default=1); q.add_argument("--pagesize", type=int, default=10)
    m = sub.add_parser("summary", help="文档摘要"); m.add_argument("slug")
    d = sub.add_parser("detail", help="文档全文"); d.add_argument("slug")
    sub.add_parser("categories", help="栏目列表")
    c = sub.add_parser("children", help="目录子项"); c.add_argument("slug"); c.add_argument("--recursive", action="store_true")
    a = sub.add_parser("ask", help="ACS ask 协议：搜索并返回统一响应")
    a.add_argument("question"); a.add_argument("--scan", action="store_true")
    cl = sub.add_parser("collect", help="全库采集")
    cl.add_argument("keyword"); cl.add_argument("--workers", type=int, default=10)
    cl.add_argument("--out", default="")
    args = p.parse_args(argv)

    asset = {"asset_id": "leyou-search", "category": "tool", "trust": "reference"}
    try:
        if args.cmd == "status":
            out = ensure_login(scan=args.scan)
        elif args.cmd == "search":
            out = run_cmd("search", args.keyword, "--page", str(args.page), "--pagesize", str(args.pagesize), scan=args.scan)
        elif args.cmd == "summary":
            out = run_cmd("summary", args.slug)
        elif args.cmd == "detail":
            out = run_cmd("detail", args.slug)
        elif args.cmd == "categories":
            out = run_cmd("categories")
        elif args.cmd == "children":
            extra = ["--recursive"] if args.recursive else []
            out = run_cmd("children", args.slug, *extra)
        elif args.cmd == "collect":
            out = run_cmd("collect", args.keyword, "--workers", str(args.workers), "--out", args.out)
        elif args.cmd == "ask":
            out = query(asset, "tool", args.question, scan=args.scan)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        if out.get("ok"):
            return 0
        err = out.get("error") or out.get("reason")
        return 3 if err in ("LOGIN_REQUIRED", "TOKEN_EXPIRED") else (4 if err == "DEPENDENCY_MISSING" else 2)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "EXEC_FAIL", "detail": str(e)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

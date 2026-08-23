#!/usr/bin/env python3
"""self_update：skill 自主更新模块（GitHub Releases 更新源）。

check —— 对比远端最新 tag 与本地 SKILL.md version，输出是否有新版本；
        网络失败静默（超时短，不阻塞主任务）。
apply —— 下载新版本 zip → 校验版本递增 → 备份 → 原子替换（保护清单外）→ 失败回滚；
        绝不覆盖本地记忆/配置/凭证/归档（PROTECT 清单），更新后下次会话生效。

用法：
  python scripts/self_update.py check              # 自检（每次使用开头，轻量）
  python scripts/self_update.py apply              # 应用更新（校验后自动替换）
  python scripts/self_update.py check --json       # JSON 输出（供 AI 解析）
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # skill 根目录
CONF = ROOT / "self_update.json"

# 保护清单：这些路径绝不覆盖（本地记忆/云端登录态/凭证/归档/缓存/版本控制）
PROTECT = (
    ".workbuddy", ".wrangler", ".pytest_cache", "__pycache__", ".git",
    "data.json.archive", "leyou_token.json", "wrangler-account.json",
    "pool_knowledge_dump.json", "self_update.json",
)
# 覆盖时保留的本地文件后缀（源码可替换；运行期产物不碰）
KEEP_SUFFIX = (".pyc", ".pyo")

UA = "skill-self-update"


def _read_conf() -> dict:
    if not CONF.exists():
        return {"repo": ""}
    try:
        return json.loads(CONF.read_text(encoding="utf-8"))
    except Exception:
        return {"repo": ""}


def _local_version() -> str:
    try:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r'version:\s*"([\d.]+)"', text)
        return m.group(1) if m else "0.0.0"
    except Exception:
        return "0.0.0"


def _ver_tuple(s: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", s)[:3]) or (0, 0, 0)


def _newer(a: str, b: str) -> bool:
    return _ver_tuple(a) > _ver_tuple(b)


def _fetch(url: str, timeout: int = 8) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _branch(conf: dict) -> str:
    return conf.get("branch") or "main"


def _remote_meta(conf: dict, timeout: int = 8) -> tuple[str, str]:
    """返回 (version, 下载 url)：branch 模式经 api.github.com contents 读 main 分支 SKILL.md 的
    version（纯 API 读版本，避免 CDN 域名差异）；release 模式读 releases/latest 的 tag。
    纯 API 部署即可用（codeload 拉分支 zip 已验证可达）。"""
    mode = conf.get("mode") or "branch"
    if mode == "release":
        api = f"https://api.github.com/repos/{conf['repo']}/releases/latest"
        data = json.loads(_fetch(api, timeout=timeout).decode("utf-8"))
        tag = str(data.get("tag_name") or "").lstrip("v")
        if not tag:
            raise ValueError(f"release tag 为空: {data.get('message')}")
        return tag, f"https://codeload.github.com/{conf['repo']}/zip/refs/tags/v{tag}"
    br = _branch(conf)
    api = f"https://api.github.com/repos/{conf['repo']}/contents/SKILL.md?ref={br}"
    data = json.loads(_fetch(api, timeout=timeout).decode("utf-8"))
    text = base64.b64decode(data.get("content") or "").decode("utf-8")
    m = re.search(r'version:\s*"([\d.]+)"', text)
    if not m:
        raise ValueError("远端 SKILL.md 无 version 字段")
    return m.group(1), f"https://codeload.github.com/{conf['repo']}/zip/refs/heads/{br}"


def check(conf: dict, timeout: int = 8) -> dict:
    local = _local_version()
    if not conf.get("repo"):
        return {"ok": True, "configured": False, "local": local, "latest": local,
                "update_available": False, "note": "未配置更新源(self_update.json repo)"}
    try:
        tag, _ = _remote_meta(conf, timeout=timeout)
    except Exception as e:
        return {"ok": False, "error": "NETWORK", "detail": str(e)[:100],
                "local": local, "latest": None, "update_available": False,
                "note": "网络不可用，跳过（不阻塞主任务）"}
    up = _newer(tag, local)
    return {"ok": True, "configured": True, "local": local, "latest": tag,
            "update_available": up,
            "note": "有新版" if up else "已是最新"}


def _iter_zip_entries(zf: zipfile.ZipFile):
    """解出 zip 内相对 skill 根的 (相对路径, 文件内容 bytes)；跳过顶层目录前缀。"""
    names = zf.namelist()
    prefix = None
    for n in names:
        if n.endswith("SKILL.md"):
            prefix = n[: n.index("SKILL.md")]
            break
    if prefix is None:
        raise ValueError("zip 内未找到 SKILL.md（非本 skill 包）")
    for n in names:
        if n.endswith("/"):
            continue
        rel = n[len(prefix):] if n.startswith(prefix) else n
        if not rel or rel.startswith(("/", "\\")):
            continue
        yield rel, zf.read(n)


def _protected(rel: str) -> bool:
    parts = rel.split("/")
    head = parts[0]
    if any(p and head == p for p in PROTECT):
        return True
    if any(head.startswith(p) for p in PROTECT):
        return True
    if rel.endswith(KEEP_SUFFIX):
        return True
    return False


def apply(conf: dict, timeout: int = 30) -> dict:
    local = _local_version()
    if not conf.get("repo"):
        return {"ok": False, "error": "NOT_CONFIGURED",
                "note": "未配置更新源(self_update.json repo)"}
    try:
        tag, zip_url = _remote_meta(conf, timeout=timeout)
    except Exception as e:
        return {"ok": False, "error": "NETWORK", "detail": str(e)[:100]}
    if not _newer(tag, local):
        return {"ok": False, "error": "NOT_NEWER", "local": local, "latest": tag,
                "note": "远端不高于本地，跳过（防降级/防重复覆盖）"}
    # 下载更新包 zip（branch 模式=codeload heads/<branch>；release 模式=tags/v<tag>）
    try:
        zdata = _fetch(zip_url, timeout=timeout)
    except Exception as e:
        return {"ok": False, "error": "DOWNLOAD", "detail": str(e)[:100]}
    tmp = Path(tempfile.mkdtemp(prefix="self_update_"))
    zp = tmp / "update.zip"
    zp.write_bytes(zdata)
    try:
        with zipfile.ZipFile(zp) as zf:
            # 校验远端版本递增（读包内 SKILL.md）
            entries = list(_iter_zip_entries(zf))
            remote_ver = "0.0.0"
            for rel, data in entries:
                if rel == "SKILL.md":
                    m = re.search(r'version:\s*"([\d.]+)"', data.decode("utf-8"))
                    remote_ver = m.group(1) if m else "0.0.0"
            if not _newer(remote_ver, local):
                return {"ok": False, "error": "NOT_NEWER", "local": local,
                        "remote": remote_ver, "note": "包内版本不高于本地，拒绝覆盖"}
            # 备份将被覆盖的文件 → 回滚依据
            backup = tmp / "backup"
            overwritten = []
            for rel, data in entries:
                if _protected(rel):
                    continue
                dst = ROOT / rel
                if dst.exists():
                    bf = backup / rel
                    bf.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dst, bf)
                    overwritten.append(rel)
            # 原子替换（先写临时再 os.replace）
            applied = []
            try:
                for rel, data in entries:
                    if _protected(rel):
                        continue
                    dst = ROOT / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    tmpf = dst.parent / (dst.name + ".su_tmp")
                    tmpf.write_bytes(data)
                    os.replace(tmpf, dst)
                    applied.append(rel)
            except Exception as e:
                # 回滚：恢复备份
                for rel in reversed(applied):
                    bf = backup / rel
                    if bf.exists():
                        shutil.copy2(bf, ROOT / rel)
                return {"ok": False, "error": "APPLY", "detail": str(e)[:100],
                        "note": "替换失败已回滚", "applied": len(applied)}
            return {"ok": True, "action": "updated", "from": local, "to": remote_ver,
                    "files": len(applied), "skipped_protected": sum(
                        1 for rel, _ in entries if _protected(rel)),
                    "note": "更新完成，下次会话生效（本地记忆/配置/凭证未触碰）"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def auto(conf: dict, timeout: int = 30) -> dict:
    """auto 一站式：check → 有新版自动 apply → 返回汇总；无新版/网络不可用直接返回。
    无需多余参数，运行即完成"检查+更新+报告"，更新后即可继续主任务（下次会话生效）。"""
    chk = check(conf, timeout=min(timeout, 8))
    if not chk.get("configured"):
        return chk
    if chk.get("error") == "NETWORK":
        return chk  # 网络不可用：静默跳过，不阻塞
    if not chk.get("update_available"):
        return chk  # 已最新
    ap = apply(conf, timeout=timeout)
    ap["checked"] = {"local": chk.get("local"), "latest": chk.get("latest")}
    return ap


def main() -> int:
    ap = argparse.ArgumentParser(description="skill 自主更新模块")
    ap.add_argument("action", choices=["auto", "check", "apply"],
                    help="auto 一键检查+自动更新（推荐，无参数直接跑）/ check 自检 / apply 应用更新")
    ap.add_argument("--json", action="store_true", help="JSON 输出（供 AI 解析）")
    ap.add_argument("--timeout", type=int, default=None, help="网络超时秒数")
    args = ap.parse_args()
    conf = _read_conf()
    t = args.timeout
    if args.action == "check":
        out = check(conf, timeout=t) if t else check(conf)
    elif args.action == "apply":
        out = apply(conf, timeout=t) if t else apply(conf)
    else:
        out = auto(conf, timeout=t) if t else auto(conf)
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        if args.action == "auto":
            if out.get("action") == "updated":
                print(f"✅ 已自动更新 {out.get('from')} → {out.get('to')}（{out.get('files')} 文件），下次会话生效")
            elif out.get("ok") and not out.get("update_available") and out.get("configured") is not False:
                print(f"✅ 已是最新（{out.get('local')}）")
            elif not out.get("configured"):
                print("⚠️ 未配置更新源（self_update.json repo）")
            else:
                print(f"⏭ 跳过：{out.get('note')}")
        else:
            print(out.get("note", ""))
            if out.get("ok") and out.get("update_available"):
                print(f"  本地 {out.get('local')} → 远端 {out.get('latest')}；执行 apply 更新")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""SQLite FTS5 派生检索索引（零依赖 · JSON 单一事实源不变）。

索引是 memory（semantic/core）与 cache 条目的派生物，可随时 build 全量重建；
JSON 文件仍是权威存储（审计/血缘/审批以 JSON 为准），索引只加速检索。

FTS5 用 trigram tokenizer：中文按 3 字符子串匹配（业务词如「缺货率」精确命中）；
查询 <3 字符时降级 LIKE 子串（如「毛利」）。search 前自动检测源文件陈旧性并重建。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from runtime_core import runtime_path, work_dir

INDEX_DIR = "runtime/index"
DB_NAME = "memory-index.db"
FTS_NAME = "idx_fts"
ENTRY_TABLE = "idx_entry"

# 轻量语义增强：业务同义词（措辞不同但同义 → 扩展召回）。
# 零依赖零成本（本地词库）；企业可按需扩充；--no-expand 可关闭。
DEFAULT_SYNONYMS: dict[str, list[str]] = {
    "缺货率": ["缺货比例", "商品缺货"],
    "成本优势率": ["成本优势", "进货优势"],
    "周转率": ["周转天数", "库存周转"],
    "毛利": ["毛利率", "毛利额"],
    "促销": ["活动", "营销活动"],
    "复盘": ["回顾", "总结"],
}


def _load_synonyms(extra: str | None) -> dict[str, list[str]]:
    """加载同义词词库：默认内嵌 + 外部 JSON 扩展（{词: [同义词]}），合并去重。"""
    syn = {k: list(v) for k, v in DEFAULT_SYNONYMS.items()}
    if extra:
        try:
            ext = json.loads(Path(extra).read_text(encoding="utf-8"))
            for k, v in (ext or {}).items():
                syn.setdefault(k, [])
                syn[k] = list(dict.fromkeys(syn[k] + list(v)))
        except Exception:
            pass  # 词库加载失败静默（不影响主检索）
    return syn


def _expand_query(q: str, syn: dict[str, list[str]]) -> str:
    """同义词扩展：查询词命中词库 → 合并同义表达为 OR 短语（召回措辞不同但同义的结果）。"""
    words = {q}
    for w, syns in syn.items():
        if w in q or q in w:
            words.add(w)
            words.update(syns)
        for s in syns:
            if s in q:
                words.add(s)
                words.add(w)
    return " OR ".join(f'"{w.replace(chr(34), chr(34) * 2)}"' for w in words if w)


def db_path(root: Path) -> Path:
    return runtime_path(root, INDEX_DIR, DB_NAME, create_parent=True)


def _source_files(root: Path) -> list[tuple[Path, str]]:
    """索引源：semantic/core 记忆文件 + cache 条目（均为 JSON 派生物）。"""
    files = []
    for scope in ("semantic", "core"):
        files.append((runtime_path(root, "memory", scope, create_parent=False), scope))
    files.append((runtime_path(root, "runtime", "cache", "entries", create_parent=False), "cache"))
    return files


def _max_mtime(root: Path) -> int:
    """源文件最大修改时间（纳秒，供陈旧检测）。"""
    m = 0
    for base, _scope in _source_files(root):
        if base.exists():
            for p in base.glob("*.json"):
                try:
                    m = max(m, p.stat().st_mtime_ns)
                except OSError:
                    pass
    return m


def _connect(root: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path(root)))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {ENTRY_TABLE} ("
        "id INTEGER PRIMARY KEY, entry_key TEXT NOT NULL, scope TEXT NOT NULL, "
        "kind TEXT NOT NULL, content TEXT NOT NULL, updated_at TEXT, importance REAL)"
    )
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_NAME} USING fts5("
        "content, content='" + ENTRY_TABLE + "', content_rowid='id', tokenize='trigram')"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS idx_meta (k TEXT PRIMARY KEY, v TEXT)"
    )


def _extract_importance(val) -> float:
    """蒸馏分（importance 精排依据）：value.score.total 或默认 0.6。"""
    if isinstance(val, dict):
        sc = val.get("score")
        if isinstance(sc, dict) and isinstance(sc.get("total"), (int, float)):
            return float(sc["total"])
        return 0.6
    return 0.6


def _entries_from_json(root: Path) -> list[tuple[str, str, str, str, str, float]]:
    """从 JSON 提取索引条目：entry_key / scope / kind / content / updated_at / importance。"""
    out = []
    for base, scope in _source_files(root):
        if not base.exists():
            continue
        for p in sorted(base.glob("*.json")):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            entries = doc.get("entries") if isinstance(doc, dict) else []
            if scope == "cache":
                # cache 文件本身就是 entry 对象
                if isinstance(doc, dict) and doc.get("object_type") == "cache_entry":
                    entries = [doc]
                else:
                    continue
            for e in entries:
                if not isinstance(e, dict):
                    continue
                key = str(e.get("key") or e.get("cache_key") or p.stem)
                val = e.get("value")
                if val is None and "payload" in e:
                    val = e.get("payload")
                if isinstance(val, dict):
                    content = json.dumps(val, ensure_ascii=False)
                elif val is not None:
                    content = str(val)
                else:
                    continue
                kind = str(e.get("kind") or "fact")
                ts = str(e.get("created_at") or e.get("updated_at") or "")
                out.append((key, scope, kind, key + " " + content, ts, _extract_importance(val)))
    return out


def build(root: Path) -> dict:
    """全量重建索引（原子：新表构建成功后替换）。"""
    rows = _entries_from_json(root)
    tmp_conn = sqlite3.connect(str(db_path(root)))
    try:
        tmp_conn.execute("PRAGMA journal_mode=WAL")
        _init(tmp_conn)
        tmp_conn.execute(f"DELETE FROM {ENTRY_TABLE}")
        tmp_conn.execute(f"DELETE FROM {FTS_NAME}")
        tmp_conn.executemany(
            f"INSERT INTO {ENTRY_TABLE} (entry_key, scope, kind, content, updated_at, importance) VALUES (?,?,?,?,?,?)",
            rows,
        )
        tmp_conn.execute(
            f"INSERT INTO {FTS_NAME} (rowid, content) "
            f"SELECT id, content FROM {ENTRY_TABLE}"
        )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tmp_conn.execute(
            "INSERT OR REPLACE INTO idx_meta (k, v) VALUES ('built_at', ?), ('source_max_mtime', ?)",
            (now, str(_max_mtime(root))),
        )
        tmp_conn.commit()
    finally:
        tmp_conn.close()
    return {"ok": True, "entries": len(rows), "built_at": now}


def _is_stale(root: Path, conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute("SELECT v FROM idx_meta WHERE k='source_max_mtime'").fetchone()
        if row is None:
            return True
        return int(row[0]) < _max_mtime(root)
    except (sqlite3.Error, TypeError, ValueError):
        return True


def search(root: Path, query: str, kind: str | None = None, limit: int = 5,
           expand: bool = True, synonyms: str | None = None) -> dict:
    """BM25 检索（trigram 中文子串；短查询降级 LIKE）+ 同义词扩展召回。返回 top-K 片段。"""
    conn = _connect(root)
    try:
        _init(conn)
        if _is_stale(root, conn):
            conn.close()
            build(root)
            conn = _connect(root)
            _init(conn)
        q = (query or "").strip()
        if not q:
            return {"ok": False, "reason": "empty_query", "hits": []}
        params: list = []
        where = ""
        if kind:
            where += " AND kind=?"
            params.append(kind)
        if len(q) >= 3:
            # trigram：查询串本身含引号时需转义；子串匹配用双引号短语
            # 同义词扩展：命中词库 → OR 多词召回（措辞不同但同义）
            phrase = q.replace('"', '""')
            match_expr = f'"{phrase}"'
            if expand:
                syn = _load_synonyms(synonyms)
                expanded = _expand_query(q, syn)
                if expanded and expanded != match_expr:
                    match_expr = expanded
            sql = (
                f"SELECT e.id, e.entry_key, e.scope, e.kind, e.content, e.updated_at, e.importance, -bm25({FTS_NAME}) AS rank "
                f"FROM {ENTRY_TABLE} e JOIN {FTS_NAME} f ON f.rowid = e.id "
                f"WHERE {FTS_NAME} MATCH ?{where} ORDER BY rank DESC LIMIT ?"
            )
            params = [match_expr] + params + [int(limit)]
        else:
            like = f"%{q}%"
            sql = (
                f"SELECT id, entry_key, scope, kind, content, updated_at, importance, 0 AS rank "
                f"FROM {ENTRY_TABLE} WHERE content LIKE ?{where} ORDER BY updated_at DESC LIMIT ?"
            )
            params = [like] + params + [int(limit)]
        rows = conn.execute(sql, params).fetchall()
        hits = []
        for rid, key, scope, k, content, ts, importance, rank in rows:
            snippet = content[:200] if len(content) > 200 else content
            hits.append({
                "key": key, "scope": scope, "kind": k,
                "snippet": snippet, "content_len": len(content),
                "updated_at": ts, "importance": round(importance, 3),
                "bm25_rank": round(rank, 3),
            })
        return {"ok": True, "hits": hits, "query": q, "indexed": True}
    finally:
        conn.close()


def status(root: Path) -> dict:
    conn = _connect(root)
    try:
        _init(conn)
        total = conn.execute(f"SELECT COUNT(*) FROM {ENTRY_TABLE}").fetchone()[0]
        by_scope = dict(conn.execute(
            f"SELECT scope, COUNT(*) FROM {ENTRY_TABLE} GROUP BY scope").fetchall())
        built = conn.execute("SELECT v FROM idx_meta WHERE k='built_at'").fetchone()
        stale = _is_stale(root, conn)
        return {"ok": True, "entries": total, "by_scope": by_scope,
                "built_at": built[0] if built else None, "stale": stale}
    finally:
        conn.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="SQLite FTS5 派生检索索引")
    s = p.add_subparsers(dest="cmd", required=True)
    a = s.add_parser("build"); a.add_argument("--work-dir")
    a = s.add_parser("search"); a.add_argument("--work-dir")
    a.add_argument("--query", required=True); a.add_argument("--kind")
    a.add_argument("--limit", type=int, default=5)
    a.add_argument("--no-expand", action="store_true", help="关闭同义词扩展（默认开启）")
    a.add_argument("--synonyms", default=None, help="外部同义词词库 JSON 路径（扩展默认词库）")
    a = s.add_parser("status"); a.add_argument("--work-dir")
    args = p.parse_args(argv)
    try:
        root = work_dir(args.work_dir, create=True)
        if args.cmd == "build":
            out = build(root)
        elif args.cmd == "search":
            out = search(root, args.query, args.kind, args.limit,
                         expand=not args.no_expand, synonyms=args.synonyms)
        else:
            out = status(root)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

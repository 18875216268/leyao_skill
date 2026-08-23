#!/usr/bin/env python3
"""Shared safe primitives for leyao_seed_pro runtime tools."""
from __future__ import annotations
import hashlib, json, os, re, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_id(value: str, label: str = "id", profile: bool = False) -> str:
    value = str(value).strip()
    if not (PROFILE_RE if profile else ID_RE).fullmatch(value):
        allowed = "letters, digits, dot, underscore, hyphen" if profile else "lowercase letters, digits, hyphens"
        raise ValueError(f"invalid {label}; use {allowed}")
    return value


def work_dir(value: str | None, create: bool = False) -> Path:
    raw = value or os.environ.get("DAILY_REPORT_WORK_DIR")
    if not raw:
        raise ValueError("--work-dir or DAILY_REPORT_WORK_DIR is required")
    path = Path(raw).expanduser().resolve(strict=False)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.is_dir():
        raise ValueError(f"work-dir is not a directory: {path}")
    return path


def contained(root: Path, path: Path, must_exist: bool = False) -> Path:
    root = root.resolve(strict=must_exist)
    target = path.resolve(strict=must_exist)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes work-dir: {path}") from exc
    return target


def runtime_path(root: Path, *parts: str, create_parent: bool = False) -> Path:
    target = contained(root, root.joinpath(*parts), must_exist=False)
    if create_parent:
        target.parent.mkdir(parents=True, exist_ok=True)
    return target


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def content_hash(data: Any) -> str:
    value = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(value).hexdigest()


def semantic_hash(data: Any, volatile_fields: set[str] | None = None) -> str:
    volatile = {"created_at", "updated_at", "generated_at", "run_id", "id"}
    if volatile_fields:
        volatile |= volatile_fields
    def stable(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: stable(item) for key, item in value.items() if key not in volatile}
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value
    return content_hash(stable(data))


def file_ref(root: Path, path: Path | str, role: str | None = None) -> dict[str, Any]:
    target = contained(root, Path(path), must_exist=True)
    if not target.is_file():
        raise ValueError(f"file required: {target}")
    result = {"path": target.relative_to(root.resolve()).as_posix(), "checksum": checksum(target), "size": target.stat().st_size}
    if role:
        result["role"] = role
    return result


def snapshot_hash(refs: list[dict[str, Any]]) -> str:
    normalized = [{key: item[key] for key in sorted(item) if key in {"path", "checksum", "role", "size"}} for item in refs]
    return content_hash(sorted(normalized, key=lambda item: (item.get("checksum", ""), item.get("path", ""))))


def cache_key(operation: str, producer: str, inputs: list[dict[str, Any]], parameters: dict[str, Any], context_hash: str | None = None, policy_version: str = "1") -> str:
    return content_hash({"cache_protocol": 1, "operation": operation, "producer": producer, "inputs": sorted(inputs, key=lambda item: (item.get("checksum", ""), item.get("path", ""))), "parameters": parameters, "context_hash": context_hash, "policy_version": policy_version})


def object_meta(object_type: str, identifier: str, version: int = 1, **extra: Any) -> dict[str, Any]:
    return {"object_type": object_type, "schema_version": SCHEMA_VERSION, "id": identifier, "version": version, "created_at": utc_now(), "updated_at": utc_now(), **extra}


def atomic_write_json(path: Path, value: Any, overwrite: bool = True) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name): os.unlink(temp_name)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def append_event(root: Path, category: str, event: dict[str, Any]) -> Path:
    safe_id(category, "event category")
    directory = contained(root, root / "audit_log", must_exist=False)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"events-{datetime.now(timezone.utc).strftime('%Y-%m')}.jsonl"
    record = {"timestamp": utc_now(), "category": category, **event}
    # One buffered append is sufficient for the local single-dispatch model; event records remain immutable.
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush(); os.fsync(handle.fileno())
    return path


def list_json(directory: Path, pattern: str = "*.json") -> list[tuple[Path, dict[str, Any]]]:
    if not directory.is_dir(): return []
    result = []
    for path in sorted(directory.glob(pattern)):
        result.append((path, read_json(path)))
    return result

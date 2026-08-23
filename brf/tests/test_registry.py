"""注册表单测：schema 字段、分类枚举、重复注册、整体校验。"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.registry import (
    CATEGORIES, NEED_TYPES, TRUSTS,
    get_asset, load_registry, register_asset, validate_entry, validate_registry,
)

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "registry.json"


class TestRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = load_registry(REGISTRY)

    def test_load_and_asset_count(self):
        self.assertGreaterEqual(len(self.reg["assets"]), 6)

    def test_categories_enum(self):
        for c in self.reg["categories"]:
            self.assertIn(c["id"], CATEGORIES)

    def test_all_assets_valid(self):
        ok, errors = validate_registry(self.reg)
        self.assertTrue(ok, msg="; ".join(errors))

    def test_covers_need_subset(self):
        for a in self.reg["assets"]:
            for n in a["covers_need"]:
                self.assertIn(n, NEED_TYPES)

    def test_trust_subset(self):
        for a in self.reg["assets"]:
            self.assertIn(a["trust"], TRUSTS)

    def test_authority_for_caliber(self):
        m = get_asset(self.reg, "ops-metrics")
        self.assertIsNotNone(m)
        self.assertEqual(m["trust"], "authority")

    def test_get_asset_missing(self):
        self.assertIsNone(get_asset(self.reg, "not-exist"))

    def test_validate_entry_missing_field(self):
        ok, msg = validate_entry({"asset_id": "x"})
        self.assertFalse(ok)
        self.assertIn("missing", msg)

    def test_register_duplicate_raises(self):
        reg = {"assets": []}
        entry = {
            "asset_id": "dup-asset", "category": "knowledge", "name": "d",
            "source": "s", "mode": "api", "trust": "reference", "read_only": True,
            "covers_need": ["term"],
        }
        tmp = ROOT / "tests" / "_tmp_registry.json"
        tmp.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        try:
            register_asset(tmp, entry)
            with self.assertRaises(ValueError):
                register_asset(tmp, entry)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass  # 沙箱回收站不可用时忽略清理


if __name__ == "__main__":
    unittest.main()

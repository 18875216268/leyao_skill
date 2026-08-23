"""适配器架构单测：按资产声明分派到闭环适配器（pool/cli/template）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.adapters import get_adapter


class TestAdapterDispatch(unittest.TestCase):
    """按资产声明分派到正确适配器。"""

    def test_cli_dispatch(self):
        self.assertEqual(get_adapter({"adapter": "cli"}).id, "cli")
        self.assertEqual(get_adapter({"mode": "cli"}).id, "cli")

    def test_template_dispatch(self):
        self.assertEqual(get_adapter({"adapter": "template"}).id, "template")
        self.assertEqual(get_adapter({"category": "template"}).id, "template")

    def test_pool_dispatch(self):
        self.assertEqual(get_adapter({"adapter": "pool"}).id, "pool")
        self.assertEqual(get_adapter({"mode": "pool"}).id, "pool")

    def test_unknown_returns_none(self):
        self.assertIsNone(get_adapter({"adapter": "nonexistent"}))
        self.assertIsNone(get_adapter({"adapter": "api"}))   # 已移除的适配器不再分派


if __name__ == "__main__":
    unittest.main()

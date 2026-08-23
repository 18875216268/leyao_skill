"""self_update 单测：check 版本对比 / apply 保护清单与回滚（离线确定性）。

注意：用 importlib 直接加载 self_update.py（不 import scripts 包）——
避免把项目根 scripts 缓存进 sys.modules，污染 brf/tests 的 scripts.adapters 解析。
"""
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

_MOD_PATH = Path(__file__).resolve().parent.parent / "scripts" / "self_update.py"
_spec = importlib.util.spec_from_file_location("self_update_mod", str(_MOD_PATH))
su = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(su)

_ver_tuple = su._ver_tuple
_newer = su._newer
_protected = su._protected
_iter_zip_entries = su._iter_zip_entries
apply = su.apply
check = su.check


def _fake_conf(tmp: Path, repo="owner/repo"):
    (tmp / "self_update.json").write_text(
        json.dumps({"repo": repo}, ensure_ascii=False), encoding="utf-8")
    return json.loads((tmp / "self_update.json").read_text(encoding="utf-8"))


class TestVersion(unittest.TestCase):
    def test_ver_tuple(self):
        self.assertEqual(_ver_tuple("12.2.1"), (12, 2, 1))
        self.assertEqual(_ver_tuple("v12.3.0"), (12, 3, 0))

    def test_newer(self):
        self.assertTrue(_newer("12.3.0", "12.2.1"))
        self.assertFalse(_newer("12.2.1", "12.3.0"))
        self.assertFalse(_newer("12.2.1", "12.2.1"))


class TestProtect(unittest.TestCase):
    def test_protect_list(self):
        for p in (".workbuddy/memory/2026-08-23.md", ".wrangler/cache/a.json",
                  "leyou_token.json", "data.json.archive", "x.pyc"):
            self.assertTrue(_protected(p), p)

    def test_replaceable(self):
        for p in ("SKILL.md", "references/chain-overview.md",
                  "scripts/self_update.py", "brf/brf.py"):
            self.assertFalse(_protected(p), p)


class TestZipEntries(unittest.TestCase):
    def test_prefix_stripped(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("repo-v12.3.0/SKILL.md", 'version: "12.3.0"')
            zf.writestr("repo-v12.3.0/references/a.md", "x")
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            entries = dict(_iter_zip_entries(zf))
        self.assertIn("SKILL.md", entries)
        self.assertIn("references/a.md", entries)
        self.assertEqual(len(entries), 2)


class TestApply(unittest.TestCase):
    def _make_update_zip(self, version="12.3.0", extra_files=None):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"repo-v{version}/SKILL.md",
                        f'version: "{version}"\n# update {version}')
            zf.writestr(f"repo-v{version}/references/new.md", "# new doc")
            for rel, content in (extra_files or {}).items():
                zf.writestr(f"repo-v{version}/{rel}", content)
        return buf.getvalue()

    def test_apply_updates_and_preserves_protected(self, tmp=None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "skill"
            root.mkdir()
            (root / "SKILL.md").write_text('version: "12.2.1"\n', encoding="utf-8")
            (root / ".workbuddy").mkdir()
            (root / ".workbuddy" / "MEMORY.md").write_text("secret", encoding="utf-8")
            conf = {"repo": "owner/repo"}
            zdata = self._make_update_zip()
            with mock.patch.object(su, "ROOT", root), \
                 mock.patch.object(su, "_remote_meta", return_value=("12.3.0", "https://codeload.test/x.zip")), \
                 mock.patch.object(su, "_fetch", return_value=zdata):
                out = apply(conf, timeout=3)
            self.assertTrue(out["ok"], out)
            self.assertEqual(out["to"], "12.3.0")
            # 新文件已写、旧文件已更新
            self.assertIn("update 12.3.0", (root / "SKILL.md").read_text(encoding="utf-8"))
            self.assertTrue((root / "references" / "new.md").exists())
            # 保护清单保留
            self.assertEqual((root / ".workbuddy" / "MEMORY.md").read_text(encoding="utf-8"), "secret")

    def test_apply_rejects_downgrade(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "skill"
            root.mkdir()
            (root / "SKILL.md").write_text('version: "12.5.0"\n', encoding="utf-8")
            conf = {"repo": "owner/repo"}
            zdata = self._make_update_zip("12.3.0")
            with mock.patch.object(su, "ROOT", root), \
                 mock.patch.object(su, "_remote_meta", return_value=("12.3.0", "https://codeload.test/x.zip")), \
                 mock.patch.object(su, "_fetch", return_value=zdata):
                out = apply(conf, timeout=3)
            self.assertFalse(out["ok"])
            self.assertEqual(out["error"], "NOT_NEWER")
            self.assertEqual((root / "SKILL.md").read_text(encoding="utf-8"),
                             'version: "12.5.0"\n')  # 原文件未动

    def test_check_unconfigured(self):
        with tempfile.TemporaryDirectory() as td:
            conf = {"repo": ""}
            with mock.patch.object(su, "ROOT", Path(td)):
                out = check(conf, timeout=3)
            self.assertTrue(out["ok"])
            self.assertFalse(out["configured"])

    def test_check_network_failure_silent(self):
        with mock.patch.object(su, "_remote_meta", side_effect=Exception("no net")):
            out = check({"repo": "owner/repo"}, timeout=3)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "NETWORK")
        self.assertFalse(out["update_available"])


if __name__ == "__main__":
    unittest.main()

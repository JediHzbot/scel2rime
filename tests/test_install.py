"""PowerShell integration tests, always in disposable directories; no real DLL calls.

The native worker is replaced ONLY inside a temporary copy of weasel-clean.
This tests orchestration/rollback independently of installed Weasel versions.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from scel2rime import rime, scel

POWERSHELL = os.environ.get("SCEL2RIME_TEST_POWERSHELL") or shutil.which("pwsh") or shutil.which("powershell")
PROJECT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell integration")
class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scel2rime-install-")
        self.root = Path(self.temp.name)
        self.scripts = self.root / "scripts"
        shutil.copytree(PROJECT / "weasel-clean", self.scripts)
        self.user = self.root / "自定义 Rime"
        self.user.mkdir()
        self.source = self.root / "词库导出"
        self.source.mkdir()
        dictionary = scel.ScelDictionary(path=Path("test.scel"), entries=[scel.WordEntry("测试", ("ce", "shi"), 3)])
        rime.write(dictionary, self.source / "sample.dict.yaml", "sample")
        self.weasel = self.root / "Fake Weasel"
        (self.weasel / "data").mkdir(parents=True)
        (self.weasel / "rime.dll").write_bytes(b"never loaded")
        self.env = os.environ.copy()
        self.env["APPDATA"] = str(self.root / "default-appdata")
        self.worker("exit 0")

    def tearDown(self):
        self.temp.cleanup()

    def worker(self, body):
        (self.scripts / "deploy-worker.ps1").write_text(
            "param([string]$WeaselRoot,[string]$UserDir,[string]$LogDir)\n$ErrorActionPreference='Stop'\n" + body,
            encoding="utf-8")

    def run_script(self, name, *args):
        proc = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(self.scripts / name), *map(str,args), "-Json"],
                              env=self.env, capture_output=True, timeout=30)
        text = proc.stdout.decode("utf-8-sig", errors="replace")
        try:
            report = json.loads(text)
        except ValueError:
            self.fail(f"Invalid report: {text}\nstderr: {proc.stderr!r}")
        self.assertEqual(proc.returncode, report["exit_code"], text)
        return proc.returncode, report

    def install(self, *args):
        return self.run_script("install.ps1", "-RimeUserDir", self.user, "-From", self.source, *args)

    def seed_previous(self):
        (self.user / "default.custom.yaml").write_bytes(b"PREVIOUS CONFIG")
        (self.user / "sample.dict.yaml").write_bytes(b"PREVIOUS DICTIONARY")
        (self.user / "build").mkdir()
        (self.user / "build/scel_merged.table.bin").write_bytes(b"PREVIOUS BUILD")

    def assert_previous(self):
        self.assertEqual((self.user / "default.custom.yaml").read_bytes(), b"PREVIOUS CONFIG")
        self.assertEqual((self.user / "sample.dict.yaml").read_bytes(), b"PREVIOUS DICTIONARY")
        self.assertEqual((self.user / "build/scel_merged.table.bin").read_bytes(), b"PREVIOUS BUILD")
        self.assertFalse((self.user / "scel_merged.dict.yaml").exists())
        self.assertFalse((self.user / "weasel.custom.yaml").exists())
        self.assertFalse((self.user / "installation.yaml").exists())
        self.assertFalse((self.user / "user.yaml").exists())

    def test_missing_source_does_not_change_configuration(self):
        self.seed_previous()
        code, report = self.run_script("install.ps1", "-RimeUserDir", self.user, "-From", self.root / "absent")
        self.assertEqual(code, 1)
        self.assert_previous()
        self.assertEqual(list(self.user.glob("backup-*")), [])

    def test_empty_source_rejected_without_writes(self):
        (self.source / "sample.dict.yaml").unlink()
        code, report = self.install()
        self.assertEqual(code, 1)
        self.assertEqual(list(self.user.iterdir()), [])

    def test_dry_run_does_not_even_create_lock_or_backup(self):
        code, report = self.install("-DryRun")
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "planned")
        self.assertEqual(list(self.user.iterdir()), [])

    def test_backup_and_rollback_restore_dictionary_and_remove_new_files(self):
        self.seed_previous()
        code, report = self.install()
        self.assertEqual(code, 0, report)
        backup = Path(report["backup_dir"])
        self.assertEqual((backup / "sample.dict.yaml").read_bytes(), b"PREVIOUS DICTIONARY")
        self.assertNotEqual((self.user / "sample.dict.yaml").read_bytes(), b"PREVIOUS DICTIONARY")
        code, restored = self.run_script("rollback.ps1", "-BackupDir", backup)
        self.assertEqual(code, 0, restored)
        self.assert_previous()

    def test_tampered_backup_refused_before_restore(self):
        self.seed_previous()
        code, report = self.install()
        self.assertEqual(code, 0, report)
        backup = Path(report["backup_dir"])
        (backup / "sample.dict.yaml").write_bytes(b"TAMPERED")
        before = (self.user / "default.custom.yaml").read_bytes()
        code, report = self.run_script("rollback.ps1", "-BackupDir", backup)
        self.assertEqual(code, 1)
        self.assertEqual((self.user / "default.custom.yaml").read_bytes(), before)

    def test_reserved_and_mismatched_dictionary_names_rejected(self):
        (self.source / "sample.dict.yaml").rename(self.source / "scel_merged.dict.yaml")
        code, report = self.install()
        self.assertEqual(code, 1)
        self.assertEqual(list(self.user.iterdir()), [])
        (self.source / "scel_merged.dict.yaml").rename(self.source / "wrong.dict.yaml")
        code, report = self.install()
        self.assertEqual(code, 1)
        self.assertEqual(list(self.user.iterdir()), [])

    def test_old_binary_never_counts_as_new_success(self):
        self.seed_previous()
        code, report = self.install("-Deploy", "-WeaselRoot", self.weasel)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "rolled_back", report)
        self.assert_previous()

    def test_native_failure_restores_configuration_and_build(self):
        self.seed_previous()
        self.worker("[IO.File]::WriteAllText((Join-Path $UserDir 'user.yaml'),'changed'); exit 7")
        code, report = self.install("-Deploy", "-WeaselRoot", self.weasel)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "rolled_back", report)
        self.assert_previous()

    def test_timeout_terminates_worker_and_restores(self):
        self.seed_previous()
        self.worker("Start-Sleep -Seconds 10")
        code, report = self.install("-Deploy", "-WeaselRoot", self.weasel, "-TimeoutSeconds", "1")
        self.assertEqual(code, 1)
        self.assertIn("timed out", report.get("error", ""), report)
        self.assert_previous()

    def test_native_error_log_blocks_success(self):
        self.seed_previous()
        self.worker("[IO.File]::WriteAllText((Join-Path $LogDir 'rime.ERROR.fake.log'),'compiler error')")
        code, report = self.install("-Deploy", "-WeaselRoot", self.weasel)
        self.assertEqual(code, 1)
        self.assertIn("Native compiler reported errors", report.get("error", ""), report)
        self.assert_previous()

    def test_custom_directory_forwarded_and_verified_build_can_be_rolled_back(self):
        self.seed_previous()
        self.worker(r"""
[IO.File]::WriteAllText((Join-Path $UserDir 'build\scel_merged.table.bin'),'new table')
[IO.File]::WriteAllText((Join-Path $UserDir 'build\luna_pinyin_simp.prism.bin'),'new prism')
[IO.File]::WriteAllText((Join-Path $UserDir 'build\luna_pinyin_simp.schema.yaml'),"translator:`n  dictionary: scel_merged`n")
""")
        code, report = self.install("-Deploy", "-WeaselRoot", self.weasel)
        self.assertEqual(code, 0, report)
        self.assertTrue(report["compiled"])
        self.assertEqual(report["deployment"]["user_dir"], str(self.user))
        self.assertFalse(Path(self.env["APPDATA"]).exists())
        code, restored = self.run_script("rollback.ps1", "-BackupDir", report["backup_dir"])
        self.assertEqual(code, 0, restored)
        self.assert_previous()

if __name__ == "__main__":
    unittest.main()

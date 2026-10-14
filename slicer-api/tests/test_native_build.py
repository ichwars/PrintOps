"""Integrity/architecture boundaries for the native image build (no network)."""

import hashlib
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "native_build.py"


class NativeBuildTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), "native build integrity helper is missing")
        spec = importlib.util.spec_from_file_location("native_build", SCRIPT)
        self.build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.build)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def elf(self, machine, *, bits=2, endian=1):
        content = bytearray(64)
        content[:6] = b"\x7fELF" + bytes([bits, endian])
        struct.pack_into("<H", content, 18, machine)
        path = self.root / "engine"
        path.write_bytes(content)
        return path

    def test_official_arm_asset_and_machine_selected_together(self):
        asset = self.build.engine_asset("arm64")
        self.assertEqual(asset["machine"], 183)
        self.assertTrue(asset["url"].startswith("https://github.com/OrcaSlicer/OrcaSlicer/releases/download/v2.4.2/"))
        self.assertTrue(asset["url"].endswith("Ubuntu2404_aarch64_V2.4.2.AppImage"))
        self.assertEqual(asset["sha256"], "e1a07275a25f176626c55a5df39e91bc4476d8c28ee4a3192ff758e29dd5c3ba")

    def test_official_amd_asset_and_machine_selected_together(self):
        asset = self.build.engine_asset("amd64")
        self.assertEqual(asset["machine"], 62)
        self.assertTrue(asset["url"].endswith("Ubuntu2404_V2.4.2.AppImage"))
        self.assertEqual(asset["sha256"], "d12fb8c8eac1aecd2dfb6377acd48f994f8fa439ed5292fa532dd82880f029fd")

    def test_unknown_architecture_rejected_before_download(self):
        with patch.object(self.build, "download_verified") as download:
            with self.assertRaisesRegex(ValueError, "Unsupported architecture"):
                self.build.install_engine("arm", self.root)
            download.assert_not_called()

    def test_native_elf_accepted_on_each_supported_architecture(self):
        for arch, machine in [("arm64", 183), ("amd64", 62)]:
            self.build.verify_elf(self.elf(machine), arch)

    def test_foreign_elf_rejected(self):
        with self.assertRaisesRegex(ValueError, "ELF architecture mismatch"):
            self.build.verify_elf(self.elf(62), "arm64")

    def test_invalid_elf_class_endianness_and_truncation_rejected(self):
        for bits, endian in [(1, 1), (2, 2)]:
            with self.assertRaises(ValueError):
                self.build.verify_elf(self.elf(183, bits=bits, endian=endian), "arm64")
        path = self.root / "empty"
        path.write_bytes(b"\x7fELF")
        with self.assertRaises(ValueError):
            self.build.verify_elf(path, "arm64")

    def test_download_checks_hash_and_removes_untrusted_content(self):
        import io

        target = self.root / "download"
        with (
            patch.object(self.build.urllib.request, "urlopen", return_value=io.BytesIO(b"corrupt")),
            self.assertRaisesRegex(ValueError, "SHA256 mismatch"),
        ):
            self.build.download_verified("https://example.test/asset", "0" * 64, target)
        self.assertFalse(target.exists())

    def test_download_preserves_verified_content(self):
        import io

        target = self.root / "download"
        with patch.object(self.build.urllib.request, "urlopen", return_value=io.BytesIO(b"correct")):
            self.build.download_verified("https://example.test/asset", hashlib.sha256(b"correct").hexdigest(), target)
        self.assertEqual(target.read_bytes(), b"correct")

    def test_corrupt_engine_never_executes_extraction(self):
        with (
            patch.object(self.build, "download_verified", side_effect=ValueError("SHA256 mismatch")),
            patch.object(self.build.subprocess, "run") as run,
        ):
            with self.assertRaises(ValueError):
                self.build.install_engine("arm64", self.root)
            run.assert_not_called()

    def test_foreign_appimage_never_executes_extraction(self):
        def download(url, sha, target):
            target.write_bytes(self.elf(62).read_bytes())

        with (
            patch.object(self.build, "download_verified", side_effect=download),
            patch.object(self.build.subprocess, "run") as run,
        ):
            with self.assertRaises(ValueError):
                self.build.install_engine("arm64", self.root)
            run.assert_not_called()

    def test_extracted_engine_is_checked_not_just_appimage_runtime(self):
        def download(url, sha, target):
            target.write_bytes(self.elf(183).read_bytes())

        def extract(*args, **kwargs):
            engine = self.root / "squashfs-root/bin/orca-slicer"
            engine.parent.mkdir(parents=True)
            engine.write_bytes(self.elf(62).read_bytes())

        with (
            patch.object(self.build, "download_verified", side_effect=download),
            patch.object(self.build.subprocess, "run", side_effect=extract),
            self.assertRaisesRegex(ValueError, "ELF architecture mismatch"),
        ):
            self.build.install_engine("arm64", self.root)


if __name__ == "__main__":
    unittest.main()

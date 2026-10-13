"""Exercise the preservation and discovery checks with broken checkout copies."""

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validate_repo", ROOT / "tools/validate_repo.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
        self.skills = self.root / "plugins/firmware-reverse-engineering/skills"

    def test_approved_checkout_has_no_release_blockers(self):
        errors, blockers = validator.validate(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(blockers, [])

    def test_missing_plugin_license_blocks_release(self):
        (self.root / "plugins/firmware-reverse-engineering/LICENSE").unlink()
        _, blockers = validator.validate(self.root)
        self.assertTrue(any("Missing LICENSE" in issue for issue in blockers))

    def test_skill_edit_is_rejected(self):
        path = self.skills / "firmware-extraction/SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nChanged instruction.\n")
        errors, _ = validator.validate(self.root)
        self.assertTrue(any("Protected skill content changed" in issue for issue in errors))

    def test_dropped_resource_is_rejected(self):
        (self.skills / "firmware-static-analysis/references/architectures.md").unlink()
        errors, blockers = validator.validate(self.root)
        self.assertTrue(any("Approved skill file missing" in issue for issue in errors))
        self.assertTrue(any("architectures.md" in issue for issue in blockers))

    def test_unapproved_new_script_is_rejected(self):
        (self.skills / "ghidra-re/scripts/unapproved_script.py").write_text("pass\n")
        errors, _ = validator.validate(self.root)
        self.assertTrue(any("added without a baseline" in issue for issue in errors))

    def test_broken_catalog_source_is_rejected(self):
        path = self.root / ".agents/plugins/marketplace.json"
        data = json.loads(path.read_text())
        data["plugins"][0]["source"]["path"] = "./nonexistent"
        path.write_text(json.dumps(data))
        errors, _ = validator.validate(self.root)
        self.assertTrue(any("does not resolve" in issue for issue in errors))

    def test_manifest_version_drift_is_rejected(self):
        path = self.root / "plugins/firmware-reverse-engineering/.codex-plugin/plugin.json"
        data = json.loads(path.read_text())
        data["version"] = "9.0.0"
        path.write_text(json.dumps(data))
        errors, _ = validator.validate(self.root)
        self.assertIn("Plugin manifests must agree on version", errors)

    def test_factory_manifest_metadata_drift_is_rejected(self):
        path = self.root / "plugins/firmware-reverse-engineering/.factory-plugin/plugin.json"
        original = json.loads(path.read_text())
        for field in ("name", "version", "description", "author", "repository", "skills", "license"):
            with self.subTest(field=field):
                data = dict(original)
                data[field] = "different"
                path.write_text(json.dumps(data))
                errors, _ = validator.validate(self.root)
                self.assertIn(f"Plugin manifests must agree on {field}", errors)

    def test_missing_factory_packaging_is_rejected(self):
        for relative in (
            ".factory-plugin/marketplace.json",
            "plugins/firmware-reverse-engineering/.factory-plugin/plugin.json",
        ):
            with self.subTest(path=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.unlink()
                errors, _ = validator.validate(self.root)
                self.assertTrue(any("Validation could not complete" in issue for issue in errors))
                path.write_bytes(original)

    def test_broken_factory_catalog_source_is_rejected(self):
        path = self.root / ".factory-plugin/marketplace.json"
        data = json.loads(path.read_text())
        data["plugins"][0]["source"] = "./nonexistent"
        path.write_text(json.dumps(data))
        errors, _ = validator.validate(self.root)
        self.assertTrue(any(".factory-plugin/marketplace.json: plugin name or source does not resolve" in issue
                            for issue in errors))

    def test_stale_factory_catalog_version_is_rejected(self):
        path = self.root / ".factory-plugin/marketplace.json"
        data = json.loads(path.read_text())
        data["plugins"][0]["version"] = "9.0.0"
        path.write_text(json.dumps(data))
        errors, _ = validator.validate(self.root)
        self.assertIn(".factory-plugin/marketplace.json: stale marketplace version", errors)

    def test_factory_additional_components_are_rejected(self):
        path = self.root / "plugins/firmware-reverse-engineering/.factory-plugin/plugin.json"
        original = json.loads(path.read_text())
        for component in ("hooks", "mcpServers", "apps", "commands", "agents", "droids"):
            with self.subTest(component=component):
                data = dict(original)
                data[component] = {}
                path.write_text(json.dumps(data))
                errors, _ = validator.validate(self.root)
                self.assertIn("Factory: unexpected executable or additional components", errors)


if __name__ == "__main__":
    unittest.main()

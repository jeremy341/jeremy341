import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "scripts" / "update_profile_cache.py"


def load_updater():
    spec = importlib.util.spec_from_file_location("update_profile_cache", UPDATER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProfileCacheUpdaterTests(unittest.TestCase):
    def test_updates_only_profile_cache_queries_and_is_idempotent(self):
        source = (
            '<source media="(max-width: 700px)" '
            'srcset="https://raw.githubusercontent.com/jeremy341/jeremy341/main/assets/profile-mobile-dark.svg?v=old">\n'
            '<img alt="Jeremy Darko profile" '
            'src="https://raw.githubusercontent.com/jeremy341/jeremy341/main/assets/profile-dark.svg?v=old">'
            '\n<a href="https://example.com/page?v=keep">link</a>'
        )
        updated = load_updater().update_cache_versions(source, "a1b2c3d4e5f6", "0f1e2d3c4b5a")

        self.assertIn("profile-dark.svg?v=a1b2c3d4e5f6", updated)
        self.assertIn("profile-mobile-dark.svg?v=0f1e2d3c4b5a", updated)
        self.assertIn('alt="Jeremy Darko profile"', updated)
        self.assertIn("https://example.com/page?v=keep", updated)
        self.assertEqual(load_updater().update_cache_versions(updated, "a1b2c3d4e5f6", "0f1e2d3c4b5a"), updated)

    def test_rejects_malformed_digest(self):
        source = self._readme_targets()
        with self.assertRaisesRegex(ValueError, "digest"):
            load_updater().update_cache_versions(source, "ABC", "0f1e2d3c4b5a")

    def test_rejects_missing_or_duplicate_expected_url(self):
        updater = load_updater()
        source = self._readme_targets().replace("profile-dark.svg?v=old", "other.svg?v=old")
        with self.assertRaisesRegex(ValueError, "profile-dark"):
            updater.update_cache_versions(source, "a1b2c3d4e5f6", "0f1e2d3c4b5a")
        source = self._readme_targets() + '\n<img src="https://raw.githubusercontent.com/jeremy341/jeremy341/main/assets/profile-dark.svg?v=old">'
        with self.assertRaisesRegex(ValueError, "once"):
            updater.update_cache_versions(source, "a1b2c3d4e5f6", "0f1e2d3c4b5a")

    @staticmethod
    def _readme_targets():
        return (
            'srcset="https://raw.githubusercontent.com/jeremy341/jeremy341/main/assets/profile-mobile-dark.svg?v=old"\n'
            'src="https://raw.githubusercontent.com/jeremy341/jeremy341/main/assets/profile-dark.svg?v=old"'
        )


if __name__ == "__main__":
    unittest.main()

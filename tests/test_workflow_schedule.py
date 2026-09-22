import re
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "refresh-profile.yml"


class WorkflowScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_schedule_runs_at_the_requested_berlin_times(self):
        self.assertRegex(self.workflow, r'(?m)^\s+- cron: "0 10,15,20 \* \* \*"$')
        self.assertRegex(self.workflow, r'(?m)^\s+timezone: "Europe/Berlin"$')

    def test_manual_dispatch_remains_enabled(self):
        self.assertRegex(self.workflow, r"(?m)^\s+workflow_dispatch:\s*$")

    def test_refresh_runs_regression_tests_updates_cache_and_stages_readme(self):
        test_step = re.search(
            r'(?m)^\s+run: python -m unittest discover -s tests -p "test_\*\.py" -v$',
            self.workflow,
        )
        render_step = re.search(r"(?m)^\s+run: python scripts/render_profile.py$", self.workflow)
        cache_step = re.search(r"(?m)^\s+run: python scripts/update_profile_cache.py$", self.workflow)

        self.assertIsNotNone(test_step, "workflow must run the regression suite")
        self.assertIsNotNone(render_step, "workflow must render profile cards")
        self.assertIsNotNone(cache_step, "workflow must update README cache versions after rendering")
        self.assertLess(test_step.start(), render_step.start())
        self.assertLess(render_step.start(), cache_step.start())
        self.assertRegex(self.workflow, r"(?m)^\s+git add -A assets README\.md$")

    def test_push_filter_includes_profile_inputs_and_tests(self):
        expected_paths = {
            "README.md",
            "scripts/profile_data.json",
            "scripts/render_profile.py",
            "scripts/update_profile_cache.py",
            "tests/test_render_profile.py",
            "tests/test_update_profile_cache.py",
            "tests/test_workflow_schedule.py",
        }
        push_block = re.search(
            r"(?ms)^  push:\n(?P<block>.*?)(?=^  [A-Za-z_][A-Za-z0-9_-]*:|\Z)",
            self.workflow,
        )
        self.assertIsNotNone(push_block, "workflow must retain a push trigger")
        configured_paths = set(
            re.findall(r'^\s+- "([^"\n]+)"\s*$', push_block.group("block"), re.MULTILINE)
        )
        self.assertTrue(expected_paths.issubset(configured_paths), expected_paths - configured_paths)


if __name__ == "__main__":
    unittest.main()

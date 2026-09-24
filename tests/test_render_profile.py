from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import copy
import importlib.util
import json
import os
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "scripts" / "render_profile.py"
PROFILE_DATA = ROOT / "scripts" / "profile_data.json"
FIXED_BERLIN_TIME = datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("Europe/Berlin"))
SVG_NS = "http://www.w3.org/2000/svg"


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_profile", RENDERER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RendererSyntaxTests(unittest.TestCase):
    def test_renderer_source_compiles(self):
        source = RENDERER.read_text(encoding="utf-8")
        compile(source, str(RENDERER), "exec")


class ProfileRendererTests(unittest.TestCase):
    def test_curated_profile_has_required_fields(self):
        profile = load_renderer().load_profile_data(PROFILE_DATA)
        self.assertTrue({"name", "role", "location", "focus", "selected_work", "current_research", "stack", "links"} <= profile.keys())

    def test_renders_four_well_formed_named_svg_variants(self):
        module = load_renderer()
        profile = module.load_profile_data(PROFILE_DATA)
        variants = module.render_svg_variants(profile, now=FIXED_BERLIN_TIME)
        self.assertEqual(set(variants), {"profile-dark.svg", "profile-light.svg", "profile-mobile-dark.svg", "profile-mobile-light.svg"})
        for filename, svg in variants.items():
            with self.subTest(filename=filename):
                root = ET.fromstring(svg)
                self.assertEqual(root.tag, f"{{{SVG_NS}}}svg")
                self.assertIsNotNone(root.find(f"{{{SVG_NS}}}title"))
                self.assertIsNotNone(root.find(f"{{{SVG_NS}}}desc"))

    def test_xml_escapes_profile_text_without_losing_parsed_value(self):
        module = load_renderer()
        profile = copy.deepcopy(module.load_profile_data(PROFILE_DATA))
        profile["name"] = "Lab & GPU <systems>"
        variants = module.render_svg_variants(profile, now=FIXED_BERLIN_TIME)
        for svg in variants.values():
            root = ET.fromstring(svg)
            text = "".join(root.itertext())
            self.assertIn("Lab & GPU <systems>", text)

    def test_rendering_needs_no_environment_or_credentials(self):
        module = load_renderer()
        profile = module.load_profile_data(PROFILE_DATA)
        previous = dict(os.environ)
        try:
            os.environ.clear()
            variants = module.render_svg_variants(profile, now=FIXED_BERLIN_TIME)
        finally:
            os.environ.update(previous)
        self.assertEqual(len(variants), 4)

    def test_injected_timestamp_is_rendered_in_berlin_cet_and_cest(self):
        module = load_renderer()
        profile = module.load_profile_data(PROFILE_DATA)
        winter = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)
        summer = datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)
        for instant, expected in ((winter, "10:00 CET"), (summer, "10:00 CEST")):
            with self.subTest(expected=expected):
                desktop = module.render_svg_variants(profile, now=instant)["profile-dark.svg"]
                self.assertIn(expected, "".join(ET.fromstring(desktop).itertext()))


class ProfileLayoutTests(unittest.TestCase):
    def test_variants_use_a_power_shell_transcript_structure(self):
        renderer = load_renderer()
        variants = renderer.render_svg_variants(renderer.load_profile_data(PROFILE_DATA), FIXED_BERLIN_TIME)
        for svg in variants.values():
            self.assertIn("PS C:\\Users\\Jeremy&gt;", svg)
            for command in ("Get-DeveloperProfile", "Get-Focus", "Get-SelectedWork", "Get-CurrentResearch"):
                self.assertIn(command, svg)
            self.assertIn("[online]", svg)
            self.assertNotIn("SELECTED WORK  /  VERIFIED PROJECT NOTES", svg)

    def test_variants_contain_selected_work_and_not_activity_metrics(self):
        module = load_renderer()
        variants = module.render_svg_variants(module.load_profile_data(PROFILE_DATA), FIXED_BERLIN_TIME)
        for svg in variants.values():
            for text in ("MIRA", "Poorup", "FluidicStudio", "ESP32-S3 Alarm Clock", "TorchVK", "Early research"):
                self.assertIn(text, svg)
            self.assertNotIn("NIMBL", svg)
            self.assertIn("AI Agents", svg)
            for term in ("Age", "years", "months", "2009-08-12", "Total Commits", "Current Streak", "Hackatime", "Stars", "Repositories", "Added", "Removed"):
                self.assertNotRegex(svg, rf"\b{re.escape(term)}\b")

    def test_desktop_proof_lines_stay_within_the_project_column_budget(self):
        module = load_renderer()
        profile = copy.deepcopy(module.load_profile_data(PROFILE_DATA))
        profile["selected_work"][0]["proof"] = "X" * 90
        desktop = module._desktop(profile, module.THEMES["dark"], FIXED_BERLIN_TIME)
        root = ET.fromstring(desktop)
        proof_lines = [
            node.text or ""
            for node in root.findall(f"{{{SVG_NS}}}text")
            if node.get("x") == "146" and "X" in (node.text or "")
        ]
        self.assertGreater(len(proof_lines), 1)
        self.assertTrue(all(len(line) <= 112 for line in proof_lines))

    def test_mobile_variants_include_the_torchvk_research_question(self):
        module = load_renderer()
        variants = module.render_svg_variants(module.load_profile_data(PROFILE_DATA), FIXED_BERLIN_TIME)
        question = "Can Vulkan Compute execute a minimal PyTorch training loop on consumer GPUs?"
        for filename in ("profile-mobile-dark.svg", "profile-mobile-light.svg"):
            with self.subTest(filename=filename):
                root = ET.fromstring(variants[filename])
                visible_text = " ".join(node.text or "" for node in root.findall(f".//{{{SVG_NS}}}text"))
                self.assertIn(question, visible_text)

    def test_mobile_project_titles_clear_the_previous_evidence_by_24_units(self):
        module = load_renderer()
        variants = module.render_svg_variants(module.load_profile_data(PROFILE_DATA), FIXED_BERLIN_TIME)
        transitions = (
            ("415-image validation split", "Poorup"),
            ("server rules; CI", "FluidicStudio"),
            ("workflows; saved sessions", "ESP32-S3 Alarm Clock"),
        )
        for filename in ("profile-mobile-dark.svg", "profile-mobile-light.svg"):
            root = ET.fromstring(variants[filename])
            text_nodes = root.findall(f".//{{{SVG_NS}}}text")
            for previous_evidence, next_title in transitions:
                with self.subTest(filename=filename, next_title=next_title):
                    evidence_y = next(
                        int(node.get("y")) for node in text_nodes
                        if previous_evidence in (node.text or "")
                    )
                    title_y = next(
                        int(node.get("y")) for node in text_nodes
                        if (node.text or "") == next_title
                    )
                    self.assertGreaterEqual(title_y - evidence_y, 24)

    def test_mobile_copy_wraps_to_the_available_width(self):
        module = load_renderer()
        lines = module.wrap_svg_text("ESP32-S3 Alarm Clock with custom PCB and WebSerial configuration", 34)
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(len(line) <= 34 for line in lines))


class AtomicAssetWriteTests(unittest.TestCase):
    def test_invalid_variant_preserves_all_existing_assets(self):
        module = load_renderer()
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory)
            old_asset = output / "profile-dark.svg"
            old_asset.write_text("last-known-good", encoding="utf-8")
            variants = {"profile-dark.svg": "<svg", "profile-light.svg": "<svg/>"}
            with self.assertRaises(ET.ParseError):
                module.write_svg_variants(variants, output)
            self.assertEqual(old_asset.read_text(encoding="utf-8"), "last-known-good")


if __name__ == "__main__":
    unittest.main()

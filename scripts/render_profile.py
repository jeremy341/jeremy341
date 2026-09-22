"""Render deterministic SVG profile cards from reviewed, curated data."""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import tempfile
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PROFILE_DATA = ROOT / "scripts" / "profile_data.json"
BERLIN = ZoneInfo("Europe/Berlin")
SVG_NS = "http://www.w3.org/2000/svg"

# Dark and light files intentionally retain the same graphite terminal identity.
THEMES = {
    "dark": {"background": "#0B0F12", "panel": "#121A1F", "primary": "#F1F6F8", "secondary": "#A8B6BC", "rule": "#2B3940", "accent": "#52D7F2"},
    "light": {"background": "#0B0F12", "panel": "#121A1F", "primary": "#F1F6F8", "secondary": "#A8B6BC", "rule": "#2B3940", "accent": "#52D7F2"},
}
FONT_STACK = "'Cascadia Code','JetBrains Mono',Consolas,monospace"


def load_profile_data(path: Path) -> dict[str, object]:
    """Load the reviewed profile JSON without consulting runtime services."""
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    if not isinstance(data, dict):
        raise ValueError("profile data must be a JSON object")
    return data


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def wrap_svg_text(value: str, max_chars: int) -> list[str]:
    """Wrap prose on word boundaries, splitting only words longer than the limit."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    return textwrap.wrap(
        str(value), width=max_chars, break_long_words=True,
        break_on_hyphens=False, replace_whitespace=True, drop_whitespace=True,
    ) or [""]


def _text(x: int, y: int, value: object, *, size: int = 16, color: str = "primary", weight: int = 400) -> str:
    return f'<text x="{x}" y="{y}" class="{color}" font-size="{size}" font-weight="{weight}">{_e(value)}</text>'


def _wrapped(x: int, y: int, value: str, max_chars: int, *, size: int = 14, color: str = "primary", line_height: int | None = None, weight: int = 400) -> tuple[str, int]:
    step = line_height if line_height is not None else size + 6
    rows = wrap_svg_text(value, max_chars)
    markup = "".join(_text(x, y + index * step, row, size=size, color=color, weight=weight) for index, row in enumerate(rows))
    return markup, len(rows) * step


def _link(x: int, y: int, value: object, href: object, *, size: int = 17) -> str:
    return f'<a href="{_e(href)}">{_text(x, y, value, size=size, color="accent", weight=600)}</a>'


def _root(width: int, height: int, theme: dict[str, str], title: str, description: str, body: list[str]) -> str:
    style = (
        f'<style>text{{font-family:{FONT_STACK}}}.primary{{fill:{theme["primary"]}}}'
        f'.secondary{{fill:{theme["secondary"]}}}.accent{{fill:{theme["accent"]}}}'
        f'.rule{{stroke:{theme["rule"]}}}a{{text-decoration:none}}</style>'
    )
    content = [
        f'<svg xmlns="{SVG_NS}" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="card-title card-desc">',
        f'<title id="card-title">{_e(title)}</title>',
        f'<desc id="card-desc">{_e(description)}</desc>',
        style,
        f'<rect width="{width}" height="{height}" fill="{theme["background"]}"/>',
        f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="none" stroke="{theme["rule"]}"/>',
        *body,
        "</svg>",
    ]
    return "".join(content)


def _terminal_bar(width: int, theme: dict[str, str]) -> list[str]:
    return [
        f'<rect x="1" y="1" width="{width - 2}" height="48" fill="{theme["panel"]}"/>',
        f'<path d="M {width - 96} 1 V 49 M {width - 64} 1 V 49 M {width - 32} 1 V 49" class="rule"/>',
        _text(18, 31, "PowerShell 7.5.2", size=16, color="primary", weight=600),
        f'<path d="M {width - 82} 22 h12 M {width - 51} 27 l6 -6 6 6 M {width - 20} 20 l8 8 M {width - 12} 20 l-8 8" fill="none" class="secondary" stroke="{theme["secondary"]}" stroke-width="1.5"/>',
    ]


def _desktop(profile: dict[str, Any], theme: dict[str, str], now: dt.datetime) -> str:
    width, height = 1000, 900
    timestamp = now.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M %Z")
    body = _terminal_bar(width, theme)
    body.extend([
        _text(42, 104, profile["name"], size=31, color="primary", weight=700),
        _text(42, 134, profile["role"], size=16, color="accent", weight=600),
        _text(42, 159, profile["location"], size=14, color="secondary"),
        _text(42, 202, "SELECTED WORK  /  VERIFIED PROJECT NOTES", size=12, color="accent", weight=700),
    ])

    y = 235
    for index, work in enumerate(profile.get("selected_work", []), start=1):
        body.append(_text(42, y, f"{index:02d}", size=12, color="secondary", weight=600))
        body.append(_link(83, y, work["name"], work["href"], size=18))
        # Each metadata/evidence row wraps within the fixed project column; no claim is clipped.
        meta, meta_height = _wrapped(83, y + 23, f"{work['area']}  /  {work['status']}", 75, size=13, color="secondary", line_height=18)
        proof_text = work["proof"]
        if work["name"] == "MIRA":
            proof_text += "; 1,375-image test split not evaluated"
        proof, proof_height = _wrapped(83, y + 24 + meta_height, proof_text, 68, size=13, color="primary", line_height=18)
        body.extend([meta, proof, f'<path d="M 42 {y + 34 + meta_height + proof_height} H 638" class="rule"/>'])
        y += 50 + meta_height + proof_height

    # Right-hand information rail uses hierarchy and whitespace, not project tiles.
    body.extend([
        f'<path d="M 674 86 V 780" class="rule"/>',
        _text(706, 104, "FOCUS", size=12, color="accent", weight=700),
    ])
    focus_y = 136
    for focus in profile.get("focus", []):
        body.append(_text(706, focus_y, focus["label"].upper(), size=11, color="secondary", weight=600))
        focus_copy, focus_height = _wrapped(706, focus_y + 21, focus["value"], 30, size=14, color="primary", line_height=19)
        body.append(focus_copy)
        focus_y += 26 + focus_height
    research = profile["current_research"]
    body.extend([
        _text(706, focus_y + 13, "CURRENT RESEARCH", size=12, color="accent", weight=700),
        _link(706, focus_y + 44, research["name"], research["href"], size=18),
        _text(706, focus_y + 66, research["status"], size=13, color="secondary", weight=600),
    ])
    question, _ = _wrapped(706, focus_y + 90, research["question"], 30, size=13, color="primary", line_height=19)
    body.append(question)
    body.extend([
        _text(706, 710, "STACK", size=12, color="accent", weight=700),
    ])
    stack, _ = _wrapped(706, 738, profile["stack"], 31, size=13, color="primary", line_height=19)
    body.extend([stack, _text(42, 856, f"LAST SYNC / {timestamp}", size=12, color="secondary")])
    body.append(_text(42, 878, "PS> █", size=13, color="accent", weight=600))
    return _root(width, height, theme, f"{profile['name']} — profile", "Industrial PowerShell profile card with focus hierarchy, four selected projects, early Vulkan research, stack and Berlin sync time.", body)


def _mobile(profile: dict[str, Any], theme: dict[str, str], now: dt.datetime) -> str:
    width = 400
    x = 20
    timestamp = now.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M %Z")
    body = _terminal_bar(width, theme)
    body.extend([
        _text(x, 80, profile["name"], size=25, color="primary", weight=700),
        _text(x, 105, profile["role"], size=14, color="accent", weight=600),
        _text(x, 125, profile["location"], size=14, color="secondary"),
        _text(x, 155, "FOCUS", size=12, color="accent", weight=700),
    ])
    focus_y = 178
    compact_focus = {
        "Primary": "PRIMARY / ML systems / Comp. Engineering",
        "Secondary": "SECONDARY / Embedded / hardware-software",
        "Emerging": "EMERGING / GPU / Vulkan / PyTorch systems",
        "Supporting": "SUPPORTING / Computer Vision / Full-stack / AI Agents",
    }
    for focus in profile.get("focus", []):
        focus_copy, height = _wrapped(x, focus_y, compact_focus.get(focus["label"], f"{focus['label'].upper()} / {focus['value']}"), 42, size=14, color="primary", line_height=18)
        body.append(focus_copy)
        focus_y += max(18, height)
    work_heading_y = focus_y + 5
    body.append(_text(x, work_heading_y, "SELECTED WORK", size=12, color="accent", weight=700))
    y = work_heading_y + 29
    mobile_evidence = {
        "MIRA": "90.6% mAP50; EXP-019: 90.58%; 415-image validation split",
        "NIMBL": "Local context; request budgets; persistent sessions; benchmarks",
        "FluidicStudio": "PyQt6 pumps; sensor data; camera workflows; saved sessions",
        "ESP32-S3 Alarm Clock": "PCB; C++ firmware; TFT; WebSerial config",
    }
    mobile_meta = {
        "MIRA": "CV / ML / validation only; 1,375-image test split not evaluated",
        "NIMBL": "AI Systems  /  Experimental prerelease",
        "FluidicStudio": "Lab software / core workflows; pump-driver detection experimental",
        "ESP32-S3 Alarm Clock": "Basic ESP32 serial tested; full-board bring-up not documented",
    }
    for index, work in enumerate(profile.get("selected_work", []), start=1):
        body.append(_text(x, y, f"{index:02d}", size=11, color="secondary", weight=600))
        body.append(_link(x + 37, y, work["name"], work["href"], size=16))
        meta, meta_height = _wrapped(x + 37, y + 19, mobile_meta.get(work["name"], f"{work['area']}  /  {work['status']}"), 34, size=13, color="secondary", line_height=15)
        proof, proof_height = _wrapped(x + 37, y + 20 + meta_height, mobile_evidence.get(work["name"], work["proof"]), 34, size=14, color="primary", line_height=16)
        body.extend([meta, proof])
        y += 28 + meta_height + proof_height
        body.append(f'<path d="M {x} {y - 18} H {width - x}" class="rule"/>')

    research = profile["current_research"]
    body.extend([
        _text(x, y + 3, "CURRENT RESEARCH", size=12, color="accent", weight=700),
        _link(x, y + 29, research["name"], research["href"], size=16),
        _text(x + 91, y + 29, research["status"], size=13, color="secondary", weight=600),
    ])
    question, question_height = _wrapped(x, y + 51, research["question"], 40, size=14, color="primary", line_height=17)
    body.append(question)
    stack_y = y + 51 + question_height + 8
    body.extend([_text(x, stack_y, "STACK", size=12, color="accent", weight=700)])
    stack, stack_height = _wrapped(x, stack_y + 18, profile["stack"], 34, size=14, color="primary", line_height=17)
    body.extend([
        stack,
        _text(x, stack_y + 22 + stack_height, f"LAST SYNC / {timestamp}", size=11, color="secondary"),
        _text(x, stack_y + 39 + stack_height, "PS> █", size=13, color="accent", weight=600),
    ])
    height = stack_y + 49 + stack_height
    if height > 860:
        raise ValueError(f"mobile profile content exceeds 860 units ({height})")
    return _root(width, height, theme, f"{profile['name']} — profile", "Compact PowerShell profile card with focus hierarchy, four selected projects, early Vulkan research, stack and Berlin sync time.", body)


def _render(profile: dict[str, Any], theme: dict[str, str], *, mobile: bool, now: dt.datetime) -> str:
    return _mobile(profile, theme, now) if mobile else _desktop(profile, theme, now)


def render_svg_variants(profile: dict[str, object], now: dt.datetime | None = None) -> dict[str, str]:
    """Return all four SVG documents; no environment or network access occurs."""
    timestamp = now if now is not None else dt.datetime.now(BERLIN)
    result: dict[str, str] = {}
    for theme_name, theme in THEMES.items():
        for mobile in (False, True):
            prefix = "profile-mobile-" if mobile else "profile-"
            result[f"{prefix}{theme_name}.svg"] = _render(profile, theme, mobile=mobile, now=timestamp)
    return result


def write_svg_variants(variants: dict[str, str], output_dir: Path) -> None:
    """Validate every SVG before staging sibling temp files and replacing outputs."""
    for filename, svg in variants.items():
        if Path(filename).name != filename or not filename.endswith(".svg"):
            raise ValueError(f"invalid SVG output name: {filename!r}")
        root = ET.fromstring(svg)
        if root.tag not in {"svg", f"{{{SVG_NS}}}svg"}:
            raise ValueError(f"{filename} must contain an SVG root element")

    output_dir.mkdir(parents=True, exist_ok=True)
    temporary: list[tuple[Path, Path]] = []
    try:
        for filename, svg in variants.items():
            fd, temp_name = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=output_dir)
            temp_path = Path(temp_name)
            temporary.append((temp_path, output_dir / filename))
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                stream.write(svg)
        for temp_path, destination in temporary:
            os.replace(temp_path, destination)
    except Exception:
        for temp_path, _ in temporary:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def main() -> None:
    profile = load_profile_data(PROFILE_DATA)
    write_svg_variants(render_svg_variants(profile), ASSETS)


if __name__ == "__main__":
    main()

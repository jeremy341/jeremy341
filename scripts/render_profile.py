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


def _prompt(
    x: int,
    y: int,
    command: str,
    *,
    command_x: int,
    path: str = "PS C:\\Users\\Jeremy\\portfolio>",
    size: int = 13,
) -> list[str]:
    """Render a prompt and command as two aligned terminal transcript cells."""
    return [
        _text(x, y, path, size=size, color="accent", weight=600),
        _text(command_x, y, command, size=size, color="primary", weight=600),
    ]


def _terminal_bar(width: int, theme: dict[str, str], timestamp: str | None = None) -> list[str]:
    """Render Windows Terminal chrome without macOS-style traffic lights."""
    body = [
        f'<rect x="1" y="1" width="{width - 2}" height="54" fill="{theme["panel"]}"/>',
        f'<path d="M 1 54 H {width - 1}" class="rule"/>',
        f'<rect x="18" y="13" width="28" height="28" rx="3" fill="{theme["background"]}" stroke="{theme["accent"]}"/>',
        _text(24, 32, ">_", size=13, color="accent", weight=700),
        _text(58, 31, "PowerShell 7.5.2", size=15, color="primary", weight=600),
        f'<path d="M {width - 90} 1 V 55 M {width - 60} 1 V 55 M {width - 30} 1 V 55" class="rule"/>',
        f'<path d="M {width - 75} 27 h12 M {width - 47} 31 l5 -5 5 5 M {width - 20} 24 l8 8 M {width - 12} 24 l-8 8" fill="none" class="secondary" stroke="{theme["secondary"]}" stroke-width="1.5"/>',
    ]
    if timestamp and width >= 700:
        body.insert(5, _text(width - 305, 31, f"LAST SYNC / {timestamp}", size=11, color="secondary"))
    return body


def _terminal_separator(y: int, *, x1: int = 42, x2: int = 958) -> str:
    return f'<path d="M {x1} {y} H {x2}" class="rule"/>'


def _desktop(profile: dict[str, Any], theme: dict[str, str], now: dt.datetime) -> str:
    width, height = 1000, 900
    timestamp = now.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M %Z")
    body = _terminal_bar(width, theme, timestamp)
    body.extend(_prompt(42, 86, "Get-DeveloperProfile", command_x=285))
    body.extend([
        _text(42, 112, "Name", size=12, color="secondary", weight=600),
        _text(138, 112, ":", size=12, color="secondary"),
        _text(158, 112, profile["name"], size=15, color="primary", weight=600),
        _text(42, 134, "Role", size=12, color="secondary", weight=600),
        _text(138, 134, ":", size=12, color="secondary"),
        _text(158, 134, profile["role"], size=13, color="primary"),
        _text(42, 156, "Location", size=12, color="secondary", weight=600),
        _text(138, 156, ":", size=12, color="secondary"),
        _text(158, 156, profile["location"], size=13, color="primary"),
        _text(42, 178, "Status", size=12, color="secondary", weight=600),
        _text(138, 178, ":", size=12, color="secondary"),
        _text(158, 178, "[online]  profile snapshot", size=13, color="accent", weight=600),
        _terminal_separator(199),
    ])

    left_x, left_value_x = 42, 83
    right_x, right_value_x = 658, 760
    body.extend(_prompt(left_x, 225, "Get-SelectedWork", command_x=285))
    body.extend(_prompt(right_x, 225, "Get-Focus", command_x=746, path="PS>"))

    y = 256
    for index, work in enumerate(profile.get("selected_work", []), start=1):
        body.append(_text(left_x, y, f"[{index:02d}]", size=11, color="secondary", weight=600))
        body.append(_link(left_value_x, y, work["name"], work["href"], size=16))
        meta, meta_height = _wrapped(left_value_x, y + 20, f"STATUS : {work['status']}", 58, size=12, color="secondary", line_height=16)
        proof_text = work["proof"]
        if work["name"] == "MIRA":
            proof_text += "; 1,375-image test split not evaluated"
        proof, proof_height = _wrapped(left_value_x, y + 21 + meta_height, f"PROOF  : {proof_text}", 61, size=12, color="primary", line_height=16)
        body.extend([meta, proof])
        divider_y = y + 28 + meta_height + proof_height
        body.append(_terminal_separator(divider_y, x1=left_x, x2=610))
        y = divider_y + 25

    focus_y = 256
    for focus in profile.get("focus", []):
        body.append(_text(right_x, focus_y, f"{str(focus['label']).upper():<10}:", size=11, color="secondary", weight=600))
        focus_copy, focus_height = _wrapped(right_value_x, focus_y, focus["value"], 24, size=13, color="primary", line_height=18)
        body.append(focus_copy)
        focus_y += max(22, focus_height) + 18

    research = profile["current_research"]
    body.extend(_prompt(right_x, 548, "Get-CurrentResearch", command_x=746, path="PS>"))
    body.extend([
        _text(right_x, 577, "Project", size=11, color="secondary", weight=600),
        _text(746, 577, ":", size=11, color="secondary"),
        _link(762, 577, research["name"], research["href"], size=16),
        _text(right_x, 599, "Phase", size=11, color="secondary", weight=600),
        _text(746, 599, ":", size=11, color="secondary"),
        _text(762, 599, research["status"], size=12, color="secondary", weight=600),
    ])
    question, _ = _wrapped(right_x, 621, f"Question : {research['question']}", 36, size=12, color="primary", line_height=17)
    body.append(question)
    body.extend(_prompt(right_x, 702, "Get-Stack", command_x=746, path="PS>"))
    stack, _ = _wrapped(right_x, 729, f"Stack    : {profile['stack']}", 36, size=12, color="primary", line_height=17)
    body.append(stack)
    body.append(_terminal_separator(814))
    body.extend([
        _text(42, 840, "[online]", size=12, color="accent", weight=600),
        _text(122, 840, f"LAST SYNC / {timestamp}", size=12, color="secondary"),
    ])
    body.extend(_prompt(42, 875, "█", command_x=285))
    return _root(width, height, theme, f"{profile['name']} — profile", "PowerShell transcript profile with command prompts, proof-led project output, early Vulkan research, stack and Berlin sync time.", body)


def _mobile(profile: dict[str, Any], theme: dict[str, str], now: dt.datetime) -> str:
    width = 400
    x = 20
    timestamp = now.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M %Z")
    body = _terminal_bar(width, theme)
    body.extend(_prompt(x, 78, "Get-DeveloperProfile", command_x=170, path="PS C:\\Users\\Jeremy>", size=12))
    body.extend([
        _text(x, 101, "Name", size=11, color="secondary", weight=600),
        _text(100, 101, ":", size=11, color="secondary"),
        _text(119, 101, profile["name"], size=14, color="primary", weight=600),
        _text(x, 120, "Role", size=11, color="secondary", weight=600),
        _text(100, 120, ":", size=11, color="secondary"),
        _text(119, 120, profile["role"], size=12, color="primary"),
        _text(x, 139, "Location", size=11, color="secondary", weight=600),
        _text(100, 139, ":", size=11, color="secondary"),
        _text(119, 139, profile["location"], size=12, color="primary"),
        _text(x, 158, "Status", size=11, color="secondary", weight=600),
        _text(100, 158, ":", size=11, color="secondary"),
        _text(119, 158, "[online]", size=12, color="accent", weight=600),
        _terminal_separator(177, x1=x, x2=width - x),
    ])

    body.extend(_prompt(x, 201, "Get-Focus", command_x=66, path="PS>", size=12))
    focus_y = 224
    compact_focus = {
        "Primary": "ML systems / Computer Engineering",
        "Secondary": "Embedded / hardware-software integration",
        "Emerging": "GPU / Vulkan / PyTorch systems",
        "Supporting": "Computer Vision / Full-stack / AI Agents",
    }
    for focus in profile.get("focus", []):
        focus_copy, height = _wrapped(x, focus_y, f"{str(focus['label']).upper():<10} : {compact_focus.get(focus['label'], focus['value'])}", 53, size=12, color="primary", line_height=15)
        body.append(focus_copy)
        focus_y += height
    work_heading_y = focus_y + 7
    body.extend(_prompt(x, work_heading_y, "Get-SelectedWork", command_x=66, path="PS>", size=12))
    y = work_heading_y + 25
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
        body.append(_text(x, y, f"[{index:02d}]", size=10, color="secondary", weight=600))
        body.append(_link(x + 37, y, work["name"], work["href"], size=15))
        meta, meta_height = _wrapped(x + 37, y + 18, f"STATUS : {mobile_meta.get(work['name'], work['status'])}", 47, size=11, color="secondary", line_height=13)
        proof, proof_height = _wrapped(x + 37, y + 19 + meta_height, f"PROOF  : {mobile_evidence.get(work['name'], work['proof'])}", 47, size=12, color="primary", line_height=14)
        body.extend([meta, proof])
        divider_y = y + 20 + meta_height + proof_height
        body.append(_terminal_separator(divider_y, x1=x, x2=width - x))
        y = divider_y + 15

    research = profile["current_research"]
    body.extend(_prompt(x, y, "Get-CurrentResearch", command_x=66, path="PS>", size=12))
    body.extend([
        _link(x, y + 23, research["name"], research["href"], size=15),
        _text(111, y + 23, research["status"], size=11, color="secondary", weight=600),
    ])
    question, question_height = _wrapped(x, y + 43, f"QUESTION : {research['question']}", 48, size=12, color="primary", line_height=14)
    body.append(question)
    stack_y = y + 43 + question_height + 7
    body.extend(_prompt(x, stack_y, "Get-Stack", command_x=66, path="PS>", size=12))
    stack, stack_height = _wrapped(x, stack_y + 20, f"STACK : {profile['stack']}", 47, size=12, color="primary", line_height=14)
    body.extend([
        stack,
        _text(x, stack_y + 24 + stack_height, "[online]", size=11, color="accent", weight=600),
        _text(82, stack_y + 24 + stack_height, f"LAST SYNC / {timestamp}", size=11, color="secondary"),
    ])
    body.extend(_prompt(x, stack_y + 42 + stack_height, "█", command_x=66, path="PS>", size=12))
    height = stack_y + 54 + stack_height
    if height > 880:
        raise ValueError(f"mobile profile content exceeds 880 units ({height})")
    return _root(width, height, theme, f"{profile['name']} — profile", "Compact PowerShell transcript with command prompts, selected projects, early Vulkan research, stack and Berlin sync time.", body)


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

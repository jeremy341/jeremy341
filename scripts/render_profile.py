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

# All four files use the same monochrome PowerShell palette on GitHub light and dark pages.
THEMES = {
    "dark": {"background": "#000000", "panel": "#171717", "primary": "#FFFFFF", "secondary": "#B8B8B8", "rule": "#565656", "accent": "#FFFFFF"},
    "light": {"background": "#000000", "panel": "#171717", "primary": "#FFFFFF", "secondary": "#B8B8B8", "rule": "#565656", "accent": "#FFFFFF"},
}
FONT_STACK = "'Cascadia Code','JetBrains Mono',Consolas,monospace"
PROMPT = "PS C:\\Users\\Jeremy>"


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


def _property(x: int, y: int, label: str, value: object, *, value_x: int, max_chars: int, size: int = 13, line_height: int = 17, color: str = "primary") -> tuple[list[str], int]:
    label_text = _text(x, y, f"{label:<11} :", size=size, color="secondary")
    value_text, value_height = _wrapped(value_x, y, str(value), max_chars, size=size, color=color, line_height=line_height)
    return [label_text, value_text], max(line_height, value_height)


def _link(x: int, y: int, value: object, href: object, *, size: int = 17) -> str:
    return f'<a href="{_e(href)}">{_text(x, y, value, size=size, color="primary", weight=600)}</a>'


def _root(width: int, height: int, theme: dict[str, str], title: str, description: str, body: list[str]) -> str:
    style = (
        f'<style>text{{font-family:{FONT_STACK}}}.primary{{fill:{theme["primary"]}}}'
        f'.secondary{{fill:{theme["secondary"]}}}.accent{{fill:{theme["accent"]}}}'
        f'.rule{{stroke:{theme["rule"]}}}a text{{text-decoration:underline;text-decoration-color:{theme["secondary"]};text-underline-offset:2px}}</style>'
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
    path: str = PROMPT,
    size: int = 13,
) -> list[str]:
    """Render a prompt and command as two aligned terminal transcript cells."""
    return [
        _text(x, y, path, size=size, color="primary", weight=600),
        _text(command_x, y, command, size=size, color="primary", weight=600),
    ]


def _terminal_bar(width: int, theme: dict[str, str]) -> list[str]:
    """Windows Terminal title bar with an active PowerShell tab."""
    body = [
        f'<rect x="1" y="1" width="{width - 2}" height="48" fill="{theme["panel"]}"/>',
        f'<path d="M 1 48 H {width - 1}" class="rule"/>',
        f'<rect x="8" y="5" width="220" height="38" fill="{theme["background"]}"/>',
        _text(18, 29, ">_", size=12, color="primary", weight=700),
        _text(48, 29, "PowerShell 7.5.2", size=14, color="primary", weight=600),
        _text(244, 29, "+", size=17, color="primary", weight=400),
        _text(271, 28, "v", size=12, color="secondary", weight=600),
    ]
    if width >= 700:
        controls_x = width - 138
        body.extend([
            f'<path d="M {controls_x} 1 V 49 M {controls_x + 46} 1 V 49 M {controls_x + 92} 1 V 49" class="rule"/>',
            _text(controls_x + 18, 29, "—", size=14, color="secondary"),
            f'<rect x="{controls_x + 62}" y="16" width="11" height="11" fill="none" stroke="{theme["secondary"]}"/>',
            _text(controls_x + 107, 29, "×", size=14, color="secondary"),
        ])
    return body


def _desktop(profile: dict[str, Any], theme: dict[str, str], now: dt.datetime) -> str:
    width = 1000
    timestamp = now.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M %Z")
    body = _terminal_bar(width, theme)
    x, value_x = 32, 150
    y = 76
    body.extend(_prompt(x, y, "Get-DeveloperProfile | Format-List", command_x=190, size=13))
    y += 23
    profile_fields = (
        ("Name", profile["name"]),
        ("Role", profile["role"]),
        ("Location", profile["location"]),
        ("Status", "[online]"),
        ("LastSync", timestamp),
    )
    for label, value in profile_fields:
        lines, line_height = _property(x, y, label, value, value_x=value_x, max_chars=112, size=12, line_height=16)
        body.extend(lines)
        y += line_height + 1

    y += 8
    body.extend(_prompt(x, y, "Get-Focus | Format-List", command_x=190, size=13))
    y += 23
    for focus in profile.get("focus", []):
        lines, line_height = _property(x, y, focus["label"], focus["value"], value_x=value_x, max_chars=112, size=12, line_height=16)
        body.extend(lines)
        y += line_height + 1

    y += 8
    body.extend(_prompt(x, y, "Get-SelectedWork | Format-List", command_x=190, size=13))
    y += 23
    for work in profile.get("selected_work", []):
        body.append(_text(x, y, "Name       :", size=12, color="secondary"))
        body.append(_link(value_x, y, work["name"], work["href"], size=12))
        y += 17
        for label in ("area", "status", "proof"):
            value = work["area"] if label == "area" else work[label]
            if work["name"] == "MIRA" and label == "proof":
                value += "; independent 1,375-image test split not evaluated"
            if label == "proof":
                body.append(_text(x, y, "Proof      :", size=12, color="secondary"))
                proof, proof_height = _wrapped(value_x, y, value, 112, size=12, color="primary", line_height=16)
                body.append(proof)
                y += proof_height
            else:
                lines, line_height = _property(x, y, label.title(), value, value_x=value_x, max_chars=112, size=12, line_height=16)
                body.extend(lines)
                y += line_height
        y += 9

    y += 2
    research = profile["current_research"]
    body.extend(_prompt(x, y, "Get-CurrentResearch | Format-List", command_x=190, size=13))
    y += 23
    body.append(_text(x, y, "Project    :", size=12, color="secondary"))
    body.append(_link(value_x, y, research["name"], research["href"], size=12))
    y += 17
    for label, value in (("Phase", research["status"]), ("Question", research["question"])):
        lines, line_height = _property(x, y, label, value, value_x=value_x, max_chars=112, size=12, line_height=16)
        body.extend(lines)
        y += line_height

    y += 8
    body.extend(_prompt(x, y, "Get-Toolchain | Format-List", command_x=190, size=13))
    y += 23
    lines, line_height = _property(x, y, "Stack", profile["stack"], value_x=value_x, max_chars=112, size=12, line_height=16)
    body.extend(lines)
    y += line_height + 12
    body.extend(_prompt(x, y, "█", command_x=190, size=13))
    height = y + 32
    return _root(width, height, theme, f"{profile['name']} — PowerShell profile", "Monochrome Windows PowerShell transcript with developer profile, focus, selected project objects, TorchVK research and toolchain.", body)


def _mobile(profile: dict[str, Any], theme: dict[str, str], now: dt.datetime) -> str:
    width = 400
    x, value_x = 20, 100
    timestamp = now.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M %Z")
    body = _terminal_bar(width, theme)
    y = 72
    body.extend(_prompt(x, y, "Get-DeveloperProfile", command_x=154, size=11))
    y += 20
    profile_fields = (
        ("Name", profile["name"]),
        ("Role", profile["role"]),
        ("Location", profile["location"]),
        ("Status", "[online]"),
        ("LastSync", timestamp),
    )
    for label, value in profile_fields:
        lines, line_height = _property(x, y, label, value, value_x=value_x, max_chars=43, size=11, line_height=14)
        body.extend(lines)
        y += line_height

    compact_focus = {
        "Primary": "ML systems / Computer Engineering",
        "Secondary": "Embedded / hardware-software integration",
        "Emerging": "GPU compute / Vulkan / PyTorch systems",
        "Supporting": "Computer vision / Full-stack / AI Agents",
    }
    y += 8
    body.extend(_prompt(x, y, "Get-Focus", command_x=154, size=11))
    y += 20
    for focus in profile.get("focus", []):
        lines, line_height = _property(x, y, focus["label"], compact_focus.get(focus["label"], focus["value"]), value_x=value_x, max_chars=43, size=11, line_height=14)
        body.extend(lines)
        y += line_height

    y += 8
    body.extend(_prompt(x, y, "Get-SelectedWork", command_x=154, size=11))
    y += 20
    mobile_proof = {
        "MIRA": "415-image validation split: 90.6% mAP50; EXP-019 90.58%; independent 1,375-image test not evaluated",
        "Poorup": "Real-time multiplayer; reconnect recovery; server rules; CI",
        "FluidicStudio": "PyQt6 pumps; sensors; camera workflows; saved sessions",
        "ESP32-S3 Alarm Clock": "Custom PCB; C++ firmware; TFT; WebSerial; basic serial test only",
    }
    for work in profile.get("selected_work", []):
        body.append(_text(x, y, "Name       :", size=11, color="secondary"))
        body.append(_link(value_x, y, work["name"], work["href"], size=12))
        y += 15
        lines, line_height = _property(x, y, "Status", work["status"], value_x=value_x, max_chars=43, size=11, line_height=14)
        body.extend(lines)
        y += line_height
        lines, line_height = _property(x, y, "Proof", mobile_proof.get(work["name"], work["proof"]), value_x=value_x, max_chars=43, size=11, line_height=14)
        body.extend(lines)
        y += line_height + 8

    research = profile["current_research"]
    y += 3
    body.extend(_prompt(x, y, "Get-CurrentResearch", command_x=154, size=11))
    y += 20
    body.append(_text(x, y, "Project    :", size=11, color="secondary"))
    body.append(_link(value_x, y, research["name"], research["href"], size=12))
    y += 15
    for label, value in (("Phase", research["status"]), ("Question", research["question"])):
        lines, line_height = _property(x, y, label, value, value_x=value_x, max_chars=43, size=11, line_height=14)
        body.extend(lines)
        y += line_height

    y += 8
    body.extend(_prompt(x, y, "Get-Toolchain", command_x=154, size=11))
    y += 20
    lines, line_height = _property(x, y, "Stack", profile["stack"], value_x=value_x, max_chars=43, size=11, line_height=14)
    body.extend(lines)
    y += line_height + 12
    body.extend(_prompt(x, y, "█", command_x=154, size=11))
    height = y + 20
    if height > 880:
        raise ValueError(f"mobile profile content exceeds 880 units ({height})")
    return _root(width, height, theme, f"{profile['name']} — PowerShell profile", "Compact monochrome Windows PowerShell transcript with developer profile, focus, selected project objects, TorchVK research and toolchain.", body)


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

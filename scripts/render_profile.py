"""Render the profile's terminal card. Run locally or through GitHub Actions."""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import urllib.request
from pathlib import Path

USERNAME = "jeremy341"
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
API = "https://api.github.com"
HACKATIME_API = "https://hackatime.hackclub.com/api/v1/stats"


def request_json(url: str, token: str | None = None) -> dict | list:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "jeremy341-profile"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def github_stats(token: str | None) -> tuple[int, int, int | None]:
    user = request_json(f"{API}/users/{USERNAME}", token)
    repos = request_json(f"{API}/users/{USERNAME}/repos?type=owner&per_page=100", token)
    stars = sum(repo.get("stargazers_count", 0) for repo in repos)
    contributions = None
    if token:
        query = """
        query($login: String!) {
          user(login: $login) {
            contributionsCollection {
              contributionCalendar { totalContributions }
            }
          }
        }
        """
        payload = json.dumps({"query": query, "variables": {"login": USERNAME}}).encode()
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=payload,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "jeremy341-profile",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.load(response)
            contributions = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]
        except Exception:
            pass
    return user.get("public_repos", len(repos)), stars, contributions


def hackatime_stats(token: str | None) -> str:
    if not token:
        return ""
    try:
        data = request_json(f"{HACKATIME_API}?range=last_7_days", token)
        languages = data.get("data", {}).get("languages", [])
        top = languages[:3]
        if not top:
            return ""
        return "  |  ".join(f"{item['name']} {item.get('text', '')}" for item in top)
    except Exception:
        return ""


def age() -> str:
    value = os.getenv("PROFILE_BIRTH_DATE")
    if not value:
        return "private"
    birthday = dt.date.fromisoformat(value)
    today = dt.date.today()
    years = today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
    return f"{years} years"


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def make_svg(theme: dict[str, str], stats: tuple[int, int, int | None], hackatime: str) -> str:
    repos, stars, contributions = stats
    contribution_text = f"{contributions:,}" if contributions is not None else "syncing"
    rows = [
        ("OS", "NRW, Germany"),
        ("Uptime", age()),
        ("Role", "Student / embedded systems engineer in training"),
        ("Focus", "embedded systems, IoT, computer vision"),
        ("Now building", "MIRA — recycling-sorting edge AI"),
        ("Languages", "C++, Python, TypeScript, JavaScript"),
        ("Hardware", "ESP32, Arduino, KiCad, Fusion 360"),
        ("Tools", "PlatformIO, Git, FastAPI, Socket.IO"),
        ("GitHub", f"{repos} public repos  |  {stars} stars  |  {contribution_text} contributions"),
        ("Portfolio", "A+  |  MIRA  ·  NIMBL  ·  ESP32-S3 Alarm Clock"),
    ]
    if hackatime:
        rows.append(("Hackatime", hackatime))
    rows += [
        ("Status", "building in public"),
    ]
    text = []
    y = 108
    for index, (key, value) in enumerate(rows):
        if index in (5, 8):
            y += 14
            text.append(f'<line x1="42" y1="{y}" x2="1058" y2="{y}" stroke="{theme["line"]}" stroke-width="1"/>')
            y += 28
        dots = "." * max(2, 18 - len(key))
        text.append(
            f'<text x="42" y="{y}" class="key">{escape(key)}</text>'
            f'<text x="190" y="{y}" class="dots">{dots}</text>'
            f'<text x="340" y="{y}" class="value">{escape(value)}</text>'
        )
        y += 35
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="570" viewBox="0 0 1100 570" role="img" aria-label="Jeremy Darko portfolio terminal">
<style>
  .title {{ fill: {theme["title"]}; font: 700 24px 'JetBrains Mono', Consolas, monospace; }}
  .sub {{ fill: {theme["muted"]}; font: 15px 'JetBrains Mono', Consolas, monospace; }}
  .key {{ fill: {theme["key"]}; font: 600 16px 'JetBrains Mono', Consolas, monospace; }}
  .value {{ fill: {theme["value"]}; font: 16px 'JetBrains Mono', Consolas, monospace; }}
  .dots {{ fill: {theme["muted"]}; font: 16px 'JetBrains Mono', Consolas, monospace; }}
</style>
<rect width="1100" height="570" rx="18" fill="{theme["bg"]}"/>
<rect x="1" y="1" width="1098" height="568" rx="17" fill="none" stroke="{theme["border"]}"/>
<circle cx="42" cy="42" r="7" fill="{theme["red"]}"/><circle cx="66" cy="42" r="7" fill="{theme["yellow"]}"/><circle cx="90" cy="42" r="7" fill="{theme["green"]}"/>
<text x="550" y="48" text-anchor="middle" class="sub">jeremy@build-lab: ~</text>
<line x1="42" y1="70" x2="1058" y2="70" stroke="{theme["line"]}" stroke-width="1"/>
<text x="42" y="108" class="title">jeremy@portfolio</text>
<text x="42" y="134" class="sub">system status: online  ·  refreshed daily</text>
{''.join(text)}
<text x="42" y="540" class="sub">github.com/jeremy341</text>
</svg>"""


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    token = os.getenv("PROFILE_GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    stats = github_stats(token)
    hackatime = hackatime_stats(os.getenv("HACKATIME_API_KEY"))
    themes = {
        "profile-dark.svg": {"bg": "#0d1117", "border": "#30363d", "line": "#30363d", "title": "#e6edf3", "muted": "#7d8590", "key": "#58a6ff", "value": "#c9d1d9", "red": "#ff7b72", "yellow": "#d29922", "green": "#3fb950"},
        "profile-light.svg": {"bg": "#f6f8fa", "border": "#d0d7de", "line": "#d8dee4", "title": "#1f2328", "muted": "#57606a", "key": "#0969da", "value": "#24292f", "red": "#cf222e", "yellow": "#9a6700", "green": "#1a7f37"},
    }
    for filename, theme in themes.items():
        (ASSETS / filename).write_text(make_svg(theme, stats, hackatime), encoding="utf-8")


if __name__ == "__main__":
    main()

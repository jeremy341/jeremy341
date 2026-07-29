"""Generate Jeremy's GitHub profile system card and project tiles."""
# Generated SVG files are committed automatically by the refresh workflow.
from __future__ import annotations

import datetime as dt
import html
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

USERNAME = "jeremy341"
BIRTH_DATE = dt.date(2009, 8, 12)
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
GITHUB_API = "https://api.github.com"
GRAPHQL_API = "https://api.github.com/graphql"
HACKATIME_API = "https://hackatime.hackclub.com/api/v1/stats"

THEMES = {
    "dark": {
        "bg": "#050505", "panel": "#0b0b0b", "text": "#ffffff",
        "muted": "#a3a3a3", "line": "#303030", "accent": "#ffffff",
    },
    "light": {
        "bg": "#ffffff", "panel": "#fafafa", "text": "#080808",
        "muted": "#666666", "line": "#d4d4d4", "accent": "#080808",
    },
}


def request_json(
    url: str,
    token: str | None = None,
    *,
    data: dict[str, Any] | None = None,
    hackatime: bool = False,
) -> dict[str, Any] | list[dict[str, Any]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "jeremy341-profile",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if hackatime:
        headers["Accept"] = "application/json"
    encoded = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        encoded = json.dumps(data).encode("utf-8")
    request = urllib.request.Request(url, headers=headers, data=encoded)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def graphql(query: str, variables: dict[str, Any], token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        response = request_json(
            GRAPHQL_API,
            token,
            data={"query": query, "variables": variables},
        )
        if isinstance(response, dict) and not response.get("errors"):
            return response.get("data")
    except Exception:
        return None
    return None


def public_repositories(token: str | None) -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    page = 1
    while True:
        url = (
            f"{GITHUB_API}/users/{USERNAME}/repos"
            f"?type=owner&sort=updated&per_page=100&page={page}"
        )
        batch = request_json(url, token)
        if not isinstance(batch, list):
            break
        repositories.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repositories


def code_history(repositories: list[dict[str, Any]], token: str | None) -> tuple[int | None, int | None, int | None]:
    if not token:
        return None, None, None

    user_query = "query($login:String!){user(login:$login){id}}"
    user_data = graphql(user_query, {"login": USERNAME}, token)
    if not user_data or not user_data.get("user"):
        return None, None, None
    author_id = user_data["user"]["id"]

    history_query = """
    query($owner:String!,$name:String!,$author:ID!,$cursor:String){
      repository(owner:$owner,name:$name){
        defaultBranchRef{
          target{
            ... on Commit{
              history(first:100,after:$cursor,author:{id:$author}){
                nodes{additions deletions}
                pageInfo{hasNextPage endCursor}
              }
            }
          }
        }
      }
    }
    """

    commits = additions = deletions = 0
    for repository in repositories:
        owner = repository["owner"]["login"]
        name = repository["name"]
        cursor = None
        while True:
            data = graphql(
                history_query,
                {"owner": owner, "name": name, "author": author_id, "cursor": cursor},
                token,
            )
            try:
                history = data["repository"]["defaultBranchRef"]["target"]["history"]
            except (TypeError, KeyError):
                break
            for node in history["nodes"]:
                commits += 1
                additions += int(node.get("additions", 0))
                deletions += int(node.get("deletions", 0))
            page = history["pageInfo"]
            if not page["hasNextPage"]:
                break
            cursor = page["endCursor"]
    return commits, additions, deletions


def github_metrics(token: str | None) -> dict[str, str]:
    repositories = public_repositories(token)
    stars = sum(int(repo.get("stargazers_count", 0)) for repo in repositories)
    commits, additions, deletions = code_history(repositories, token)

    def number(value: int | None) -> str:
        return f"{value:,}" if value is not None else "sync pending"

    if additions is None or deletions is None:
        code = "sync pending"
    else:
        net = additions - deletions
        code = f"+{additions:,} / -{deletions:,} / {net:,} net"

    return {
        "repositories": str(len(repositories)),
        "stars": f"{stars:,}",
        "commits": number(commits),
        "code": code,
    }


def format_seconds(value: float | int) -> str:
    minutes = int(value) // 60
    hours, minutes = divmod(minutes, 60)
    return f"{hours:,}h {minutes:02d}m"


def hackatime_metrics(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    try:
        response = request_json(
            f"{HACKATIME_API}?range=all_time",
            token,
            hackatime=True,
        )
        if not isinstance(response, dict):
            return {}
        data = response.get("data", response)
        total = (
            data.get("human_readable_total")
            or data.get("human_readable_total_including_other_language")
            or (
                format_seconds(data["total_seconds"])
                if data.get("total_seconds") is not None
                else None
            )
        )
        languages = data.get("languages", [])[:3]
        projects = data.get("projects", [])[:3]
        result: dict[str, str] = {}
        if total:
            result["time"] = str(total)
        if languages:
            result["languages"] = " · ".join(
                f"{item.get('name', 'Unknown')} {item.get('text', '')}".strip()
                for item in languages
            )
        if projects:
            result["projects"] = " · ".join(
                f"{item.get('name', 'Unknown')} {item.get('text', '')}".strip()
                for item in projects
            )
        return result
    except Exception:
        return {}


def current_age() -> int:
    today = dt.date.today()
    return today.year - BIRTH_DATE.year - (
        (today.month, today.day) < (BIRTH_DATE.month, BIRTH_DATE.day)
    )


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def svg_text(x: int, y: int, value: object, css_class: str, anchor: str | None = None) -> str:
    anchor_attr = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{x}" y="{y}" class="{css_class}"{anchor_attr}>{esc(value)}</text>'


def render_system_card(theme: dict[str, str], github: dict[str, str], hackatime: dict[str, str]) -> str:
    synced = dt.datetime.now(dt.timezone.utc)
    revision = synced.strftime("%Y.%m.%d")
    last_sync = synced.strftime("%Y-%m-%d / %H:%M UTC")

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="640" viewBox="0 0 1000 640" role="img" aria-label="Jeremy Darko engineering system profile">',
        "<style>",
        f".hero{{fill:{theme['text']};font:700 26px 'JetBrains Mono',Consolas,monospace;letter-spacing:1.4px}}",
        f".meta{{fill:{theme['muted']};font:11px 'JetBrains Mono',Consolas,monospace;letter-spacing:1px}}",
        f".section{{fill:{theme['text']};font:700 12px 'JetBrains Mono',Consolas,monospace;letter-spacing:2px}}",
        f".label{{fill:{theme['muted']};font:11px 'JetBrains Mono',Consolas,monospace;letter-spacing:1px}}",
        f".value{{fill:{theme['text']};font:14px 'JetBrains Mono',Consolas,monospace}}",
        f".module{{fill:{theme['text']};font:700 20px 'JetBrains Mono',Consolas,monospace;letter-spacing:1px}}",
        f".status{{fill:{theme['bg']};font:700 10px 'JetBrains Mono',Consolas,monospace;letter-spacing:1.5px}}",
        "</style>",
        f'<rect width="1000" height="640" fill="{theme["bg"]}"/>',
        f'<rect x="1" y="1" width="998" height="638" rx="3" fill="none" stroke="{theme["line"]}"/>',
        f'<rect x="12" y="12" width="976" height="616" rx="2" fill="none" stroke="{theme["line"]}"/>',
        # Technical reference marks
        f'<path d="M12 34h14 M12 606h14 M974 34h14 M974 606h14 M36 12v14 M964 12v14 M36 614v14 M964 614v14" stroke="{theme["text"]}" stroke-width="1"/>',
        f'<circle cx="500" cy="12" r="3" fill="{theme["bg"]}" stroke="{theme["text"]}"/>',
        f'<circle cx="500" cy="628" r="3" fill="{theme["bg"]}" stroke="{theme["text"]}"/>',

        svg_text(36, 48, "JDK-001 / SYSTEM PROFILE", "hero"),
        svg_text(36, 72, "EMBEDDED SYSTEMS · SOFTWARE · APPLIED AI", "meta"),
        svg_text(672, 43, f"REV / {revision}", "meta"),
        svg_text(672, 65, f"SYNC / {last_sync}", "meta"),
        f'<rect x="895" y="31" width="67" height="28" fill="{theme["accent"]}"/>',
        svg_text(928, 50, "SYS.OK", "status", "middle"),
        f'<line x1="36" y1="96" x2="964" y2="96" stroke="{theme["line"]}"/>',
        f'<circle cx="36" cy="96" r="3" fill="{theme["text"]}"/>',
        f'<circle cx="964" cy="96" r="3" fill="{theme["text"]}"/>',

        svg_text(36, 127, "IDENTITY / 01", "section"),
        svg_text(524, 127, "DEVELOPMENT METRICS / 02", "section"),
        f'<line x1="500" y1="112" x2="500" y2="304" stroke="{theme["line"]}"/>',
    ]

    identity = [
        ("AGE", f"{current_age()} YRS"),
        ("LOCATION", "NRW / DE"),
        ("ROLE", "STUDENT · EMBEDDED SYSTEMS"),
        ("TARGET", "HARDWARE R&D"),
    ]
    metrics = [
        ("PUBLIC REPOSITORIES", github["repositories"]),
        ("TOTAL STARS", github["stars"]),
        ("AUTHORED COMMITS", github["commits"]),
        ("CODE DELTA", github["code"]),
    ]
    y = 165
    for label, value in identity:
        parts.extend([svg_text(36, y, label, "label"), svg_text(158, y, value, "value")])
        y += 42
    y = 165
    for label, value in metrics:
        parts.extend([svg_text(524, y, label, "label"), svg_text(716, y, value, "value")])
        y += 42

    parts.extend([
        f'<line x1="36" y1="320" x2="964" y2="320" stroke="{theme["line"]}"/>',
        svg_text(36, 350, "ACTIVE MODULE / 03", "section"),
        svg_text(36, 389, "MIRA", "module"),
        svg_text(36, 416, "MACHINE INTELLIGENCE FOR RECYCLING AUTOMATION", "meta"),
        svg_text(690, 370, "STATE", "label"),
        svg_text(790, 370, "IN DEVELOPMENT", "value"),
        svg_text(690, 400, "TARGET", "label"),
        svg_text(790, 400, "EDGE DEPLOYMENT", "value"),
        svg_text(690, 430, "CLASS", "label"),
        svg_text(790, 430, "COMPUTER VISION", "value"),

        f'<line x1="36" y1="454" x2="964" y2="454" stroke="{theme["line"]}"/>',
        svg_text(36, 484, "TOOLCHAIN / 04", "section"),
        svg_text(36, 516, "LANG", "label"),
        svg_text(112, 516, "C++ · C · PYTHON · TYPESCRIPT · JAVASCRIPT", "value"),
        svg_text(36, 546, "HW", "label"),
        svg_text(112, 546, "ESP32 · ARDUINO · I²C · SPI · CUSTOM PCB", "value"),
        svg_text(524, 516, "CAD", "label"),
        svg_text(600, 516, "KICAD · FUSION 360", "value"),
        svg_text(524, 546, "BUILD", "label"),
        svg_text(600, 546, "PLATFORMIO · GIT · FASTAPI", "value"),

        f'<line x1="36" y1="570" x2="964" y2="570" stroke="{theme["line"]}"/>',
        svg_text(36, 600, "ACTIVITY / 05", "section"),
    ])

    if hackatime:
        activity = "TOTAL " + hackatime.get("time", "—")
        languages = hackatime.get("languages", "")
        projects = hackatime.get("projects", "")
        parts.extend([
            svg_text(192, 600, activity[:30], "value"),
            svg_text(420, 600, languages[:42], "meta"),
            svg_text(964, 600, projects[:42], "meta", "end"),
        ])
    else:
        parts.extend([
            svg_text(192, 600, "GITHUB API / DAILY REFRESH", "value"),
            svg_text(964, 600, "HACKATIME / OPTIONAL", "meta", "end"),
        ])

    parts.extend([
        svg_text(36, 621, "REF JDK-PROFILE-001", "meta"),
        svg_text(964, 621, "DATA SCOPE / PUBLIC REPOSITORIES", "meta", "end"),
        "</svg>",
    ])
    return "".join(parts)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    github_token = os.getenv("PROFILE_GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    github = github_metrics(github_token)
    hackatime = hackatime_metrics(os.getenv("HACKATIME_API_KEY"))

    for theme_name, theme in THEMES.items():
        (ASSETS / f"profile-{theme_name}.svg").write_text(
            render_system_card(theme, github, hackatime),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()

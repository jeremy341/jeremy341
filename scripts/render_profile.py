"""Generate Jeremy's GitHub profile system card and project tiles."""
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

PROJECTS = [
    ("01", "MIRA", "Edge-AI recycling automation", "MIRA-AI"),
    ("02", "NIMBL", "Token-efficient AI coding companion", "NIMBL"),
    ("03", "ESP32-S3 ALARM CLOCK", "Custom PCB, firmware and enclosure", "esp32-alarm-clock"),
    ("04", "POORUP", "Real-time multiplayer board game", "Poorup"),
]

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
    left_rows = [
        ("AGE", f"{current_age()} years"),
        ("LOCATION", "NRW, Germany"),
        ("ROLE", "Student · embedded systems"),
        ("FOCUS", "Hardware · firmware · applied AI"),
        ("BUILDING", "MIRA"),
    ]
    right_rows = [
        ("PUBLIC REPOSITORIES", github["repositories"]),
        ("TOTAL STARS", github["stars"]),
        ("TOTAL COMMITS", github["commits"]),
        ("CODE CHANGES", github["code"]),
    ]
    if hackatime.get("time"):
        right_rows.append(("HACKATIME TOTAL", hackatime["time"]))

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="540" viewBox="0 0 1000 540" role="img" aria-label="Jeremy Darko system profile">',
        "<style>",
        f".title{{fill:{theme['text']};font:700 28px 'JetBrains Mono',Consolas,monospace;letter-spacing:1px}}",
        f".subtitle{{fill:{theme['muted']};font:14px 'JetBrains Mono',Consolas,monospace}}",
        f".section{{fill:{theme['text']};font:700 13px 'JetBrains Mono',Consolas,monospace;letter-spacing:2px}}",
        f".label{{fill:{theme['muted']};font:12px 'JetBrains Mono',Consolas,monospace;letter-spacing:1px}}",
        f".value{{fill:{theme['text']};font:15px 'JetBrains Mono',Consolas,monospace}}",
        f".status{{fill:{theme['bg']};font:700 11px 'JetBrains Mono',Consolas,monospace;letter-spacing:1px}}",
        "</style>",
        f'<rect width="1000" height="540" rx="16" fill="{theme["bg"]}"/>',
        f'<rect x="1" y="1" width="998" height="538" rx="15" fill="none" stroke="{theme["line"]}"/>',
        svg_text(38, 52, "JEREMY DARKO", "title"),
        svg_text(38, 77, "SYSTEM PROFILE / EMBEDDED · SOFTWARE · AI", "subtitle"),
        f'<rect x="872" y="31" width="90" height="28" rx="14" fill="{theme["accent"]}"/>',
        svg_text(917, 50, "ONLINE", "status", "middle"),
        f'<line x1="38" y1="102" x2="962" y2="102" stroke="{theme["line"]}"/>',
        svg_text(38, 135, "IDENTITY", "section"),
        svg_text(520, 135, "LIVE METRICS", "section"),
        f'<line x1="482" y1="122" x2="482" y2="365" stroke="{theme["line"]}"/>',
    ]

    y = 172
    for label, value in left_rows:
        parts.extend([
            svg_text(38, y, label, "label"),
            svg_text(165, y, value, "value"),
        ])
        y += 43

    y = 172
    for label, value in right_rows:
        parts.extend([
            svg_text(520, y, label, "label"),
            svg_text(710, y, value, "value"),
        ])
        y += 43

    parts.extend([
        f'<line x1="38" y1="382" x2="962" y2="382" stroke="{theme["line"]}"/>',
        svg_text(38, 413, "STACK", "section"),
        svg_text(38, 443, "C++ · C · Python · TypeScript · JavaScript", "value"),
        svg_text(520, 413, "HARDWARE + TOOLS", "section"),
        svg_text(520, 443, "ESP32 · KiCad · PlatformIO · Fusion 360", "value"),
        f'<line x1="38" y1="466" x2="962" y2="466" stroke="{theme["line"]}"/>',
    ])

    if hackatime:
        parts.extend([
            svg_text(38, 495, "HACKATIME / ALL TIME", "section"),
            svg_text(38, 522, hackatime.get("languages", "Languages unavailable")[:55], "subtitle"),
            svg_text(520, 522, hackatime.get("projects", "Projects unavailable")[:55], "subtitle"),
        ])
    else:
        parts.extend([
            svg_text(38, 497, "SELECTED PROJECTS", "section"),
            svg_text(38, 522, "Open a project card below to view its repository.", "subtitle"),
        ])

    parts.append("</svg>")
    return "".join(parts)


def render_project_card(theme: dict[str, str], index: str, title: str, description: str) -> str:
    return "".join([
        '<svg xmlns="http://www.w3.org/2000/svg" width="485" height="112" viewBox="0 0 485 112" role="img">',
        "<style>",
        f".index{{fill:{theme['muted']};font:12px 'JetBrains Mono',Consolas,monospace;letter-spacing:1px}}",
        f".title{{fill:{theme['text']};font:700 17px 'JetBrains Mono',Consolas,monospace}}",
        f".desc{{fill:{theme['muted']};font:12px 'JetBrains Mono',Consolas,monospace}}",
        f".open{{fill:{theme['text']};font:700 11px 'JetBrains Mono',Consolas,monospace;letter-spacing:1px}}",
        "</style>",
        f'<rect width="485" height="112" rx="12" fill="{theme["panel"]}"/>',
        f'<rect x="1" y="1" width="483" height="110" rx="11" fill="none" stroke="{theme["line"]}"/>',
        svg_text(24, 28, index, "index"),
        svg_text(24, 55, title, "title"),
        svg_text(24, 78, description, "desc"),
        svg_text(461, 94, "OPEN REPOSITORY →", "open", "end"),
        "</svg>",
    ])


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
        for index, title, description, repository in PROJECTS:
            slug = repository.lower()
            (ASSETS / f"project-{slug}-{theme_name}.svg").write_text(
                render_project_card(theme, index, title, description),
                encoding="utf-8",
            )


if __name__ == "__main__":
    main()

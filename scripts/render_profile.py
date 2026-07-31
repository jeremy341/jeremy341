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
from zoneinfo import ZoneInfo
from typing import Any

USERNAME = "jeremy341"
BIRTH_DATE = dt.date(2009, 8, 12)
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
GITHUB_API = "https://api.github.com"
GRAPHQL_API = "https://api.github.com/graphql"
HACKATIME_API = "https://hackatime.hackclub.com/api/v1/authenticated"

THEMES = {
    "dark": {
        "bg": "#0c0c0c", "panel": "#181818", "text": "#f5f5f5",
        "muted": "#9b9b9b", "line": "#333333", "accent": "#f5f5f5",
    },
    "light": {
        "bg": "#0c0c0c", "panel": "#181818", "text": "#f5f5f5",
        "muted": "#9b9b9b", "line": "#333333", "accent": "#f5f5f5",
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

    today = dt.date.today()
    start_date = BIRTH_DATE.isoformat()
    end_date = today.isoformat()
    endpoints = {
        # This is the same all-time total used by the official Hackatime/WakaTime-compatible view.
        "all_time": "https://hackatime.hackclub.com/api/v1/users/current/all_time_since_today",
        "hours": f"{HACKATIME_API}/hours?{urllib.parse.urlencode({'start_date': start_date, 'end_date': end_date})}",
        "streak": f"{HACKATIME_API}/streak",
        "projects": f"{HACKATIME_API}/projects?include_archived=false",
    }

    responses: dict[str, dict[str, Any]] = {}
    for name, url in endpoints.items():
        try:
            response = request_json(url, token, hackatime=True)
            if isinstance(response, dict):
                # Some deployments wrap OAuth responses in a data object.
                payload = response.get("data") if isinstance(response.get("data"), dict) else response
                responses[name] = payload
        except Exception:
            continue

    result: dict[str, str] = {}
    # The dashboard uses the authenticated date-range total. Prefer it so the card matches the official UI.
    total_seconds = responses.get("hours", {}).get("total_seconds")
    if total_seconds is None:
        all_time = responses.get("all_time", {})
        grand_total = all_time.get("grand_total", {}) if isinstance(all_time, dict) else {}
        total_seconds = grand_total.get("total_seconds") or all_time.get("total_seconds")
    if total_seconds is not None:
        result["time"] = format_seconds(total_seconds)

    streak_days = responses.get("streak", {}).get("streak_days")
    if streak_days is not None:
        days = int(streak_days)
        result["streak"] = f"{days} day{'s' if days != 1 else ''}"

    projects_payload = responses.get("projects", {})
    projects = projects_payload.get("projects", []) if isinstance(projects_payload, dict) else projects_payload
    if isinstance(projects, list):
        ranked = sorted(
            (project for project in projects if isinstance(project, dict)),
            key=lambda project: float(project.get("total_seconds", 0)),
            reverse=True,
        )[:3]
        if ranked:
            result["projects"] = " · ".join(
                f"{project.get('name', 'Unknown')} {format_seconds(project.get('total_seconds', 0))}"
                for project in ranked
            )

    return result


def current_age_parts() -> tuple[int, int, int]:
    """Return precise age as completed years, months, and days."""
    today = dt.date.today()
    years = today.year - BIRTH_DATE.year
    if (today.month, today.day) < (BIRTH_DATE.month, BIRTH_DATE.day):
        years -= 1

    anchor = BIRTH_DATE.replace(year=BIRTH_DATE.year + years)
    months = (today.year - anchor.year) * 12 + today.month - anchor.month
    if today.day < anchor.day:
        months -= 1

    month_index = anchor.month - 1 + months
    anchor_month = month_index % 12 + 1
    anchor_year = anchor.year + month_index // 12
    anchor_after_months = anchor.replace(year=anchor_year, month=anchor_month)
    days = (today - anchor_after_months).days
    return years, months, days


def format_age() -> str:
    years, months, days = current_age_parts()
    return f"{years} years {months} months {days} days"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def svg_text(x: int, y: int, value: object, css_class: str, anchor: str | None = None) -> str:
    anchor_attr = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{x}" y="{y}" class="{css_class}"{anchor_attr}>{esc(value)}</text>'


def render_system_card(theme: dict[str, str], github: dict[str, str], hackatime: dict[str, str]) -> str:
    synced = dt.datetime.now(ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d %H:%M %Z")
    added, removed, net = "—", "—", "—"
    if github["code"] != "sync pending":
        try:
            chunks = github["code"].replace(" net", "").split(" / ")
            added, removed, net = chunks
        except ValueError:
            pass

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="780" viewBox="0 0 1000 780" role="img" aria-label="Jeremy Darko PowerShell developer profile">',
        "<style>",
        f".chrome{{fill:{theme['text']};font:12px 'Cascadia Code','JetBrains Mono',Consolas,monospace}}",
        f".chrome-muted{{fill:{theme['muted']};font:11px 'Cascadia Code','JetBrains Mono',Consolas,monospace}}",
        f".prompt{{fill:{theme['text']};font:700 14px 'Cascadia Code','JetBrains Mono',Consolas,monospace}}",
        f".command{{fill:{theme['text']};font:14px 'Cascadia Code','JetBrains Mono',Consolas,monospace}}",
        f".label{{fill:{theme['muted']};font:13px 'Cascadia Code','JetBrains Mono',Consolas,monospace}}",
        f".value{{fill:{theme['text']};font:13px 'Cascadia Code','JetBrains Mono',Consolas,monospace}}",
        f".table-head{{fill:{theme['muted']};font:11px 'Cascadia Code','JetBrains Mono',Consolas,monospace;letter-spacing:.5px}}",
        f".table-value{{fill:{theme['text']};font:13px 'Cascadia Code','JetBrains Mono',Consolas,monospace}}",
        "</style>",
        f'<rect width="1000" height="780" rx="9" fill="{theme["bg"]}"/>',
        f'<rect x="1" y="1" width="998" height="778" rx="8" fill="none" stroke="{theme["line"]}"/>',

        # Windows Terminal title bar
        f'<path d="M9 0h982a9 9 0 0 1 9 9v43H0V9a9 9 0 0 1 9-9z" fill="{theme["panel"]}"/>',
        f'<rect x="12" y="9" width="272" height="43" rx="6" fill="{theme["bg"]}"/>',
        f'<rect x="24" y="20" width="22" height="22" rx="3" fill="{theme["text"]}"/>',
        f'<text x="35" y="36" text-anchor="middle" style="fill:{theme["bg"]};font:700 11px Cascadia Code,monospace">&gt;_</text>',
        svg_text(58, 36, "PowerShell 7.5.2", "chrome"),
        svg_text(301, 35, "+", "chrome"),
        svg_text(332, 35, "⌄", "chrome-muted"),
        svg_text(830, 34, f"LAST SYNC / {synced}", "chrome-muted", "end"),
        f'<rect x="844" y="0" width="52" height="52" fill="transparent"/>',
        f'<rect x="896" y="0" width="52" height="52" fill="transparent"/>',
        f'<rect x="948" y="0" width="52" height="52" fill="transparent"/>',
        svg_text(870, 32, "—", "chrome", "middle"),
        svg_text(922, 32, "□", "chrome", "middle"),
        svg_text(974, 32, "×", "chrome", "middle"),
        f'<line x1="0" y1="52" x2="1000" y2="52" stroke="{theme["line"]}"/>',

        # Command 1
        svg_text(30, 86, "PS C:\\Users\\Jeremy>", "prompt"),
        svg_text(205, 86, "Get-DeveloperProfile", "command"),
        svg_text(30, 116, "Name", "label"), svg_text(126, 116, ":", "label"), svg_text(150, 116, "Jeremy Darko", "value"),
        svg_text(30, 142, "Age", "label"), svg_text(126, 142, ":", "label"), svg_text(150, 142, format_age(), "value"),
        svg_text(30, 168, "Location", "label"), svg_text(126, 168, ":", "label"), svg_text(150, 168, "NRW, Germany", "value"),
        svg_text(30, 194, "Role", "label"), svg_text(126, 194, ":", "label"), svg_text(150, 194, "Student / Embedded Systems", "value"),
        svg_text(30, 220, "Focus", "label"), svg_text(126, 220, ":", "label"), svg_text(150, 220, "Hardware, Firmware, Applied AI", "value"),

        # Command 2
        svg_text(30, 260, "PS C:\\Users\\Jeremy>", "prompt"),
        svg_text(205, 260, "Get-GitHubMetrics | Format-Table", "command"),
        svg_text(30, 291, "Repositories", "table-head"),
        svg_text(170, 291, "Stars", "table-head"),
        svg_text(260, 291, "Commits", "table-head"),
        svg_text(370, 291, "Added", "table-head"),
        svg_text(520, 291, "Removed", "table-head"),
        svg_text(675, 291, "Net", "table-head"),
        svg_text(30, 309, "------------", "label"),
        svg_text(170, 309, "-----", "label"),
        svg_text(260, 309, "-------", "label"),
        svg_text(370, 309, "-------------", "label"),
        svg_text(520, 309, "-------------", "label"),
        svg_text(675, 309, "-------------", "label"),
        svg_text(30, 333, github["repositories"], "table-value"),
        svg_text(170, 333, github["stars"], "table-value"),
        svg_text(260, 333, github["commits"], "table-value"),
        svg_text(370, 333, added, "table-value"),
        svg_text(520, 333, removed, "table-value"),
        svg_text(675, 333, net, "table-value"),

        # Command 3
        svg_text(30, 376, "PS C:\\Users\\Jeremy>", "prompt"),
        svg_text(205, 376, "Get-CurrentProject", "command"),
        svg_text(30, 406, "Name", "label"), svg_text(126, 406, ":", "label"), svg_text(150, 406, "MIRA", "value"),
        svg_text(30, 432, "Type", "label"), svg_text(126, 432, ":", "label"), svg_text(150, 432, "Edge-AI Recycling Automation", "value"),
        svg_text(30, 458, "State", "label"), svg_text(126, 458, ":", "label"), svg_text(150, 458, "In Development", "value"),
        svg_text(30, 484, "Target", "label"), svg_text(126, 484, ":", "label"), svg_text(150, 484, "Resource-Constrained Edge Hardware", "value"),

        # Command 4
        svg_text(30, 524, "PS C:\\Users\\Jeremy>", "prompt"),
        svg_text(205, 524, "Get-Toolchain", "command"),
        svg_text(30, 554, "Languages", "label"), svg_text(126, 554, ":", "label"), svg_text(150, 554, "C++, C, Python, TypeScript, JavaScript", "value"),
        svg_text(30, 580, "Hardware", "label"), svg_text(126, 580, ":", "label"), svg_text(150, 580, "ESP32, Arduino, I2C, SPI, Custom PCBs", "value"),
        svg_text(30, 606, "Tools", "label"), svg_text(126, 606, ":", "label"), svg_text(150, 606, "KiCad, PlatformIO, Fusion 360, Git", "value"),
    ]

    cursor_y = 660
    if hackatime:
        parts.extend([
            svg_text(30, 646, "PS C:\\Users\\Jeremy>", "prompt"),
            svg_text(205, 646, "Get-HackatimeSummary -Range AllTime | Format-Table", "command"),
            svg_text(30, 674, "Total Coding", "table-head"),
            svg_text(210, 674, "Current Streak", "table-head"),
            svg_text(390, 674, "Top Projects", "table-head"),
            svg_text(30, 690, "----------------", "label"),
            svg_text(210, 690, "----------------", "label"),
            svg_text(390, 690, "----------------------------------------------------------", "label"),
            svg_text(30, 712, hackatime.get("time", "—"), "table-value"),
            svg_text(210, 712, hackatime.get("streak", "—"), "table-value"),
            svg_text(390, 712, hackatime.get("projects", "")[:62], "table-value"),
            svg_text(30, 754, "PS C:\\Users\\Jeremy>", "prompt"),
            f'<rect x="205" y="740" width="9" height="18" fill="{theme["text"]}"><animate attributeName="opacity" values="1;1;0;0;1" dur="1.2s" repeatCount="indefinite"/></rect>',
        ])
    else:
        parts.extend([
            svg_text(30, cursor_y, "PS C:\\Users\\Jeremy>", "prompt"),
            f'<rect x="205" y="{cursor_y - 14}" width="9" height="18" fill="{theme["text"]}"><animate attributeName="opacity" values="1;1;0;0;1" dur="1.2s" repeatCount="indefinite"/></rect>',
        ])

    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    github_token = os.getenv("PROFILE_GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    github = github_metrics(github_token)
    hackatime_token = os.getenv("HACKATIME_ACCESS_TOKEN") or os.getenv("HACKATIME_API_KEY")
    hackatime = hackatime_metrics(hackatime_token)

    for theme_name, theme in THEMES.items():
        (ASSETS / f"profile-{theme_name}.svg").write_text(
            render_system_card(theme, github, hackatime),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()

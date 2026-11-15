#!/usr/bin/env python3
"""Render GitHub stats + top-languages cards (dark and light) as SVG.

Self-hosted replacement for the public readme-stats services, which are
frequently paused or rate-limited. Runs in GitHub Actions with GITHUB_TOKEN
and writes into dist/.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from html import escape
from pathlib import Path

USER = os.environ.get("GH_USER") or sys.argv[1]
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = Path(os.environ.get("OUT_DIR", "dist"))

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar { totalContributions }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

THEMES = {
    "dark": {"bg": "#0d1117", "border": "#30363d", "title": "#58a6ff",
             "text": "#c9d1d9", "muted": "#8b949e", "icon": "#06b6d4"},
    "light": {"bg": "#ffffff", "border": "#d0d7de", "title": "#0969da",
              "text": "#24292f", "muted": "#57606a", "icon": "#0891b2"},
}
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"


def fetch() -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    return data["data"]["user"]


def stats_card(u: dict, t: dict) -> str:
    cc = u["contributionsCollection"]
    repos = u["repositories"]
    rows = [
        ("Total contributions (year)", cc["contributionCalendar"]["totalContributions"]
         + cc["restrictedContributionsCount"]),
        ("Commits (year)", cc["totalCommitContributions"] + cc["restrictedContributionsCount"]),
        ("Pull requests", u["pullRequests"]["totalCount"]),
        ("Public repositories", repos["totalCount"]),
        ("Stars earned", sum(r["stargazerCount"] for r in repos["nodes"])),
    ]
    body = ""
    for i, (label, value) in enumerate(rows):
        y = 70 + i * 26
        body += (f'<circle cx="32" cy="{y - 5}" r="4" fill="{t["icon"]}"/>'
                 f'<text x="46" y="{y}" fill="{t["text"]}" font-size="14">{escape(label)}</text>'
                 f'<text x="455" y="{y}" fill="{t["text"]}" font-size="14" font-weight="700" '
                 f'text-anchor="end">{value:,}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="210" viewBox="0 0 480 210" '
            f'font-family="{FONT}"><rect x="0.5" y="0.5" width="479" height="209" rx="10" '
            f'fill="{t["bg"]}" stroke="{t["border"]}"/>'
            f'<text x="25" y="36" fill="{t["title"]}" font-size="17" font-weight="700">'
            f'{escape(u["name"] or USER)}\'s GitHub stats</text>{body}</svg>')


def langs_card(u: dict, t: dict, top: int = 6) -> str:
    # Each repo gets an equal vote, split by its own language mix. Raw byte
    # totals let one notebook-heavy repo drown everything else, and notebooks
    # are Python code, so Jupyter Notebook is counted as Python.
    merge = {"Jupyter Notebook": ("Python", "#3572A5")}
    # Platform boilerplate that Flutter and web projects generate, not code I write.
    skip = {"HTML", "CSS", "Shell", "Dockerfile", "Makefile", "Batchfile", "CMake",
            "Swift", "Kotlin", "Objective-C", "C++", "C"}
    sizes: dict[str, list] = {}
    for repo in u["repositories"]["nodes"]:
        edges = [e for e in repo["languages"]["edges"] if e["node"]["name"] not in skip]
        repo_total = sum(e["size"] for e in edges)
        for e in edges:
            name, color = merge.get(e["node"]["name"], (e["node"]["name"], e["node"]["color"]))
            entry = sizes.setdefault(name, [0.0, color or "#8b949e"])
            entry[0] += e["size"] / repo_total
    ranked = sorted(sizes.items(), key=lambda kv: kv[1][0], reverse=True)[:top]
    total = sum(v[0] for _, v in ranked) or 1
    bar, x = "", 25.0
    for _, (size, color) in ranked:
        w = 430 * size / total
        bar += f'<rect x="{x:.2f}" y="56" width="{w:.2f}" height="10" fill="{color}"/>'
        x += w
    legend = ""
    for i, (name, (size, color)) in enumerate(ranked):
        col, row = i % 2, i // 2
        lx, ly = 25 + col * 220, 100 + row * 30
        legend += (f'<circle cx="{lx + 6}" cy="{ly - 5}" r="6" fill="{color}"/>'
                   f'<text x="{lx + 20}" y="{ly}" fill="{t["text"]}" font-size="14">{escape(name)} '
                   f'<tspan fill="{t["muted"]}">{100 * size / total:.1f}%</tspan></text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="210" viewBox="0 0 480 210" '
            f'font-family="{FONT}"><rect x="0.5" y="0.5" width="479" height="209" rx="10" '
            f'fill="{t["bg"]}" stroke="{t["border"]}"/>'
            f'<text x="25" y="36" fill="{t["title"]}" font-size="17" font-weight="700">Most used languages</text>'
            f'<clipPath id="bar"><rect x="25" y="56" width="430" height="10" rx="5"/></clipPath>'
            f'<g clip-path="url(#bar)">{bar}</g>{legend}</svg>')


def main() -> None:
    u = fetch()
    OUT.mkdir(parents=True, exist_ok=True)
    for theme, t in THEMES.items():
        (OUT / f"stats-{theme}.svg").write_text(stats_card(u, t), encoding="utf-8")
        (OUT / f"langs-{theme}.svg").write_text(langs_card(u, t), encoding="utf-8")
    print("wrote", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()

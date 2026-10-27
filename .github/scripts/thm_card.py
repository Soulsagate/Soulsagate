"""Draw a TryHackMe stats card (SVG) for the profile README from THM's public profile.

    python3 .github/scripts/thm_card.py S0uls dist/thm-card.svg

Run by .github/workflows/thm-card.yml once a day. If THM can't be reached or the numbers are
missing, it exits non-zero without writing anything, so the last good card stays up.
"""

from __future__ import annotations

import datetime
import html
import json
import sys
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; Soulsagate-profile-card; +https://github.com/Soulsagate)"
ENDPOINTS = [
    "https://tryhackme.com/api/v2/public-profile?username={user}",
]


def fetch(url: str, tries: int = 3):
    """GET JSON, waiting and retrying when THM answers 429 (it rate-limits shared CI IPs)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == tries - 1:
                raise
            wait = min(int(exc.headers.get("Retry-After") or 0) or 15 * (attempt + 1), 60)
            print(f"429 from {url}, retrying in {wait}s")
            time.sleep(wait)


def shape(obj, depth=0) -> list[str]:
    """Field names and value types, for the log (no values beyond short scalars)."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                out.append("  " * depth + f"{k}: {type(v).__name__}")
                if depth < 2:
                    out += shape(v if isinstance(v, dict) else (v[0] if v else {}), depth + 1)
            else:
                out.append("  " * depth + f"{k}: {v!r}"[:120])
    return out


def pick(data: dict, *names):
    for n in names:
        if data.get(n) not in (None, ""):
            return data[n]
    return None


def profile(user: str) -> dict:
    errors = []
    for url in ENDPOINTS:
        url = url.format(user=user)
        try:
            raw = fetch(url)
        except Exception as exc:  # noqa: BLE001 - log every failure and try the next endpoint
            errors.append(f"{url}: {exc}")
            continue
        print(f"--- {url}\n" + "\n".join(shape(raw)))
        data = raw.get("data", raw) if isinstance(raw, dict) else {}
        stats = {
            "level": pick(data, "level"),
            "rank": pick(data, "rank", "userRank", "globalRank"),
            "top": pick(data, "topPercentage", "top_percentage", "topPercent"),
            "rooms": pick(data, "completedRoomsNumber", "completedRooms", "roomsCompleted"),
            "badges": pick(data, "badgesNumber", "badges", "badgeCount"),
            "streak": pick(data, "streak"),
            "points": pick(data, "totalPoints", "points"),
        }
        print("parsed:", stats)
        if stats["rank"] is not None and stats["rooms"] is not None:
            return stats
        errors.append(f"{url}: rank/rooms missing")
    # Older public endpoints, one number each
    try:
        stats = {"level": None, "top": None, "streak": None, "points": None,
                 "rank": fetch(f"https://tryhackme.com/api/user/rank/{user}").get("userRank"),
                 "rooms": fetch(f"https://tryhackme.com/api/no-completed-rooms-public/{user}"),
                 "badges": len(fetch(f"https://tryhackme.com/api/badges/get/{user}") or [])}
        print("legacy:", stats)
        if stats["rank"] is not None and stats["rooms"] is not None:
            return stats
        errors.append("legacy endpoints: rank/rooms missing")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"legacy endpoints: {exc}")
    raise SystemExit("no usable TryHackMe profile data:\n  " + "\n  ".join(errors))


def card(user: str, s: dict) -> str:
    gold, fg, muted, bg, line = "#c8a24a", "#e6e8eb", "#9aa3ad", "#0d0f13", "#262a33"
    level = s["level"]
    level_txt = f"[0x{int(level):X}]" if isinstance(level, (int, float)) or str(level).isdigit() else str(level or "")
    top = s["top"]
    rows = [
        ("Global rank", f"#{int(s['rank']):,}" if str(s["rank"]).isdigit() else str(s["rank"])),
        ("Top", f"{top}%" if top is not None else "-"),
        ("Rooms completed", f"{s['rooms']}"),
        ("Badges", f"{s['badges']}" if s["badges"] is not None else "-"),
        ("Day streak", f"{s['streak']}" if s["streak"] is not None else "-"),
    ]
    y0, step = 82, 22
    lines = "".join(
        f'<text x="25" y="{y0 + i * step}" class="k">{html.escape(k)}</text>'
        f'<text x="290" y="{y0 + i * step}" class="v" text-anchor="end">{html.escape(v)}</text>'
        for i, (k, v) in enumerate(rows))
    today = datetime.date.today().isoformat()
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200" viewBox="0 0 320 200" role="img"
 aria-label="TryHackMe stats for {html.escape(user)}">
<style>
.t{{font:600 17px 'Segoe UI',Ubuntu,'Helvetica Neue',sans-serif;fill:{gold}}}
.l{{font:600 12px 'Segoe UI',Ubuntu,sans-serif;fill:{fg}}}
.k{{font:400 13px 'Segoe UI',Ubuntu,sans-serif;fill:{muted}}}
.v{{font:700 13px 'Segoe UI',Ubuntu,sans-serif;fill:{fg}}}
.u{{font:400 10px 'Segoe UI',Ubuntu,sans-serif;fill:{muted}}}
</style>
<rect width="320" height="200" rx="6" fill="{bg}"/>
<text x="25" y="35" class="t">TryHackMe · {html.escape(user)}</text>
<text x="25" y="54" class="l">Level {html.escape(level_txt)}</text>
<line x1="25" y1="64" x2="295" y2="64" stroke="{line}"/>
{lines}
<text x="295" y="190" class="u" text-anchor="end">updated {today}</text>
</svg>
"""


if __name__ == "__main__":
    user, out = sys.argv[1], sys.argv[2]
    svg = card(user, profile(user))
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print("wrote", out)

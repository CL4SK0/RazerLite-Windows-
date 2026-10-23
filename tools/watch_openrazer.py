"""Surveille OpenRazer : signale par une fiche (issue) les modifications qui touchent nos appareils.

Lancé chaque semaine par .github/workflows/openrazer-watch.yml. Rien n'est recopié automatiquement :
la fiche sert à adapter la correction dans RazerLite.
"""

import datetime as dt
import json
import os
import re
import urllib.request

UPSTREAM = "openrazer/openrazer"
DEVICES = re.compile(r"basilisk[ _-]?v3[ _-]?pro|deathstalker[ _-]?v2[ _-]?pro|kraken[ _-]?v3[ _-]?hyper", re.I)
API = "https://api.github.com"


def api(path, data=None):
    req = urllib.request.Request(API + path, data=json.dumps(data).encode() if data else None,
                                 headers={"Accept": "application/vnd.github+json",
                                          "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                                          "User-Agent": "razerlite-watch"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def matching_commits(commits, details):
    """Commits dont le message ou les lignes modifiées parlent d'un de nos appareils."""
    found = []
    for c in commits:
        full = details(c["sha"])
        # seulement les lignes ajoutées ou retirées : les lignes de contexte citent souvent nos appareils
        # simplement parce qu'ils sont voisins dans les listes d'OpenRazer
        changed = [line for f in full.get("files", []) for line in f.get("patch", "").splitlines()
                   if line[:1] in "+-" and not line.startswith(("+++", "---"))]
        text = c["commit"]["message"] + "\n" + "\n".join(changed)
        hits = sorted({m.group(0).lower().replace("_", " ").replace("-", " ") for m in DEVICES.finditer(text)})
        if hits:
            found.append({"sha": c["sha"], "title": c["commit"]["message"].splitlines()[0],
                          "url": c["html_url"], "devices": hits,
                          "files": [f["filename"] for f in full.get("files", [])][:8]})
    return found


def issue_body(found):
    lines = ["Nouveautés d'OpenRazer qui concernent nos appareils. À adapter dans RazerLite si utile.", ""]
    for f in found:
        lines.append(f"- [{f['title']}]({f['url']}) — {', '.join(f['devices'])}")
        lines.extend(f"  - `{name}`" for name in f["files"])
    lines += ["", "<!-- " + " ".join(f["sha"] for f in found) + " -->"]
    return "\n".join(lines)


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    days = int(os.environ.get("DAYS") or 8)
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    commits = api(f"/repos/{UPSTREAM}/commits?since={since}&per_page=100")
    found = matching_commits(commits, lambda sha: api(f"/repos/{UPSTREAM}/commits/{sha}"))
    # ne pas signaler deux fois le même commit
    known = " ".join(i.get("body") or "" for i in api(f"/repos/{repo}/issues?state=all&per_page=100"))
    found = [f for f in found if f["sha"] not in known]
    print(f"{len(commits)} commits OpenRazer depuis {days} jours, {len(found)} nouveaux pour nos appareils")
    if found:
        issue = api(f"/repos/{repo}/issues", {"title": f"OpenRazer : {len(found)} nouveauté(s) pour nos appareils",
                                              "body": issue_body(found)})
        print(issue["html_url"])


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
GitHub Repository Intelligence Report Generator
================================================
Analyzes a GitHub repository and generates a professional interactive HTML dashboard.

Usage:
    python github_intelligence.py https://github.com/user/repo [options]

Options:
    --token TOKEN      GitHub personal access token
    --output DIR       Output directory (default: reports)
    --html             Generate HTML report (default: True)
    --json             Export JSON summary
    --csv              Export CSV analytics
    --verbose          Enable verbose logging
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import math
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from toolbook.utils import get_token

# ── third-party ──────────────────────────────────────────────────────────────
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    sys.exit("requests is required: pip install requests")

try:
    import pandas as pd  # noqa: F401
except ImportError:
    sys.exit("pandas is required: pip install pandas")

try:
    from jinja2 import Environment, BaseLoader
except ImportError:
    sys.exit("jinja2 is required: pip install jinja2")

# Optional – graceful degradation if missing
try:
    # pyrefly: ignore [missing-import]
    import plotly.graph_objects as go  # noqa: F401
    # pyrefly: ignore [missing-import]
    import plotly.express as px  # noqa: F401
    # pyrefly: ignore [missing-import]
    from plotly.subplots import make_subplots  # noqa: F401
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("github-intel")


# ═══════════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ContributorInfo:
    login: str
    contributions: int
    avatar_url: str = ""
    html_url: str = ""
    percentage: float = 0.0


@dataclass
class PRStats:
    total: int = 0
    open: int = 0
    closed: int = 0
    merged: int = 0
    merge_rate: float = 0.0
    avg_merge_hours: float = 0.0


@dataclass
class IssueStats:
    total: int = 0
    open: int = 0
    closed: int = 0
    avg_close_hours: float = 0.0
    label_distribution: dict[str, int] = field(default_factory=dict)


@dataclass
class RepoSummary:
    repository_health_score: int = 0
    security_risk_score: int = 0
    dependency_risk_score: int = 0
    contributors: int = 0
    commits: int = 0
    open_issues: int = 0
    pull_requests: int = 0
    top_languages: list[str] = field(default_factory=list)
    detected_technologies: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# GitHub API client
# ═══════════════════════════════════════════════════════════════════════════════

class GitHubClient:
    BASE = "https://api.github.com"

    def __init__(self, token: str | None = None):
        self.session = requests.Session()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.session.headers.update(headers)
        retry = Retry(total=5, backoff_factor=1,
                      status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.BASE}{path}"
        while True:
            r = self.session.get(url, params=params, timeout=30)
            if r.status_code == 403 and "rate limit" in r.text.lower():
                reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(reset - time.time(), 5)
                log.warning("Rate-limited. Sleeping %.0fs …", wait)
                time.sleep(wait)
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()

    def paginate(self, path: str, params: dict | None = None,
                 max_pages: int = 10) -> list:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        results: list = []
        page = 1
        while page <= max_pages:
            params["page"] = page
            data = self._get(path, params)
            if not data:
                break
            if isinstance(data, list):
                results.extend(data)
                if len(data) < params["per_page"]:
                    break
            else:
                results.append(data)
                break
            page += 1
        return results

    def get_repo(self, owner: str, repo: str) -> dict:
        return self._get(f"/repos/{owner}/{repo}") or {}

    def get_contributors(self, owner: str, repo: str) -> list:
        return self.paginate(f"/repos/{owner}/{repo}/contributors", max_pages=5)

    def get_commits(self, owner: str, repo: str) -> list:
        return self.paginate(f"/repos/{owner}/{repo}/commits",
                             params={"per_page": 100}, max_pages=10)

    def get_languages(self, owner: str, repo: str) -> dict:
        return self._get(f"/repos/{owner}/{repo}/languages") or {}

    def get_pulls(self, owner: str, repo: str, state: str = "all") -> list:
        return self.paginate(f"/repos/{owner}/{repo}/pulls",
                             params={"state": state}, max_pages=5)

    def get_issues(self, owner: str, repo: str) -> list:
        return self.paginate(f"/repos/{owner}/{repo}/issues",
                             params={"state": "all"}, max_pages=5)

    def get_releases(self, owner: str, repo: str) -> list:
        return self.paginate(f"/repos/{owner}/{repo}/releases", max_pages=3)

    def get_branches(self, owner: str, repo: str) -> list:
        return self.paginate(f"/repos/{owner}/{repo}/branches", max_pages=3)

    def get_contents(self, owner: str, repo: str, path: str = "") -> Any:
        return self._get(f"/repos/{owner}/{repo}/contents/{path}")

    def get_workflows(self, owner: str, repo: str) -> list:
        data = self._get(f"/repos/{owner}/{repo}/actions/workflows") or {}
        return data.get("workflows", [])

    def get_topics(self, owner: str, repo: str) -> list[str]:
        data = self._get(f"/repos/{owner}/{repo}/topics") or {}
        return data.get("names", [])


# ═══════════════════════════════════════════════════════════════════════════════
# Analysis modules
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_repo_url(url: str) -> tuple[str, str]:
    """Extract owner and repo name from GitHub URL."""
    parsed = urlparse(url.rstrip("/"))
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse repo URL: {url}")
    return parts[0], parts[1].removesuffix(".git")


def analyze_repo_overview(client: GitHubClient,
                           owner: str, repo: str) -> dict:
    log.info("📊 Fetching repository overview …")
    data = client.get_repo(owner, repo)
    topics = client.get_topics(owner, repo)

    created = data.get("created_at", "")
    updated = data.get("updated_at", "")
    pushed  = data.get("pushed_at", "")

    # Age-based activity score
    age_days = 0
    idle_days = 0
    if created:
        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - created_dt).days
    if pushed:
        pushed_dt = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
        idle_days = (datetime.now(timezone.utc) - pushed_dt).days

    # Health score heuristic
    stars     = data.get("stargazers_count", 0)
    forks     = data.get("forks_count", 0)
    has_desc  = bool(data.get("description"))
    has_lic   = bool(data.get("license"))
    has_wiki  = bool(data.get("has_wiki"))

    health = 50
    if has_desc:
        health += 10
    if has_lic:
        health += 10
    if has_wiki:
        health += 5
    if topics:
        health += 5
    if idle_days < 30:
        health += 15
    elif idle_days < 90:
        health += 8
    if stars > 100:
        health += 5

    return {
        "name": data.get("name", ""),
        "owner": data.get("owner", {}).get("login", ""),
        "full_name": data.get("full_name", ""),
        "description": data.get("description", "No description"),
        "stars": stars,
        "forks": forks,
        "watchers": data.get("watchers_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "license": (data.get("license") or {}).get("spdx_id", "None"),
        "default_branch": data.get("default_branch", "main"),
        "topics": topics,
        "size_kb": data.get("size", 0),
        "created_at": created,
        "updated_at": updated,
        "pushed_at": pushed,
        "homepage": data.get("homepage") or "",
        "language": data.get("language") or "Unknown",
        "is_archived": data.get("archived", False),
        "is_fork": data.get("fork", False),
        "age_days": age_days,
        "idle_days": idle_days,
        "health_score": min(100, health),
    }


def analyze_contributors(client: GitHubClient,
                          owner: str, repo: str) -> list[ContributorInfo]:
    log.info("👥 Analyzing contributors …")
    raw = client.get_contributors(owner, repo)
    total = sum(c.get("contributions", 0) for c in raw) or 1
    return [
        ContributorInfo(
            login=c["login"],
            contributions=c["contributions"],
            avatar_url=c.get("avatar_url", ""),
            html_url=c.get("html_url", ""),
            percentage=round(c["contributions"] / total * 100, 1),
        )
        for c in raw[:20]
    ]


def analyze_commits(client: GitHubClient,
                    owner: str, repo: str) -> dict:
    log.info("📈 Analyzing commit trends …")
    commits = client.get_commits(owner, repo)
    if not commits:
        return {"total": 0, "by_day": {}, "by_hour": {}, "by_month": {},
                "by_author": {}, "velocity_per_week": 0, "heatmap_data": []}

    dates = []
    hours: list[int] = []
    authors: list[str] = []
    for c in commits:
        raw_date = (c.get("commit", {})
                     .get("author", {})
                     .get("date", ""))
        if raw_date:
            try:
                dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                dates.append(dt)
                hours.append(dt.hour)
                authors.append(
                    c.get("author", {}).get("login", "unknown")
                    if c.get("author") else "unknown"
                )
            except ValueError:
                pass

    by_day   = Counter(d.strftime("%Y-%m-%d") for d in dates)
    by_hour  = Counter(h for h in hours)
    by_month = Counter(d.strftime("%Y-%m") for d in dates)
    by_author = Counter(authors)

    # Heatmap: last 52 weeks × 7 days
    today = datetime.now(timezone.utc).date()
    date_set = {d.date() for d in dates}
    heatmap: list[dict] = []
    for week in range(52):
        for dow in range(7):
            day = today - timedelta(weeks=week, days=dow)
            heatmap.append({
                "date": str(day),
                "week": week,
                "dow": dow,
                "count": 1 if day in date_set else 0,
            })

    # velocity: commits per week over last 12 weeks
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=12)
    recent = [d for d in dates if d >= cutoff]
    velocity = round(len(recent) / 12, 1)

    return {
        "total": len(commits),
        "by_day": dict(sorted(by_day.items())[-90:]),
        "by_hour": {str(k): v for k, v in sorted(by_hour.items())},
        "by_month": dict(sorted(by_month.items())[-18:]),
        "by_author": dict(by_author.most_common(10)),
        "velocity_per_week": velocity,
        "heatmap_data": heatmap,
        "most_active_hour": (max(by_hour, key=by_hour.get)
                             if by_hour else 0),
        "most_active_day": (max(by_day, key=by_day.get)
                            if by_day else "N/A"),
    }


def analyze_languages(client: GitHubClient,
                       owner: str, repo: str) -> dict:
    log.info("🔤 Detecting languages …")
    raw = client.get_languages(owner, repo)
    total = sum(raw.values()) or 1
    return {
        lang: {"bytes": b, "pct": round(b / total * 100, 1)}
        for lang, b in sorted(raw.items(), key=lambda x: -x[1])
    }


# Technology fingerprinting
_TECH_FINGERPRINTS: dict[str, list[str]] = {
    "React":      ["react", "react-dom"],
    "Next.js":    ["next"],
    "Vue":        ["vue"],
    "Angular":    ["@angular/core"],
    "Svelte":     ["svelte"],
    "Node.js":    ["express", "koa", "fastify", "hapi"],
    "Django":     ["django"],
    "Flask":      ["flask"],
    "FastAPI":    ["fastapi"],
    "Celery":     ["celery"],
    "SQLAlchemy": ["sqlalchemy"],
    "Docker":     ["dockerfile", "docker-compose"],
    "Kubernetes": ["kubernetes", "kubectl", "helm"],
    "Terraform":  ["terraform"],
    "PostgreSQL": ["psycopg2", "pg"],
    "Redis":      ["redis"],
    "GraphQL":    ["graphql", "apollo"],
    "TypeScript": ["typescript", "ts-node"],
    "Tailwind":   ["tailwindcss"],
    "Pytest":     ["pytest"],
    "Jest":       ["jest"],
}


def detect_technologies(client: GitHubClient,
                         owner: str, repo: str,
                         languages: dict) -> dict:
    log.info("🛠️  Detecting technologies …")
    detected: set[str] = set()
    ci_tools: set[str] = []
    has_docker = False
    has_k8s    = False

    # Language-based detection
    for lang in languages:
        if lang == "TypeScript":
            detected.add("TypeScript")
        if lang == "Go":
            detected.add("Go")
        if lang == "Rust":
            detected.add("Rust")

    # File-based detection
    def _check_file(path: str) -> str:
        try:
            item = client.get_contents(owner, repo, path)
            if isinstance(item, dict) and item.get("content"):
                return base64.b64decode(item["content"]).decode("utf-8", errors="ignore")
        except Exception:
            pass
        return ""

    # package.json
    pkg_json = _check_file("package.json")
    if pkg_json:
        try:
            pkg = json.loads(pkg_json)
            all_deps = {**pkg.get("dependencies", {}),
                        **pkg.get("devDependencies", {})}
            for tech, keys in _TECH_FINGERPRINTS.items():
                if any(k in all_deps for k in keys):
                    detected.add(tech)
        except json.JSONDecodeError:
            pass

    # requirements.txt
    req_txt = _check_file("requirements.txt")
    if req_txt:
        lower = req_txt.lower()
        for tech, keys in _TECH_FINGERPRINTS.items():
            if any(k in lower for k in keys):
                detected.add(tech)

    # pyproject.toml
    pyproject = _check_file("pyproject.toml")
    if pyproject:
        lower = pyproject.lower()
        for tech, keys in _TECH_FINGERPRINTS.items():
            if any(k in lower for k in keys):
                detected.add(tech)

    # Dockerfile
    dockerfile = _check_file("Dockerfile")
    if dockerfile:
        has_docker = True
        detected.add("Docker")

    # docker-compose
    dc = _check_file("docker-compose.yml") or _check_file("docker-compose.yaml")
    if dc:
        has_docker = True
        detected.add("Docker Compose")

    # Kubernetes manifests
    k8s = _check_file("k8s") or _check_file("kubernetes")
    if k8s:
        has_k8s = True
        detected.add("Kubernetes")

    # CI/CD workflows
    workflows = client.get_workflows(owner, repo)
    if workflows:
        detected.add("GitHub Actions")
        ci_tools = ["GitHub Actions"]

    # Terraform
    tf = _check_file("main.tf") or _check_file("terraform")
    if tf:
        detected.add("Terraform")

    return {
        "technologies": sorted(detected),
        "has_docker": has_docker,
        "has_kubernetes": has_k8s,
        "ci_tools": ci_tools,
        "workflow_count": len(workflows),
        "devops_score": _devops_score(detected, workflows),
    }


def _devops_score(techs: set, workflows: list) -> int:
    score = 0
    if "GitHub Actions" in techs:
        score += 30
    if "Docker" in techs:
        score += 20
    if "Docker Compose" in techs:
        score += 10
    if "Kubernetes" in techs:
        score += 20
    if "Terraform" in techs:
        score += 15
    if workflows:
        score += min(len(workflows) * 5, 15)
    return min(100, score)


def analyze_pull_requests(client: GitHubClient,
                           owner: str, repo: str) -> PRStats:
    log.info("🔀 Analyzing pull requests …")
    pulls = client.get_pulls(owner, repo)
    if not pulls:
        return PRStats()

    open_prs   = [p for p in pulls if p.get("state") == "open"]
    closed_prs = [p for p in pulls if p.get("state") == "closed"]
    merged_prs = [p for p in closed_prs if p.get("merged_at")]

    merge_times: list[float] = []
    for pr in merged_prs:
        created = pr.get("created_at", "")
        merged  = pr.get("merged_at", "")
        if created and merged:
            try:
                c = datetime.fromisoformat(created.replace("Z", "+00:00"))
                m = datetime.fromisoformat(merged.replace("Z", "+00:00"))
                merge_times.append((m - c).total_seconds() / 3600)
            except ValueError:
                pass

    avg_merge = round(sum(merge_times) / len(merge_times), 1) if merge_times else 0
    merge_rate = round(len(merged_prs) / len(closed_prs) * 100, 1) if closed_prs else 0

    return PRStats(
        total=len(pulls),
        open=len(open_prs),
        closed=len(closed_prs),
        merged=len(merged_prs),
        merge_rate=merge_rate,
        avg_merge_hours=avg_merge,
    )


def analyze_issues(client: GitHubClient,
                   owner: str, repo: str) -> IssueStats:
    log.info("🐛 Analyzing issues …")
    issues = [i for i in client.get_issues(owner, repo)
              if not i.get("pull_request")]  # exclude PRs
    if not issues:
        return IssueStats()

    open_i   = [i for i in issues if i.get("state") == "open"]
    closed_i = [i for i in issues if i.get("state") == "closed"]

    close_times: list[float] = []
    for iss in closed_i:
        created = iss.get("created_at", "")
        closed  = iss.get("closed_at", "")
        if created and closed:
            try:
                c = datetime.fromisoformat(created.replace("Z", "+00:00"))
                cl = datetime.fromisoformat(closed.replace("Z", "+00:00"))
                close_times.append((cl - c).total_seconds() / 3600)
            except ValueError:
                pass

    avg_close = round(sum(close_times) / len(close_times), 1) if close_times else 0

    label_counts: Counter = Counter()
    for iss in issues:
        for lbl in iss.get("labels", []):
            label_counts[lbl["name"]] += 1

    return IssueStats(
        total=len(issues),
        open=len(open_i),
        closed=len(closed_i),
        avg_close_hours=avg_close,
        label_distribution=dict(label_counts.most_common(10)),
    )


def analyze_releases(client: GitHubClient,
                     owner: str, repo: str) -> dict:
    log.info("🚀 Analyzing releases …")
    releases = client.get_releases(owner, repo)
    if not releases:
        return {"count": 0, "latest": None, "cadence_days": 0, "items": []}

    dates = []
    items = []
    for r in releases[:20]:
        pub = r.get("published_at", "")
        if pub:
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                dates.append(dt)
            except ValueError:
                pass
        items.append({
            "name": r.get("name") or r.get("tag_name", ""),
            "tag": r.get("tag_name", ""),
            "published_at": pub,
            "prerelease": r.get("prerelease", False),
        })

    cadence = 0
    if len(dates) >= 2:
        spans = [(dates[i] - dates[i+1]).days for i in range(len(dates)-1)]
        cadence = round(sum(spans) / len(spans))

    return {
        "count": len(releases),
        "latest": items[0] if items else None,
        "cadence_days": cadence,
        "items": items[:10],
    }


def compute_dependency_risk(client: GitHubClient,
                             owner: str, repo: str,
                             languages: dict) -> dict:
    """Heuristic dependency risk without running pip-audit locally."""
    log.info("🔒 Computing dependency risk …")
    score = 50  # baseline
    notes: list[str] = []

    req_txt = ""
    try:
        item = client.get_contents(owner, repo, "requirements.txt")
        if isinstance(item, dict) and item.get("content"):
            req_txt = base64.b64decode(item["content"]).decode("utf-8", errors="ignore")
    except Exception:
        pass

    dep_count = 0
    pinned = 0
    unpinned = 0
    if req_txt:
        for line in req_txt.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                dep_count += 1
                if "==" in line:
                    pinned += 1
                else:
                    unpinned += 1
        if unpinned > 0:
            score -= min(unpinned * 3, 20)
            notes.append(f"{unpinned} unpinned dependencies")
        if dep_count > 50:
            score -= 10
            notes.append("High dependency count (>50)")

    pkg_json = ""
    try:
        item = client.get_contents(owner, repo, "package.json")
        if isinstance(item, dict) and item.get("content"):
            pkg_json = base64.b64decode(item["content"]).decode("utf-8", errors="ignore")
    except Exception:
        pass

    npm_dep_count = 0
    if pkg_json:
        try:
            pkg = json.loads(pkg_json)
            deps = pkg.get("dependencies", {})
            dev_deps = pkg.get("devDependencies", {})
            npm_dep_count = len(deps) + len(dev_deps)
            if npm_dep_count > 100:
                score -= 10
                notes.append(f"High npm dependency count ({npm_dep_count})")
        except json.JSONDecodeError:
            pass

    # Bonus for having lock files
    lockfiles = ["package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                 "poetry.lock", "Pipfile.lock", "requirements.lock"]
    found_lock = False
    for lf in lockfiles:
        try:
            item = client.get_contents(owner, repo, lf)
            if item:
                found_lock = True
                break
        except Exception:
            pass
    if found_lock:
        score += 10
    else:
        notes.append("No lock file detected")

    risk_level = "Low" if score >= 70 else "Medium" if score >= 45 else "High"

    return {
        "score": max(0, min(100, score)),
        "risk_level": risk_level,
        "dep_count": dep_count + npm_dep_count,
        "pinned": pinned,
        "unpinned": unpinned,
        "has_lock_file": found_lock,
        "notes": notes,
    }


def compute_security_risk(repo_info: dict, dep_risk: dict,
                           tech: dict) -> int:
    score = 80  # start optimistic
    if repo_info.get("license") in ("None", None):
        score -= 10
    if dep_risk["risk_level"] == "High":
        score -= 20
    elif dep_risk["risk_level"] == "Medium":
        score -= 10
    if not dep_risk.get("has_lock_file"):
        score -= 5
    if repo_info.get("idle_days", 0) > 365:
        score -= 10
    return max(0, min(100, score))


# ═══════════════════════════════════════════════════════════════════════════════
# HTML Report template (inline, no external files needed)
# ═══════════════════════════════════════════════════════════════════════════════

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{{ repo.full_name }} — Intelligence Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#0d1117;--surface:#161b22;--surface2:#1c2128;--border:#30363d;
  --text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;--accent2:#f78166;
  --green:#3fb950;--yellow:#d29922;--red:#f85149;--purple:#bc8cff;
  --font-mono:'JetBrains Mono',monospace;
}
*{margin:0;padding:0;box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;
  display:flex;min-height:100vh;}

/* ── Sidebar ── */
nav{width:220px;min-width:220px;background:var(--surface);border-right:1px solid var(--border);
  position:fixed;top:0;left:0;height:100%;overflow-y:auto;z-index:100;padding:24px 0;}
nav .logo{padding:0 20px 24px;border-bottom:1px solid var(--border);margin-bottom:16px;}
nav .logo h2{font-size:14px;color:var(--accent);letter-spacing:.05em;text-transform:uppercase;}
nav .logo p{font-size:11px;color:var(--muted);margin-top:4px;word-break:break-all;}
nav a{display:flex;align-items:center;gap:10px;padding:9px 20px;color:var(--muted);
  text-decoration:none;font-size:13px;border-left:3px solid transparent;transition:.15s;}
nav a:hover,nav a.active{color:var(--text);background:var(--surface2);
  border-left-color:var(--accent);}
nav a .icon{width:16px;text-align:center;}

/* ── Main ── */
main{margin-left:220px;flex:1;padding:32px;}
section{margin-bottom:48px;}
h1{font-size:28px;font-weight:700;margin-bottom:4px;}
.subtitle{color:var(--muted);font-size:14px;margin-bottom:32px;}
h2{font-size:18px;font-weight:600;margin-bottom:16px;color:var(--text);
   padding-bottom:8px;border-bottom:1px solid var(--border);}
h3{font-size:14px;font-weight:600;color:var(--muted);text-transform:uppercase;
   letter-spacing:.06em;margin-bottom:12px;}

/* ── Grid helpers ── */
.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;}
@media(max-width:900px){.grid4,.grid3{grid-template-columns:repeat(2,1fr);}
  .grid2{grid-template-columns:1fr;}}

/* ── Cards ── */
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px;}
.card.accent{border-color:var(--accent);}
.metric-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:18px 20px;display:flex;flex-direction:column;gap:6px;}
.metric-card .val{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums;}
.metric-card .lbl{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;}
.metric-card .sub{font-size:12px;color:var(--muted);}

/* ── Score rings ── */
.score-wrap{display:flex;gap:24px;flex-wrap:wrap;margin-bottom:24px;}
.score-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:24px;display:flex;flex-direction:column;align-items:center;gap:12px;flex:1;min-width:140px;}
.ring-svg{width:90px;height:90px;}
.score-card .label{font-size:13px;color:var(--muted);text-align:center;}

/* ── Contributor ── */
.contributor-row{display:flex;align-items:center;gap:12px;padding:10px 0;
  border-bottom:1px solid var(--border);}
.contributor-row:last-child{border-bottom:none;}
.avatar{width:36px;height:36px;border-radius:50%;object-fit:cover;
  background:var(--border);flex-shrink:0;}
.contributor-row .name{font-weight:600;font-size:14px;}
.contributor-row .commits{color:var(--muted);font-size:13px;}
.bar-bg{flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden;}
.bar-fg{height:100%;background:var(--accent);border-radius:3px;transition:width .5s;}

/* ── Heatmap ── */
.heatmap-grid{display:flex;gap:3px;overflow-x:auto;padding-bottom:8px;}
.heatmap-col{display:flex;flex-direction:column;gap:3px;}
.heatmap-cell{width:11px;height:11px;border-radius:2px;background:var(--border);}
.heatmap-cell.l1{background:#0e4429;}
.heatmap-cell.l2{background:#006d32;}
.heatmap-cell.l3{background:#26a641;}
.heatmap-cell.l4{background:#39d353;}

/* ── Tech badges ── */
.tech-grid{display:flex;flex-wrap:wrap;gap:8px;}
.tech-badge{background:var(--surface2);border:1px solid var(--border);border-radius:20px;
  padding:5px 14px;font-size:12px;font-weight:500;color:var(--text);}
.tech-badge.ci{border-color:var(--accent);color:var(--accent);}
.tech-badge.docker{border-color:#1d63ed;color:#60a5fa;}
.tech-badge.k8s{border-color:#326ce5;color:#93bbff;}

/* ── Labels ── */
.label-row{display:flex;align-items:center;gap:8px;padding:6px 0;}
.label-dot{width:10px;height:10px;border-radius:50%;}
.label-name{font-size:13px;flex:1;}
.label-count{font-size:12px;color:var(--muted);}

/* ── Risk indicators ── */
.risk-bar-wrap{margin-bottom:12px;}
.risk-label{display:flex;justify-content:space-between;margin-bottom:4px;font-size:13px;}
.risk-bar-bg{height:8px;background:var(--border);border-radius:4px;overflow:hidden;}
.risk-bar-fg{height:100%;border-radius:4px;transition:width .6s;}
.risk-low{background:var(--green);}
.risk-med{background:var(--yellow);}
.risk-high{background:var(--red);}

/* ── Release timeline ── */
.release-item{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);}
.release-item:last-child{border-bottom:none;}
.release-tag{background:var(--surface2);border:1px solid var(--border);border-radius:4px;
  padding:2px 8px;font-size:12px;font-family:var(--font-mono);color:var(--accent);}
.release-date{font-size:12px;color:var(--muted);}
.badge{display:inline-block;padding:2px 7px;border-radius:10px;font-size:11px;font-weight:600;}
.badge-pre{background:#2d1b00;color:var(--yellow);}
.badge-stable{background:#0d2e18;color:var(--green);}

/* ── Recommendations ── */
.rec-item{display:flex;gap:12px;padding:12px;background:var(--surface2);
  border-radius:6px;margin-bottom:8px;border-left:3px solid var(--accent);}
.rec-item.warn{border-left-color:var(--yellow);}
.rec-item.crit{border-left-color:var(--red);}
.rec-icon{font-size:18px;}
.rec-text h4{font-size:13px;font-weight:600;margin-bottom:2px;}
.rec-text p{font-size:12px;color:var(--muted);}

/* ── Misc ── */
.chart-wrap{position:relative;height:260px;}
.chip{display:inline-block;background:var(--surface2);border:1px solid var(--border);
  border-radius:4px;padding:2px 8px;font-size:11px;color:var(--muted);margin:2px;}
.empty{color:var(--muted);font-size:13px;font-style:italic;padding:16px 0;}
.tag{display:inline-block;background:#0d419d26;border:1px solid #388bfd40;color:var(--accent);
  border-radius:12px;padding:2px 10px;font-size:11px;margin:2px;}
</style>
</head>
<body>

<!-- Sidebar -->
<nav>
  <div class="logo">
    <h2>⚡ GH Intel</h2>
    <p>{{ repo.full_name }}</p>
  </div>
  <a href="#overview" class="active"><span class="icon">🏠</span>Overview</a>
  <a href="#contributors"><span class="icon">👥</span>Contributors</a>
  <a href="#activity"><span class="icon">📈</span>Activity</a>
  <a href="#heatmap"><span class="icon">🔥</span>Heatmap</a>
  <a href="#languages"><span class="icon">🔤</span>Languages</a>
  <a href="#techstack"><span class="icon">🛠️</span>Tech Stack</a>
  <a href="#pullrequests"><span class="icon">🔀</span>Pull Requests</a>
  <a href="#issues"><span class="icon">🐛</span>Issues</a>
  <a href="#releases"><span class="icon">🚀</span>Releases</a>
  <a href="#dependencies"><span class="icon">📦</span>Dependencies</a>
  <a href="#devops"><span class="icon">⚙️</span>DevOps</a>
  <a href="#recommendations"><span class="icon">💡</span>Recommendations</a>
</nav>

<!-- Main -->
<main>

<!-- ── Header ── -->
<section id="overview">
  <h1>{{ repo.name }}</h1>
  <p class="subtitle">{{ repo.description }}</p>
  {% if repo.topics %}
  <div style="margin-bottom:20px;">
    {% for t in repo.topics %}<span class="tag">{{ t }}</span>{% endfor %}
  </div>
  {% endif %}

  <!-- Score rings -->
  <div class="score-wrap">
    {% for s in scores %}
    <div class="score-card">
      <svg class="ring-svg" viewBox="0 0 90 90">
        <circle cx="45" cy="45" r="38" fill="none" stroke="var(--border)" stroke-width="8"/>
        <circle cx="45" cy="45" r="38" fill="none" stroke="{{ s.color }}" stroke-width="8"
          stroke-dasharray="{{ s.dash }} 239"
          stroke-dashoffset="60" stroke-linecap="round" transform="rotate(-90 45 45)"/>
        <text x="45" y="49" text-anchor="middle" fill="{{ s.color }}" font-size="18"
          font-weight="bold" font-family="monospace">{{ s.value }}</text>
      </svg>
      <span class="label">{{ s.label }}</span>
    </div>
    {% endfor %}
  </div>

  <!-- KPI grid -->
  <div class="grid4">
    <div class="metric-card">
      <span class="val" style="color:var(--yellow);">⭐ {{ repo.stars | commas }}</span>
      <span class="lbl">Stars</span>
    </div>
    <div class="metric-card">
      <span class="val" style="color:var(--accent);">🍴 {{ repo.forks | commas }}</span>
      <span class="lbl">Forks</span>
    </div>
    <div class="metric-card">
      <span class="val" style="color:var(--purple);">📝 {{ commits.total | commas }}</span>
      <span class="lbl">Commits</span>
      <span class="sub">~{{ commits.velocity_per_week }}/week</span>
    </div>
    <div class="metric-card">
      <span class="val" style="color:var(--green);">👁️ {{ repo.watchers | commas }}</span>
      <span class="lbl">Watchers</span>
    </div>
    <div class="metric-card">
      <span class="val">🐛 {{ repo.open_issues | commas }}</span>
      <span class="lbl">Open Issues</span>
    </div>
    <div class="metric-card">
      <span class="val">🔀 {{ prs.total | commas }}</span>
      <span class="lbl">Pull Requests</span>
      <span class="sub">{{ prs.merge_rate }}% merge rate</span>
    </div>
    <div class="metric-card">
      <span class="val">📦 {{ releases.count | commas }}</span>
      <span class="lbl">Releases</span>
    </div>
    <div class="metric-card">
      <span class="val">⚖️ {{ repo.license }}</span>
      <span class="lbl">License</span>
    </div>
  </div>

  <!-- Repo meta -->
  <div class="card" style="margin-top:16px;">
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;font-size:13px;">
      <div><span style="color:var(--muted);">Default branch</span><br/><strong>{{ repo.default_branch }}</strong></div>
      <div><span style="color:var(--muted);">Primary language</span><br/><strong>{{ repo.language }}</strong></div>
      <div><span style="color:var(--muted);">Repo size</span><br/><strong>{{ (repo.size_kb / 1024) | round(1) }} MB</strong></div>
      <div><span style="color:var(--muted);">Created</span><br/><strong>{{ repo.created_at[:10] }}</strong></div>
      <div><span style="color:var(--muted);">Last pushed</span><br/><strong>{{ repo.pushed_at[:10] }}</strong></div>
      <div><span style="color:var(--muted);">Idle days</span><br/><strong style="color:{% if repo.idle_days > 180 %}var(--red){% elif repo.idle_days > 60 %}var(--yellow){% else %}var(--green){% endif %};">{{ repo.idle_days }}</strong></div>
    </div>
  </div>
</section>

<!-- ── Contributors ── -->
<section id="contributors">
  <h2>👥 Contributor Analysis</h2>
  <div class="grid2">
    <div class="card">
      <h3>Leaderboard</h3>
      {% for c in contributors[:10] %}
      <div class="contributor-row">
        <img class="avatar" src="{{ c.avatar_url }}" onerror="this.style.background='#30363d'" alt=""/>
        <div style="flex:1;min-width:0;">
          <div class="name">{{ c.login }}</div>
          <div class="commits">{{ c.contributions | commas }} commits · {{ c.percentage }}%</div>
          <div class="bar-bg" style="margin-top:4px;">
            <div class="bar-fg" style="width:{{ c.percentage }}%;"></div>
          </div>
        </div>
      </div>
      {% else %}
      <p class="empty">No contributor data</p>
      {% endfor %}
    </div>
    <div class="card">
      <h3>Distribution</h3>
      <div class="chart-wrap"><canvas id="contribChart"></canvas></div>
    </div>
  </div>
</section>

<!-- ── Activity ── -->
<section id="activity">
  <h2>📈 Commit Activity</h2>
  <div class="grid2">
    <div class="card">
      <h3>Monthly commits (last 18 months)</h3>
      <div class="chart-wrap"><canvas id="monthlyChart"></canvas></div>
    </div>
    <div class="card">
      <h3>Commits by hour of day</h3>
      <div class="chart-wrap"><canvas id="hourChart"></canvas></div>
    </div>
  </div>
</section>

<!-- ── Heatmap ── -->
<section id="heatmap">
  <h2>🔥 Activity Heatmap (last year)</h2>
  <div class="card">
    <p style="font-size:12px;color:var(--muted);margin-bottom:12px;">Each cell = one day. Colour intensity = commit activity.</p>
    <div class="heatmap-grid" id="heatmapGrid"></div>
    <div style="display:flex;align-items:center;gap:6px;margin-top:10px;font-size:11px;color:var(--muted);">
      Less <div class="heatmap-cell"></div>
      <div class="heatmap-cell l1"></div>
      <div class="heatmap-cell l2"></div>
      <div class="heatmap-cell l3"></div>
      <div class="heatmap-cell l4"></div> More
    </div>
  </div>
</section>

<!-- ── Languages ── -->
<section id="languages">
  <h2>🔤 Language Breakdown</h2>
  <div class="grid2">
    <div class="card">
      <div class="chart-wrap"><canvas id="langChart"></canvas></div>
    </div>
    <div class="card">
      {% for lang, info in languages.items() %}
      <div class="risk-bar-wrap">
        <div class="risk-label"><span>{{ lang }}</span><span>{{ info.pct }}%</span></div>
        <div class="risk-bar-bg"><div class="risk-bar-fg risk-low" style="width:{{ info.pct }}%;"></div></div>
      </div>
      {% else %}
      <p class="empty">No language data</p>
      {% endfor %}
    </div>
  </div>
</section>

<!-- ── Tech Stack ── -->
<section id="techstack">
  <h2>🛠️ Technology Stack</h2>
  <div class="card">
    <h3>Detected technologies</h3>
    <div class="tech-grid">
      {% for t in tech.technologies %}
      <span class="tech-badge {% if t in ['GitHub Actions'] %}ci{% elif t in ['Docker','Docker Compose'] %}docker{% elif t == 'Kubernetes' %}k8s{% endif %}">{{ t }}</span>
      {% else %}
      <p class="empty">No technologies detected</p>
      {% endfor %}
    </div>
    {% if tech.ci_tools %}
    <div style="margin-top:16px;">
      <h3>CI/CD</h3>
      <div class="tech-grid">
        {% for t in tech.ci_tools %}<span class="tech-badge ci">⚙️ {{ t }}</span>{% endfor %}
      </div>
    </div>
    {% endif %}
  </div>
</section>

<!-- ── Pull Requests ── -->
<section id="pullrequests">
  <h2>🔀 Pull Request Analytics</h2>
  <div class="grid4" style="margin-bottom:16px;">
    <div class="metric-card"><span class="val">{{ prs.total }}</span><span class="lbl">Total PRs</span></div>
    <div class="metric-card"><span class="val" style="color:var(--green);">{{ prs.merged }}</span><span class="lbl">Merged</span></div>
    <div class="metric-card"><span class="val" style="color:var(--accent);">{{ prs.open }}</span><span class="lbl">Open</span></div>
    <div class="metric-card">
      <span class="val" style="color:var(--yellow);">{{ prs.avg_merge_hours }}h</span>
      <span class="lbl">Avg merge time</span>
    </div>
  </div>
  <div class="card">
    <div class="chart-wrap"><canvas id="prChart"></canvas></div>
  </div>
</section>

<!-- ── Issues ── -->
<section id="issues">
  <h2>🐛 Issue Analytics</h2>
  <div class="grid2">
    <div class="card">
      <div class="grid2">
        <div class="metric-card"><span class="val" style="color:var(--accent);">{{ issues.open }}</span><span class="lbl">Open</span></div>
        <div class="metric-card"><span class="val" style="color:var(--green);">{{ issues.closed }}</span><span class="lbl">Closed</span></div>
        <div class="metric-card"><span class="val">{{ issues.total }}</span><span class="lbl">Total</span></div>
        <div class="metric-card"><span class="val">{{ issues.avg_close_hours }}h</span><span class="lbl">Avg close time</span></div>
      </div>
    </div>
    <div class="card">
      <h3>Label distribution</h3>
      {% for lbl, cnt in issues.label_distribution.items() %}
      <div class="label-row">
        <div class="label-dot" style="background:#{{ range(16,256)|random|format('02x') }}{{ range(16,256)|random|format('02x') }}{{ range(16,256)|random|format('02x') }};"></div>
        <span class="label-name">{{ lbl }}</span>
        <span class="label-count">{{ cnt }}</span>
      </div>
      {% else %}
      <p class="empty">No label data</p>
      {% endfor %}
    </div>
  </div>
</section>

<!-- ── Releases ── -->
<section id="releases">
  <h2>🚀 Release History</h2>
  <div class="grid2">
    <div class="card">
      <div class="grid2" style="margin-bottom:16px;">
        <div class="metric-card"><span class="val">{{ releases.count }}</span><span class="lbl">Total releases</span></div>
        <div class="metric-card"><span class="val">~{{ releases.cadence_days }}d</span><span class="lbl">Avg cadence</span></div>
      </div>
      {% for r in releases['items'] %}
      <div class="release-item">
        <div>
          <span class="release-tag">{{ r.tag }}</span>
          {% if r.prerelease %}<span class="badge badge-pre">pre</span>{% else %}<span class="badge badge-stable">stable</span>{% endif %}
          <div class="release-date">{{ r.published_at[:10] if r.published_at else '' }}</div>
        </div>
        <div style="font-size:13px;color:var(--muted);">{{ r.name }}</div>
      </div>
      {% else %}
      <p class="empty">No releases found</p>
      {% endfor %}
    </div>
    <div class="card">
      <h3>Release cadence</h3>
      <div class="chart-wrap"><canvas id="releaseChart"></canvas></div>
    </div>
  </div>
</section>

<!-- ── Dependencies ── -->
<section id="dependencies">
  <h2>📦 Dependency Risk</h2>
  <div class="grid3">
    <div class="metric-card">
      <span class="val" style="color:{% if dep.risk_level=='High' %}var(--red){% elif dep.risk_level=='Medium' %}var(--yellow){% else %}var(--green){% endif %};">{{ dep.risk_level }}</span>
      <span class="lbl">Risk level</span>
    </div>
    <div class="metric-card"><span class="val">{{ dep.dep_count }}</span><span class="lbl">Total deps</span></div>
    <div class="metric-card">
      <span class="val" style="color:{% if dep.has_lock_file %}var(--green){% else %}var(--red){% endif %};">{{ "✓" if dep.has_lock_file else "✗" }}</span>
      <span class="lbl">Lock file</span>
    </div>
  </div>
  <div class="card" style="margin-top:16px;">
    <div class="risk-bar-wrap">
      <div class="risk-label"><span>Dependency health score</span><span>{{ dep.score }}/100</span></div>
      <div class="risk-bar-bg"><div class="risk-bar-fg {% if dep.score >= 70 %}risk-low{% elif dep.score >= 45 %}risk-med{% else %}risk-high{% endif %}" style="width:{{ dep.score }}%;"></div></div>
    </div>
    {% if dep.notes %}
    <div style="margin-top:12px;">
      {% for n in dep.notes %}<div class="chip">⚠️ {{ n }}</div>{% endfor %}
    </div>
    {% endif %}
  </div>
</section>

<!-- ── DevOps ── -->
<section id="devops">
  <h2>⚙️ DevOps Maturity</h2>
  <div class="card">
    <div class="risk-bar-wrap">
      <div class="risk-label"><span>DevOps maturity score</span><span>{{ tech.devops_score }}/100</span></div>
      <div class="risk-bar-bg"><div class="risk-bar-fg {% if tech.devops_score >= 70 %}risk-low{% elif tech.devops_score >= 40 %}risk-med{% else %}risk-high{% endif %}" style="width:{{ tech.devops_score }}%;"></div></div>
    </div>
    <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:16px;font-size:13px;">
      <div>GitHub Actions: <strong style="color:{% if tech.has_docker %}var(--green){% else %}var(--muted){% endif %};">{{ "✓" if "GitHub Actions" in tech.technologies else "✗" }}</strong></div>
      <div>Docker: <strong style="color:{% if tech.has_docker %}var(--green){% else %}var(--muted){% endif %};">{{ "✓" if tech.has_docker else "✗" }}</strong></div>
      <div>Kubernetes: <strong style="color:{% if tech.has_kubernetes %}var(--green){% else %}var(--muted){% endif %};">{{ "✓" if tech.has_kubernetes else "✗" }}</strong></div>
      <div>Workflows: <strong>{{ tech.workflow_count }}</strong></div>
    </div>
  </div>
</section>

<!-- ── Recommendations ── -->
<section id="recommendations">
  <h2>💡 Recommendations</h2>
  {% for r in recommendations %}
  <div class="rec-item {{ r.level }}">
    <div class="rec-icon">{{ r.icon }}</div>
    <div class="rec-text">
      <h4>{{ r.title }}</h4>
      <p>{{ r.body }}</p>
    </div>
  </div>
  {% else %}
  <p class="empty">No recommendations — repository looks healthy!</p>
  {% endfor %}
</section>

</main>

<script>
// ── Chart.js defaults ──────────────────────────────────────────────────────
Chart.defaults.color = '#8b949e';
Chart.defaults.borderColor = '#30363d';
Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";

// ── Contributor doughnut ───────────────────────────────────────────────────
(function(){
  const labels = {{ contrib_labels | tojson }};
  const data   = {{ contrib_data | tojson }};
  if(!labels.length) return;
  new Chart(document.getElementById('contribChart'), {
    type:'doughnut',
    data:{
      labels,
      datasets:[{data,
        backgroundColor:['#58a6ff','#3fb950','#f78166','#d29922','#bc8cff',
          '#39d353','#ff7b72','#79c0ff','#56d364','#e3b341'],
        borderWidth:2,borderColor:'#161b22'}]
    },
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{position:'right',labels:{font:{size:11},boxWidth:12}}}}
  });
})();

// ── Monthly commits bar ────────────────────────────────────────────────────
(function(){
  const labels = {{ monthly_labels | tojson }};
  const data   = {{ monthly_data | tojson }};
  if(!labels.length) return;
  new Chart(document.getElementById('monthlyChart'), {
    type:'bar',
    data:{labels,datasets:[{
      label:'Commits',data,
      backgroundColor:'rgba(88,166,255,0.5)',borderColor:'#58a6ff',borderWidth:1,
      borderRadius:3}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{x:{ticks:{maxRotation:45}},y:{beginAtZero:true}}}
  });
})();

// ── Hour heatmap bar ───────────────────────────────────────────────────────
(function(){
  const labels = Array.from({length:24},(_,i)=>i+'h');
  const data   = {{ hour_data | tojson }};
  new Chart(document.getElementById('hourChart'), {
    type:'bar',
    data:{labels,datasets:[{
      label:'Commits',data,
      backgroundColor:'rgba(63,185,80,0.5)',borderColor:'#3fb950',borderWidth:1,
      borderRadius:2}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{y:{beginAtZero:true}}}
  });
})();

// ── Language pie ───────────────────────────────────────────────────────────
(function(){
  const labels = {{ lang_labels | tojson }};
  const data   = {{ lang_data | tojson }};
  if(!labels.length) return;
  new Chart(document.getElementById('langChart'), {
    type:'pie',
    data:{labels,datasets:[{data,
      backgroundColor:['#58a6ff','#3fb950','#f78166','#d29922','#bc8cff',
        '#39d353','#ff7b72','#79c0ff'],
      borderWidth:2,borderColor:'#161b22'}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{position:'right',labels:{font:{size:11},boxWidth:12}}}}
  });
})();

// ── PR bar ────────────────────────────────────────────────────────────────
(function(){
  const ctx = document.getElementById('prChart');
  new Chart(ctx, {
    type:'bar',
    data:{
      labels:['Open','Merged','Closed (not merged)'],
      datasets:[{
        data:[{{ prs.open }},{{ prs.merged }},{{ prs.closed - prs.merged }}],
        backgroundColor:['rgba(88,166,255,.6)','rgba(63,185,80,.6)','rgba(248,81,73,.6)'],
        borderWidth:1,borderRadius:4}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{y:{beginAtZero:true}}}
  });
})();

// ── Release chart ─────────────────────────────────────────────────────────
(function(){
  const labels = {{ release_labels | tojson }};
  const data   = {{ release_data | tojson }};
  if(!labels.length) return;
  new Chart(document.getElementById('releaseChart'), {
    type:'bar',
    data:{labels,datasets:[{
      label:'Releases',data,
      backgroundColor:'rgba(188,140,255,.5)',borderColor:'#bc8cff',
      borderWidth:1,borderRadius:3}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{y:{beginAtZero:true,ticks:{stepSize:1}}}}
  });
})();

// ── Heatmap ───────────────────────────────────────────────────────────────
(function(){
  const heatmap = {{ heatmap_json | tojson }};
  // group by week
  const weeks = {};
  heatmap.forEach(d=>{
    if(!weeks[d.week]) weeks[d.week]=[];
    weeks[d.week].push(d);
  });
  const grid = document.getElementById('heatmapGrid');
  Object.keys(weeks).sort((a,b)=>b-a).forEach(w=>{
    const col = document.createElement('div');
    col.className = 'heatmap-col';
    weeks[w].sort((a,b)=>a.dow-b.dow).forEach(d=>{
      const cell = document.createElement('div');
      const lvl = d.count===0?'':d.count===1?'l1':'l2';
      cell.className = 'heatmap-cell '+lvl;
      cell.title = d.date;
      col.appendChild(cell);
    });
    grid.appendChild(col);
  });
})();

// ── Sidebar active link on scroll ─────────────────────────────────────────
(function(){
  const links = document.querySelectorAll('nav a');
  const ids   = [...links].map(l=>l.getAttribute('href').slice(1));
  const obs = new IntersectionObserver(entries=>{
    entries.forEach(e=>{
      if(e.isIntersecting){
        links.forEach(l=>l.classList.remove('active'));
        const a = document.querySelector(`nav a[href="#${e.target.id}"]`);
        if(a) a.classList.add('active');
      }
    });
  },{threshold:.3});
  ids.forEach(id=>{const el=document.getElementById(id);if(el)obs.observe(el);});
})();
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Report builder
# ═══════════════════════════════════════════════════════════════════════════════

def _score_dash(value: int, color: str, label: str) -> dict:
    circumference = 2 * math.pi * 38  # ≈ 238.76
    dash = round(circumference * value / 100, 1)
    return {"value": value, "dash": dash, "color": color, "label": label}


def _build_recommendations(repo_info: dict, dep: dict, tech: dict,
                            prs: PRStats, issues: IssueStats) -> list[dict]:
    recs = []

    if not repo_info.get("license") or repo_info["license"] == "None":
        recs.append({"icon": "⚖️", "level": "warn",
                     "title": "Add a license",
                     "body": "Repository has no license. This limits open-source usability."})

    if repo_info.get("idle_days", 0) > 180:
        recs.append({"icon": "💤", "level": "crit",
                     "title": "Repository appears inactive",
                     "body": f"No commits pushed in the last {repo_info['idle_days']} days."})

    if not dep.get("has_lock_file"):
        recs.append({"icon": "📦", "level": "warn",
                     "title": "Add a dependency lock file",
                     "body": "Lock files ensure reproducible builds. Consider poetry.lock, package-lock.json, etc."})

    if dep.get("unpinned", 0) > 5:
        recs.append({"icon": "🔒", "level": "warn",
                     "title": "Pin dependencies",
                     "body": f"{dep['unpinned']} unpinned dependencies found. Pin versions for stability."})

    if not tech.get("has_docker") and tech.get("devops_score", 0) < 30:
        recs.append({"icon": "🐳", "level": "",
                     "title": "Containerise the application",
                     "body": "Adding a Dockerfile improves portability and deployment consistency."})

    if "GitHub Actions" not in tech.get("technologies", []):
        recs.append({"icon": "⚙️", "level": "",
                     "title": "Set up CI/CD",
                     "body": "No CI workflows detected. GitHub Actions can automate testing and deployment."})

    if prs.avg_merge_hours > 168:
        recs.append({"icon": "⏱️", "level": "warn",
                     "title": "Improve PR review velocity",
                     "body": f"Average merge time is {prs.avg_merge_hours:.0f}h (> 1 week). Consider code review SLAs."})

    if not repo_info.get("description"):
        recs.append({"icon": "📝", "level": "",
                     "title": "Add a repository description",
                     "body": "A clear description improves discoverability."})

    return recs


def _render_report(data: dict, output_path: Path) -> None:
    env = Environment(loader=BaseLoader())

    # Custom filter
    def commas(v):
        try:
            return f"{int(v):,}"
        except (ValueError, TypeError):
            return v

    env.filters["commas"] = commas
    env.filters["round"] = round

    tmpl = env.from_string(HTML_TEMPLATE)
    html = tmpl.render(**data)
    output_path.write_text(html, encoding="utf-8")


def _build_chart_data(commits: dict, languages: dict,
                       contributors: list[ContributorInfo],
                       releases: dict) -> dict:
    # Monthly
    monthly_labels = list(commits.get("by_month", {}).keys())
    monthly_data   = list(commits.get("by_month", {}).values())

    # Hourly (all 24 hours)
    by_hour = commits.get("by_hour", {})
    hour_data = [by_hour.get(str(h), 0) for h in range(24)]

    # Languages
    lang_labels = list(languages.keys())[:8]
    lang_data   = [languages[lang]["pct"] for lang in lang_labels]

    # Contributors
    contrib_labels = [c.login for c in contributors[:10]]
    contrib_data   = [c.contributions for c in contributors[:10]]

    # Releases by month
    release_counts: Counter = Counter()
    for r in releases.get("items", []):
        d = r.get("published_at", "")[:7]
        if d:
            release_counts[d] += 1
    release_labels = sorted(release_counts.keys())[-18:]
    release_data   = [release_counts[rel] for rel in release_labels]

    return {
        "monthly_labels": monthly_labels,
        "monthly_data":   monthly_data,
        "hour_data":      hour_data,
        "lang_labels":    lang_labels,
        "lang_data":      lang_data,
        "contrib_labels": contrib_labels,
        "contrib_data":   contrib_data,
        "release_labels": release_labels,
        "release_data":   release_data,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════════

def gitRepoReport(
    repo_url: str,
    *,
    token: str | None = None,
    output_dir: str = "reports",
    verbose: bool = False,
) -> tuple[str, dict]:
    """
    Analyse a GitHub repository and generate a professional HTML dashboard.

    Parameters
    ----------
    repo_url   : full GitHub URL, e.g. https://github.com/owner/repo
    token      : GitHub PAT (optional, but avoids rate-limits)
    output_dir : root directory for reports (default: "reports")
    verbose    : enable DEBUG logging

    Returns
    -------
    (report_path: str, summary: dict)
    """
    if verbose:
        log.setLevel(logging.DEBUG)

    owner, repo_name = _parse_repo_url(repo_url)
    log.info("🔍 Analysing %s/%s …", owner, repo_name)

    # ── Setup directories ──
    base   = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    client = GitHubClient(token=token)

    # ── Collect data ──
    repo_info    = analyze_repo_overview(client, owner, repo_name)
    contributors = analyze_contributors(client, owner, repo_name)
    commits      = analyze_commits(client, owner, repo_name)
    languages    = analyze_languages(client, owner, repo_name)
    tech         = detect_technologies(client, owner, repo_name, languages)
    prs          = analyze_pull_requests(client, owner, repo_name)
    issues       = analyze_issues(client, owner, repo_name)
    releases     = analyze_releases(client, owner, repo_name)
    dep          = compute_dependency_risk(client, owner, repo_name, languages)

    security_score = compute_security_risk(repo_info, dep, tech)
    health_score   = repo_info["health_score"]
    dep_score      = dep["score"]

    # ── Summary dict ──
    summary: dict = {
        "repository_health_score": health_score,
        "security_risk_score":     security_score,
        "dependency_risk_score":   dep_score,
        "contributors":            len(contributors),
        "commits":                 commits["total"],
        "open_issues":             repo_info["open_issues"],
        "pull_requests":           prs.total,
        "top_languages":           list(languages.keys())[:5],
        "detected_technologies":   tech["technologies"],
    }

    # ── Chart data ──
    chart = _build_chart_data(commits, languages, contributors, releases)

    # ── Scores for rings ──
    scores = [
        _score_dash(health_score,  "#3fb950", "Health Score"),
        _score_dash(security_score,"#58a6ff", "Security Score"),
        _score_dash(dep_score,     "#d29922", "Dep. Health"),
        _score_dash(tech["devops_score"], "#bc8cff", "DevOps Maturity"),
    ]

    recommendations = _build_recommendations(repo_info, dep, tech, prs, issues)

    # ── Render HTML ──
    report_path = base / f"{owner}-{repo_name}.html"
    _render_report(
        {
            "repo":         repo_info,
            "contributors": contributors,
            "commits":      commits,
            "languages":    languages,
            "tech":         tech,
            "prs":          prs,
            "issues":       issues,
            "releases":     releases,
            "dep":          dep,
            "scores":       scores,
            "recommendations": recommendations,
            "heatmap_json": commits.get("heatmap_data", []),
            **chart,
        },
        report_path,
    )
    log.info("✅ HTML report saved → %s", report_path)

    return str(report_path), summary


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def _cli():
    parser = argparse.ArgumentParser(
        description="GitHub Repository Intelligence Report Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("repo_url", help="GitHub repository URL")
    parser.add_argument("--token",   help="GitHub personal access token")
    parser.add_argument("--output",  default="reports", help="Output directory")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    token = args.token or get_token("GITHUB_TOKEN")

    path, summary = gitRepoReport(
        args.repo_url,
        token=token,
        output_dir=args.output,
        verbose=args.verbose,
    )

    print("\n" + "="*60)
    print(f"  Report path : {path}")
    print("  Summary:")
    for k, v in summary.items():
        print(f"    {k:<30} {v}")
    print("="*60)


if __name__ == "__main__":
    _cli()
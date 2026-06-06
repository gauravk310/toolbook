"""
GitHub User Report Generator
Generates a comprehensive, interactive HTML analytics dashboard for any GitHub user.
"""

import json
import logging
import time
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from datetime import datetime, timezone
from collections import Counter
from typing import Optional
from pathlib import Path
from jinja2 import Template
from github import Github, RateLimitExceededException, Auth
from toolbook.utils import get_token

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  GITHUB DATA FETCHER
# ─────────────────────────────────────────────


class GitHubFetcher:
    """Handles all GitHub API calls with rate-limit handling and retries."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or get_token("GITHUB_TOKEN")
        self.gh = Github(auth=Auth.Token(self.token)) if self.token else Github()
        self.session_headers = {
            "Accept": "application/vnd.github.v3+json",
            **({"Authorization": f"token {self.token}"} if self.token else {}),
        }

    def _wait_for_rate_limit(self):
        try:
            rate = self.gh.get_rate_limit()
            core = getattr(rate, "rate", getattr(rate, "core", None))
            if core and core.remaining < 10:
                reset_time = core.reset
                if reset_time.tzinfo is None:
                    reset_time = reset_time.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                wait = max(0, (reset_time - now).total_seconds() + 5)
                logger.warning(
                    f"Rate limit low ({core.remaining}). Waiting {wait:.0f}s…"
                )
                time.sleep(wait)
        except Exception as e:
            logger.warning(f"Failed to check rate limit: {e}")
            time.sleep(60)

    def _api_get(self, url: str) -> Optional[dict]:
        for attempt in range(3):
            try:
                r = requests.get(url, headers=self.session_headers, timeout=15)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 403:
                    time.sleep(60)
            except Exception as e:
                logger.warning(f"Request failed ({attempt + 1}/3): {e}")
                time.sleep(5 * (attempt + 1))
        return None

    def get_user(self, username: str):
        self._wait_for_rate_limit()
        return self.gh.get_user(username)

    def get_repos(self, user):
        self._wait_for_rate_limit()
        repos = []
        try:
            for repo in user.get_repos(type="owner", sort="updated"):
                repos.append(repo)
                if len(repos) % 50 == 0:
                    logger.info(f"  Fetched {len(repos)} repos…")
        except RateLimitExceededException:
            self._wait_for_rate_limit()
        return repos

    def get_commit_activity(self, username: str) -> list:
        url = f"https://api.github.com/users/{username}/events/public"
        events = []
        page = 1
        while page <= 10:
            data = self._api_get(f"{url}?per_page=100&page={page}")
            if not data:
                break
            events.extend(data)
            if len(data) < 100:
                break
            page += 1
        return events

    def get_repo_commits(self, repo, max_commits: int = 200) -> list:
        self._wait_for_rate_limit()
        commits = []
        try:
            for c in repo.get_commits():
                commits.append(c)
                if len(commits) >= max_commits:
                    break
        except Exception:
            pass
        return commits

    def get_languages(self, repo) -> dict:
        self._wait_for_rate_limit()
        try:
            return repo.get_languages()
        except Exception:
            return {}

    def detect_tech_stack(self, repo) -> list:
        """Detect frameworks/tools from repo file names."""
        tech = []
        self._wait_for_rate_limit()
        try:
            contents = [f.name.lower() for f in repo.get_contents("")]
        except Exception:
            return tech
        mapping = {
            "requirements.txt": "Python",
            "pyproject.toml": "Python",
            "package.json": "Node.js",
            "dockerfile": "Docker",
            "docker-compose.yml": "Docker Compose",
            ".github": "GitHub Actions",
            "terraform.tf": "Terraform",
            "kubernetes": "Kubernetes",
            "go.mod": "Go",
            "cargo.toml": "Rust",
            "pom.xml": "Java/Maven",
            "build.gradle": "Java/Gradle",
            "gemfile": "Ruby",
            "composer.json": "PHP",
        }
        for fname, tname in mapping.items():
            if fname in contents:
                tech.append(tname)
        return tech

    def get_contribution_calendar(self, username: str) -> dict:
        """Fetch contribution calendar via GraphQL (requires token)."""
        if not self.token:
            return {}
        query = """
        query($login: String!) {
          user(login: $login) {
            contributionsCollection {
              contributionCalendar {
                totalContributions
                weeks {
                  contributionDays {
                    date
                    contributionCount
                  }
                }
              }
            }
          }
        }
        """
        try:
            r = requests.post(
                "https://api.github.com/graphql",
                headers={**self.session_headers, "Content-Type": "application/json"},
                json={"query": query, "variables": {"login": username}},
                timeout=20,
            )
            if r.status_code == 200:
                data = r.json()
                cal = (
                    data.get("data", {})
                    .get("user", {})
                    .get("contributionsCollection", {})
                    .get("contributionCalendar", {})
                )
                return cal
        except Exception as e:
            logger.warning(f"GraphQL contribution calendar failed: {e}")
        return {}


# ─────────────────────────────────────────────
#  ANALYZER
# ─────────────────────────────────────────────


class GitHubAnalyzer:
    """Aggregates and scores all fetched data."""

    def __init__(self, fetcher: GitHubFetcher):
        self.fetcher = fetcher

    def analyze(self, username: str) -> dict:
        logger.info(f"Starting analysis for: {username}")
        user = self.fetcher.get_user(username)
        logger.info("Fetching repositories…")
        repos = self.fetcher.get_repos(user)
        logger.info(f"Found {len(repos)} repositories")
        logger.info("Fetching public events…")
        events = self.fetcher.get_commit_activity(username)
        logger.info("Fetching contribution calendar…")
        cal = self.fetcher.get_contribution_calendar(username)

        profile = self._analyze_profile(user)
        repo_stats = self._analyze_repos(repos)
        language_stats = self._analyze_languages(repos)
        tech_stack = self._analyze_tech_stack(repos)
        commit_stats = self._analyze_commits(events, username)
        contribution_stats = self._analyze_contributions(events, cal)
        quality_stats = self._analyze_quality(repos)
        collab_stats = self._analyze_collaboration(user, repos, events)

        scores = self._compute_scores(
            profile,
            repo_stats,
            language_stats,
            commit_stats,
            contribution_stats,
            quality_stats,
            collab_stats,
        )

        return {
            "profile": profile,
            "repos": repo_stats,
            "languages": language_stats,
            "tech_stack": tech_stack,
            "commits": commit_stats,
            "contributions": contribution_stats,
            "quality": quality_stats,
            "collaboration": collab_stats,
            "scores": scores,
        }

    def _analyze_profile(self, user) -> dict:
        created = user.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - created).days
        return {
            "name": user.name or user.login,
            "username": user.login,
            "bio": user.bio or "",
            "avatar_url": user.avatar_url,
            "followers": user.followers,
            "following": user.following,
            "public_repos": user.public_repos,
            "public_gists": user.public_gists,
            "company": user.company or "",
            "website": user.blog or "",
            "location": user.location or "",
            "email": user.email or "",
            "joined": created.strftime("%B %d, %Y"),
            "account_age_days": age_days,
            "account_age_years": round(age_days / 365, 1),
            "hireable": user.hireable or False,
            "twitter": user.twitter_username or "",
        }

    def _analyze_repos(self, repos: list) -> dict:
        if not repos:
            return {}
        total_stars = sum(r.stargazers_count for r in repos)
        total_forks = sum(r.forks_count for r in repos)
        total_watchers = sum(r.watchers_count for r in repos)
        total_issues = sum(r.open_issues_count for r in repos)
        total_size = sum(r.size for r in repos)
        archived = [r for r in repos if r.archived]
        forked = [r for r in repos if r.fork]
        original = [r for r in repos if not r.fork]
        top_starred = sorted(repos, key=lambda r: r.stargazers_count, reverse=True)[:10]
        top_forked = sorted(repos, key=lambda r: r.forks_count, reverse=True)[:10]
        creation_years = Counter()
        for r in repos:
            if r.created_at:
                yr = r.created_at.year
                creation_years[yr] += 1
        topics_all = []
        for r in repos:
            try:
                topics_all.extend(r.get_topics())
            except Exception:
                pass
        top_topics = Counter(topics_all).most_common(15)
        return {
            "total": len(repos),
            "original": len(original),
            "forked_count": len(forked),
            "archived_count": len(archived),
            "total_stars": total_stars,
            "total_forks": total_forks,
            "total_watchers": total_watchers,
            "total_issues": total_issues,
            "total_size_mb": round(total_size / 1024, 1),
            "avg_stars": round(total_stars / max(len(repos), 1), 1),
            "top_starred": [
                {
                    "name": r.name,
                    "stars": r.stargazers_count,
                    "forks": r.forks_count,
                    "language": r.language or "N/A",
                    "description": (r.description or "")[:80],
                    "url": r.html_url,
                }
                for r in top_starred
            ],
            "top_forked": [
                {"name": r.name, "forks": r.forks_count, "url": r.html_url}
                for r in top_forked
            ],
            "creation_by_year": dict(creation_years),
            "top_topics": top_topics,
        }

    def _analyze_languages(self, repos: list) -> dict:
        lang_bytes: Counter = Counter()
        lang_repo_count: Counter = Counter()
        for repo in repos:
            if repo.fork:
                continue
            langs = self.fetcher.get_languages(repo)
            for lang, bytes_count in langs.items():
                try:
                    count = int(bytes_count)
                    lang_bytes[lang] += count
                    lang_repo_count[lang] += 1
                except (ValueError, TypeError):
                    pass
        total_bytes = sum(lang_bytes.values()) or 1
        top_langs = lang_bytes.most_common(20)
        language_pcts = {lang: round(b / total_bytes * 100, 1) for lang, b in top_langs}
        return {
            "by_bytes": dict(lang_bytes.most_common(15)),
            "by_repos": dict(lang_repo_count.most_common(15)),
            "percentages": language_pcts,
            "top_languages": [lang for lang, _ in lang_bytes.most_common(6)],
            "total_languages": len(lang_bytes),
        }

    def _analyze_tech_stack(self, repos: list) -> dict:
        all_tech: Counter = Counter()
        for repo in repos[:50]:
            if repo.fork:
                continue
            tech = self.fetcher.detect_tech_stack(repo)
            for t in tech:
                all_tech[t] += 1
        categories = {
            "backend": [],
            "frontend": [],
            "devops": [],
            "database": [],
            "cloud": [],
        }
        devops_kw = {
            "Docker",
            "Docker Compose",
            "Kubernetes",
            "Terraform",
            "GitHub Actions",
        }
        backend_kw = {
            "Python",
            "Node.js",
            "Go",
            "Rust",
            "Java/Maven",
            "Java/Gradle",
            "Ruby",
            "PHP",
        }
        frontend_kw = {"React", "Vue", "Angular", "Next.js"}
        for tech in all_tech:
            if tech in devops_kw:
                categories["devops"].append(tech)
            elif tech in backend_kw:
                categories["backend"].append(tech)
            elif tech in frontend_kw:
                categories["frontend"].append(tech)
        return {
            "all_tech": dict(all_tech.most_common(20)),
            "categories": categories,
            "top_tech": [t for t, _ in all_tech.most_common(8)],
        }

    def _analyze_commits(self, events: list, username: str) -> dict:
        push_events = [e for e in events if e.get("type") == "PushEvent"]
        hour_counter: Counter = Counter()
        day_counter: Counter = Counter()
        month_counter: Counter = Counter()
        dates = []
        for event in push_events:
            ts = event.get("created_at", "")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                hour_counter[dt.hour] += 1
                day_counter[dt.strftime("%A")] += 1
                month_counter[dt.strftime("%Y-%m")] += 1
                dates.append(dt)
            except Exception:
                pass
        total_commits = sum(e.get("payload", {}).get("size", 0) for e in push_events)
        most_active_hour = (
            max(hour_counter, key=hour_counter.get) if hour_counter else 12
        )
        most_active_day = (
            max(day_counter, key=day_counter.get) if day_counter else "Monday"
        )
        day_order = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        day_counts = {d: day_counter.get(d, 0) for d in day_order}
        hour_counts = {h: hour_counter.get(h, 0) for h in range(24)}
        return {
            "total_commits_from_events": total_commits,
            "push_events": len(push_events),
            "most_active_hour": most_active_hour,
            "most_active_day": most_active_day,
            "day_distribution": day_counts,
            "hour_distribution": hour_counts,
            "monthly_trend": dict(month_counter.most_common(12)),
        }

    def _analyze_contributions(self, events: list, cal: dict) -> dict:
        total_contributions = cal.get("totalContributions", 0)
        days_data = []
        if cal.get("weeks"):
            for week in cal["weeks"]:
                for day in week.get("contributionDays", []):
                    days_data.append(
                        {
                            "date": day["date"],
                            "count": day["contributionCount"],
                        }
                    )
        # Contribution streak
        streak = 0
        max_streak = 0
        current_streak = 0
        if days_data:
            for d in sorted(days_data, key=lambda x: x["date"]):
                if d["count"] > 0:
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 0
            streak = current_streak
        # Monthly aggregation
        monthly: Counter = Counter()
        for d in days_data:
            month = d["date"][:7]
            monthly[month] += d["count"]
        event_dates = Counter()
        for e in events:
            ts = e.get("created_at", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    event_dates[dt.strftime("%Y-%m-%d")] += 1
                except Exception:
                    pass
        return {
            "total": total_contributions,
            "current_streak": streak,
            "max_streak": max_streak,
            "heatmap_data": days_data[-365:] if days_data else [],
            "monthly_trend": dict(monthly.most_common(12)),
            "active_days": sum(1 for d in days_data if d["count"] > 0),
        }

    def _analyze_quality(self, repos: list) -> dict:
        scores = []
        for repo in repos[:30]:
            if repo.fork:
                continue
            score = 0
            try:
                contents = [f.name.lower() for f in repo.get_contents("")]
                if "readme.md" in contents or "readme.rst" in contents:
                    score += 20
                if repo.license:
                    score += 15
                if ".github" in contents:
                    score += 15
                if "dockerfile" in contents:
                    score += 10
                if repo.description:
                    score += 10
                try:
                    topics = repo.get_topics()
                    if topics:
                        score += 10
                except Exception:
                    pass
                if any(
                    t in contents
                    for t in ["test", "tests", "spec", "specs", "__tests__"]
                ):
                    score += 10
                if repo.stargazers_count > 0:
                    score += min(10, repo.stargazers_count)
            except Exception:
                score = 30
            scores.append(
                {"name": repo.name, "score": min(100, score), "url": repo.html_url}
            )
        avg_score = round(sum(s["score"] for s in scores) / max(len(scores), 1))
        top_quality = sorted(scores, key=lambda x: x["score"], reverse=True)[:5]
        return {
            "average_score": avg_score,
            "top_repos": top_quality,
            "repos_analyzed": len(scores),
        }

    def _analyze_collaboration(self, user, repos: list, events: list) -> dict:
        pr_events = [e for e in events if e.get("type") == "PullRequestEvent"]
        issue_events = [e for e in events if e.get("type") == "IssuesEvent"]
        review_events = [e for e in events if e.get("type") == "PullRequestReviewEvent"]
        follower_ratio = (
            round(user.followers / max(user.following, 1), 2)
            if user.following
            else user.followers
        )
        return {
            "pull_requests": len(pr_events),
            "issues": len(issue_events),
            "reviews": len(review_events),
            "forks_received": sum(r.forks_count for r in repos),
            "follower_to_following_ratio": follower_ratio,
            "followers": user.followers,
            "following": user.following,
        }

    def _compute_scores(
        self, profile, repos, languages, commits, contributions, quality, collab
    ) -> dict:
        # Profile score
        p_score = 0
        if profile.get("bio"):
            p_score += 10
        if profile.get("website"):
            p_score += 10
        if profile.get("location"):
            p_score += 10
        p_score += min(30, profile.get("followers", 0) // 10)
        p_score += min(20, profile.get("public_repos", 0))
        p_score += min(20, profile.get("account_age_years", 0) * 4)
        profile_score = min(100, p_score)

        # Productivity score
        prod_score = 0
        prod_score += min(30, repos.get("total", 0))
        prod_score += min(20, repos.get("total_stars", 0) // 10)
        prod_score += min(25, commits.get("push_events", 0) // 5)
        prod_score += min(25, contributions.get("total", 0) // 50)
        productivity_score = min(100, prod_score)

        # Collaboration score
        col_score = 0
        col_score += min(30, collab.get("followers", 0) // 5)
        col_score += min(20, collab.get("pull_requests", 0) * 5)
        col_score += min(20, collab.get("issues", 0) * 3)
        col_score += min(20, collab.get("forks_received", 0) // 5)
        col_score += min(10, collab.get("reviews", 0) * 5)
        collaboration_score = min(100, col_score)

        return {
            "profile_score": profile_score,
            "productivity_score": productivity_score,
            "collaboration_score": collaboration_score,
            "quality_score": quality.get("average_score", 50),
            "overall": round(
                (
                    profile_score
                    + productivity_score
                    + collaboration_score
                    + quality.get("average_score", 50)
                )
                / 4
            ),
        }


# ─────────────────────────────────────────────
#  CHART GENERATOR
# ─────────────────────────────────────────────


class ChartGenerator:
    """Generates Plotly charts as JSON for inline HTML embedding."""

    @staticmethod
    def _fig_to_json(fig) -> str:
        return pio.to_json(fig)

    def language_donut(self, language_data: dict) -> str:
        pcts = language_data.get("percentages", {})
        if not pcts:
            return "{}"
        labels = list(pcts.keys())[:10]
        values = [pcts[label] for label in labels]
        colors = [
            "#00D8FF",
            "#F7E018",
            "#3178C6",
            "#00ADD8",
            "#B07219",
            "#E34C26",
            "#563D7C",
            "#F1502F",
            "#00A88E",
            "#CC342D",
        ]
        fig = go.Figure(
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker=dict(
                    colors=colors[: len(labels)], line=dict(color="#0d1117", width=2)
                ),
                textinfo="label+percent",
                textfont=dict(color="#e6edf3", size=11),
            )
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"),
            showlegend=False,
            margin=dict(l=10, r=10, t=10, b=10),
            height=320,
        )
        return self._fig_to_json(fig)

    def commit_heatmap(self, heatmap_data: list) -> str:
        if not heatmap_data:
            return "{}"
        df = pd.DataFrame(heatmap_data)
        if df.empty:
            return "{}"
        df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=False)
        df["week"] = df["date"].dt.isocalendar().week.astype(str)
        df["day"] = df["date"].dt.day_name()
        day_order = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        df["day"] = pd.Categorical(
            df["date"].dt.day_name(), categories=day_order, ordered=True
        )
        pivot = df.pivot_table(
            index="day", columns="date", values="count", fill_value=0
        )
        z = pivot.values.tolist()
        x = [str(c.date()) for c in pivot.columns]
        y = list(pivot.index)
        fig = go.Figure(
            go.Heatmap(
                z=z,
                x=x,
                y=y,
                colorscale=[
                    [0, "#0d1117"],
                    [0.01, "#0e4429"],
                    [0.3, "#006d32"],
                    [0.7, "#26a641"],
                    [1, "#39d353"],
                ],
                showscale=False,
                xgap=2,
                ygap=2,
                hovertemplate="%{x}: %{z} contributions<extra></extra>",
            )
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3", size=10),
            margin=dict(l=60, r=10, t=10, b=30),
            height=160,
            xaxis=dict(showgrid=False, tickfont=dict(size=9)),
            yaxis=dict(showgrid=False),
        )
        return self._fig_to_json(fig)

    def commit_hour_bar(self, hour_dist: dict) -> str:
        hours = list(range(24))
        counts = [hour_dist.get(h, 0) for h in hours]
        labels = [f"{h:02d}:00" for h in hours]
        fig = go.Figure(
            go.Bar(
                x=labels,
                y=counts,
                marker=dict(
                    color=counts,
                    colorscale=[[0, "#1c2128"], [0.5, "#1f6feb"], [1, "#58a6ff"]],
                    showscale=False,
                ),
                hovertemplate="%{x}: %{y} commits<extra></extra>",
            )
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"),
            margin=dict(l=30, r=10, t=10, b=40),
            height=220,
            xaxis=dict(showgrid=False, tickangle=45, tickfont=dict(size=9)),
            yaxis=dict(showgrid=True, gridcolor="#21262d"),
        )
        return self._fig_to_json(fig)

    def repo_growth_chart(self, creation_by_year: dict) -> str:
        if not creation_by_year:
            return "{}"
        years = sorted(creation_by_year.keys())
        counts = [creation_by_year[y] for y in years]
        cumulative = []
        total = 0
        for c in counts:
            total += c
            cumulative.append(total)
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=years,
                y=counts,
                name="New Repos",
                marker_color="#1f6feb",
                opacity=0.7,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=years,
                y=cumulative,
                name="Total Repos",
                line=dict(color="#58a6ff", width=2),
                mode="lines+markers",
                yaxis="y2",
            )
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"),
            margin=dict(l=40, r=40, t=10, b=40),
            height=250,
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#21262d", title="New"),
            yaxis2=dict(overlaying="y", side="right", showgrid=False, title="Total"),
            legend=dict(x=0.02, y=0.98, bgcolor="rgba(0,0,0,0)"),
            barmode="group",
        )
        return self._fig_to_json(fig)

    def radar_chart(self, scores: dict) -> str:
        categories = [
            "Profile",
            "Productivity",
            "Collaboration",
            "Code Quality",
            "Activity",
        ]
        values = [
            scores.get("profile_score", 0),
            scores.get("productivity_score", 0),
            scores.get("collaboration_score", 0),
            scores.get("quality_score", 0),
            min(100, scores.get("productivity_score", 0) + 10),
        ]
        fig = go.Figure(
            go.Scatterpolar(
                r=values + [values[0]],
                theta=categories + [categories[0]],
                fill="toself",
                fillcolor="rgba(31, 111, 235, 0.2)",
                line=dict(color="#58a6ff", width=2),
                marker=dict(size=6, color="#58a6ff"),
            )
        )
        fig.update_layout(
            polar=dict(
                bgcolor="rgba(0,0,0,0)",
                radialaxis=dict(
                    visible=True,
                    range=[0, 100],
                    gridcolor="#21262d",
                    tickfont=dict(color="#8b949e", size=9),
                    linecolor="#21262d",
                ),
                angularaxis=dict(
                    gridcolor="#21262d",
                    tickfont=dict(color="#e6edf3", size=11),
                    linecolor="#21262d",
                ),
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"),
            margin=dict(l=50, r=50, t=30, b=30),
            height=300,
            showlegend=False,
        )
        return self._fig_to_json(fig)

    def monthly_contributions(self, monthly_trend: dict) -> str:
        if not monthly_trend:
            return "{}"
        sorted_months = sorted(monthly_trend.keys())[-12:]
        values = [monthly_trend[m] for m in sorted_months]
        fig = go.Figure(
            go.Scatter(
                x=sorted_months,
                y=values,
                fill="tozeroy",
                fillcolor="rgba(31, 111, 235, 0.15)",
                line=dict(color="#1f6feb", width=2),
                mode="lines",
                hovertemplate="%{x}: %{y} contributions<extra></extra>",
            )
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"),
            margin=dict(l=40, r=10, t=10, b=40),
            height=200,
            xaxis=dict(showgrid=False, tickangle=45, tickfont=dict(size=9)),
            yaxis=dict(showgrid=True, gridcolor="#21262d"),
        )
        return self._fig_to_json(fig)

    def weekday_bar(self, day_dist: dict) -> str:
        day_order = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        counts = [day_dist.get(d, 0) for d in day_order]
        short_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        colors = ["#1f6feb" if i < 5 else "#388bfd" for i in range(7)]
        fig = go.Figure(
            go.Bar(
                x=short_days,
                y=counts,
                marker_color=colors,
                hovertemplate="%{x}: %{y} pushes<extra></extra>",
            )
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"),
            margin=dict(l=30, r=10, t=10, b=30),
            height=200,
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#21262d"),
        )
        return self._fig_to_json(fig)


# ─────────────────────────────────────────────
#  HTML REPORT GENERATOR
# ─────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{{ profile.name }} — GitHub Analytics</title>
<script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Outfit:wght@300;400;500;600;700&display=swap');
  :root {
    --bg: #0d1117;
    --surface: #161b22;
    --surface2: #1c2128;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --blue: #1f6feb;
    --blue-light: #58a6ff;
    --green: #2ea043;
    --green-light: #3fb950;
    --orange: #d29922;
    --red: #f85149;
    --purple: #8957e5;
    --mono: 'JetBrains Mono', monospace;
    --sans: 'Outfit', sans-serif;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { scroll-behavior: smooth; }
  body {
    font-family: var(--sans);
    background: var(--bg);
    color: var(--text);
    display: flex;
    min-height: 100vh;
  }
  /* ── Sidebar ── */
  .sidebar {
    width: 220px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    position: fixed;
    top: 0; left: 0; bottom: 0;
    padding: 24px 0;
    display: flex;
    flex-direction: column;
    z-index: 100;
    overflow-y: auto;
  }
  .sidebar-logo {
    padding: 0 20px 24px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 16px;
  }
  .sidebar-logo .octocat { font-size: 28px; }
  .sidebar-logo h2 {
    font-size: 13px;
    font-weight: 600;
    color: var(--blue-light);
    letter-spacing: 0.5px;
    margin-top: 4px;
    font-family: var(--mono);
  }
  .nav-section {
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin: 12px 0 4px;
  }
  .nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 20px;
    color: var(--muted);
    text-decoration: none;
    font-size: 13.5px;
    font-weight: 400;
    transition: all .15s;
    cursor: pointer;
    border-left: 2px solid transparent;
  }
  .nav-item:hover, .nav-item.active {
    color: var(--text);
    background: var(--surface2);
    border-left-color: var(--blue-light);
  }
  .nav-icon { width: 16px; text-align: center; font-size: 14px; }
  /* ── Main ── */
  .main {
    margin-left: 220px;
    flex: 1;
    padding: 32px;
    max-width: 1200px;
  }
  /* ── Section ── */
  .section {
    margin-bottom: 40px;
    scroll-margin-top: 24px;
  }
  .section-title {
    font-size: 20px;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .section-title .icon { font-size: 20px; }
  /* ── Cards ── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
  }
  .card-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .8px;
    margin-bottom: 12px;
  }
  /* ── Hero ── */
  .hero {
    background: linear-gradient(135deg, var(--surface) 0%, #12191f 100%);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 32px;
    display: flex;
    gap: 28px;
    align-items: flex-start;
    margin-bottom: 40px;
    position: relative;
    overflow: hidden;
  }
  .hero::before {
    content: '';
    position: absolute;
    top: -40px; right: -40px;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(31,111,235,.15) 0%, transparent 70%);
  }
  .avatar {
    width: 96px; height: 96px;
    border-radius: 50%;
    border: 3px solid var(--border);
    flex-shrink: 0;
  }
  .hero-info { flex: 1; }
  .hero-name {
    font-size: 28px; font-weight: 700;
    color: var(--text); line-height: 1.2;
  }
  .hero-username {
    font-size: 16px; color: var(--blue-light);
    font-family: var(--mono); margin-bottom: 8px;
  }
  .hero-bio {
    font-size: 14px; color: var(--muted);
    line-height: 1.6; margin-bottom: 14px; max-width: 600px;
  }
  .hero-meta {
    display: flex; flex-wrap: wrap; gap: 16px;
  }
  .hero-meta-item {
    display: flex; align-items: center; gap: 6px;
    font-size: 13px; color: var(--muted);
  }
  .hero-scores {
    display: flex; flex-direction: column; gap: 10px; min-width: 160px;
  }
  .score-item { }
  .score-label {
    font-size: 11px; color: var(--muted);
    text-transform: uppercase; letter-spacing: .6px; margin-bottom: 4px;
  }
  .score-bar-wrap {
    background: var(--surface2);
    border-radius: 4px; height: 6px; overflow: hidden;
  }
  .score-bar {
    height: 100%; border-radius: 4px;
    background: linear-gradient(90deg, var(--blue), var(--blue-light));
    transition: width 1s ease;
  }
  .score-val {
    font-family: var(--mono);
    font-size: 11px; color: var(--blue-light);
    text-align: right; margin-top: 2px;
  }
  /* ── Stat grid ── */
  .stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 16px;
  }
  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px 20px;
    position: relative;
    overflow: hidden;
    transition: border-color .2s, transform .2s;
  }
  .stat-card:hover {
    border-color: var(--blue);
    transform: translateY(-2px);
  }
  .stat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 2px;
  }
  .stat-card.blue::before { background: var(--blue-light); }
  .stat-card.green::before { background: var(--green-light); }
  .stat-card.orange::before { background: var(--orange); }
  .stat-card.purple::before { background: var(--purple); }
  .stat-card.red::before { background: var(--red); }
  .stat-icon { font-size: 22px; margin-bottom: 8px; }
  .stat-value {
    font-family: var(--mono); font-size: 26px; font-weight: 600;
    color: var(--text); line-height: 1;
  }
  .stat-label {
    font-size: 12px; color: var(--muted);
    margin-top: 4px; font-weight: 400;
  }
  /* ── Charts grid ── */
  .charts-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 20px;
  }
  .charts-grid.three { grid-template-columns: repeat(3, 1fr); }
  .charts-grid.full { grid-template-columns: 1fr; }
  /* ── Repo table ── */
  .repo-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
  }
  .repo-table th {
    text-align: left;
    padding: 10px 14px;
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .6px;
    border-bottom: 1px solid var(--border);
  }
  .repo-table td {
    padding: 11px 14px;
    border-bottom: 1px solid var(--surface2);
    vertical-align: middle;
  }
  .repo-table tr:last-child td { border-bottom: none; }
  .repo-table tr:hover td { background: var(--surface2); }
  .repo-name a {
    color: var(--blue-light); text-decoration: none;
    font-family: var(--mono); font-weight: 500;
  }
  .repo-name a:hover { text-decoration: underline; }
  .repo-desc { color: var(--muted); font-size: 12px; margin-top: 2px; }
  .lang-dot {
    width: 10px; height: 10px; border-radius: 50%;
    display: inline-block; margin-right: 5px;
  }
  .badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: 20px;
    font-size: 11px; font-weight: 500;
    border: 1px solid;
  }
  .badge-blue { color: var(--blue-light); border-color: rgba(88,166,255,.3); background: rgba(31,111,235,.1); }
  .badge-green { color: var(--green-light); border-color: rgba(63,185,80,.3); background: rgba(46,160,67,.1); }
  .badge-orange { color: var(--orange); border-color: rgba(210,153,34,.3); background: rgba(210,153,34,.1); }
  /* ── Tech tags ── */
  .tech-grid { display: flex; flex-wrap: wrap; gap: 8px; }
  .tech-tag {
    padding: 5px 12px; border-radius: 6px;
    font-size: 12.5px; font-family: var(--mono);
    background: var(--surface2); border: 1px solid var(--border);
    color: var(--text); display: flex; align-items: center; gap: 6px;
  }
  .tech-count {
    font-size: 10px; color: var(--muted);
    background: var(--surface); border-radius: 4px;
    padding: 1px 5px;
  }
  /* ── Streak ── */
  .streak-box {
    display: flex; gap: 20px; flex-wrap: wrap;
  }
  .streak-item {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px 24px;
    text-align: center;
    flex: 1; min-width: 120px;
  }
  .streak-val {
    font-family: var(--mono); font-size: 36px; font-weight: 700;
    color: var(--green-light); line-height: 1;
  }
  .streak-label { font-size: 12px; color: var(--muted); margin-top: 6px; }
  /* ── Recommendations ── */
  .rec-list { display: flex; flex-direction: column; gap: 10px; }
  .rec-item {
    display: flex; gap: 12px; align-items: flex-start;
    padding: 14px 16px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    border-left: 3px solid var(--blue);
  }
  .rec-icon { font-size: 18px; flex-shrink: 0; margin-top: 1px; }
  .rec-content {}
  .rec-title { font-size: 14px; font-weight: 500; color: var(--text); margin-bottom: 3px; }
  .rec-desc { font-size: 12.5px; color: var(--muted); line-height: 1.5; }
  /* ── Footer ── */
  .footer {
    margin-top: 60px; padding: 24px 0;
    border-top: 1px solid var(--border);
    font-size: 12px; color: var(--muted);
    text-align: center;
  }
  /* ── Divider ── */
  .divider { height: 1px; background: var(--border); margin: 4px 0 20px; }
  /* ── Overall badge ── */
  .overall-badge {
    display: inline-flex; align-items: center; gap: 8px;
    background: linear-gradient(135deg, #1f6feb, #388bfd);
    color: white; padding: 6px 14px; border-radius: 20px;
    font-size: 13px; font-weight: 600;
    margin-left: auto;
  }
  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--muted); }
</style>
</head>
<body>

<nav class="sidebar">
  <div class="sidebar-logo">
    <div class="octocat">🐙</div>
    <h2>GH·ANALYTICS</h2>
  </div>
  <span class="nav-section">Overview</span>
  <a class="nav-item active" href="#profile">
    <span class="nav-icon">👤</span> Profile
  </a>
  <a class="nav-item" href="#stats">
    <span class="nav-icon">📊</span> Stats
  </a>
  <span class="nav-section">Activity</span>
  <a class="nav-item" href="#contributions">
    <span class="nav-icon">🟩</span> Contributions
  </a>
  <a class="nav-item" href="#commits">
    <span class="nav-icon">🔀</span> Commit Patterns
  </a>
  <span class="nav-section">Code</span>
  <a class="nav-item" href="#languages">
    <span class="nav-icon">🌐</span> Languages
  </a>
  <a class="nav-item" href="#techstack">
    <span class="nav-icon">⚙️</span> Tech Stack
  </a>
  <span class="nav-section">Repositories</span>
  <a class="nav-item" href="#repositories">
    <span class="nav-icon">📁</span> Top Repos
  </a>
  <a class="nav-item" href="#quality">
    <span class="nav-icon">✅</span> Code Quality
  </a>
  <span class="nav-section">Insights</span>
  <a class="nav-item" href="#collaboration">
    <span class="nav-icon">🤝</span> Collaboration
  </a>
  <a class="nav-item" href="#radar">
    <span class="nav-icon">🎯</span> Radar
  </a>
  <a class="nav-item" href="#recommendations">
    <span class="nav-icon">💡</span> Recommendations
  </a>
</nav>

<main class="main">

  <!-- HERO -->
  <div class="hero" id="profile">
    <img class="avatar" src="{{ profile.avatar_url }}" alt="{{ profile.name }}" onerror="this.src='https://github.com/identicons/{{ profile.username }}.png'"/>
    <div class="hero-info">
      <div class="hero-name">{{ profile.name }}</div>
      <div class="hero-username">@{{ profile.username }}</div>
      {% if profile.bio %}<div class="hero-bio">{{ profile.bio }}</div>{% endif %}
      <div class="hero-meta">
        {% if profile.company %}<span class="hero-meta-item">🏢 {{ profile.company }}</span>{% endif %}
        {% if profile.location %}<span class="hero-meta-item">📍 {{ profile.location }}</span>{% endif %}
        {% if profile.website %}<span class="hero-meta-item">🔗 <a href="{{ profile.website }}" style="color:var(--blue-light)">{{ profile.website }}</a></span>{% endif %}
        <span class="hero-meta-item">📅 Joined {{ profile.joined }}</span>
        <span class="hero-meta-item">⏱️ {{ profile.account_age_years }}y on GitHub</span>
      </div>
    </div>
    <div class="hero-scores">
      <div class="overall-badge">⭐ {{ scores.overall }}/100</div>
      {% for label, key, color in [('Profile', 'profile_score', '#58a6ff'), ('Productivity', 'productivity_score', '#3fb950'), ('Collaboration', 'collaboration_score', '#d29922'), ('Quality', 'quality_score', '#8957e5')] %}
      <div class="score-item" style="margin-top:8px">
        <div class="score-label">{{ label }}</div>
        <div class="score-bar-wrap">
          <div class="score-bar" style="width:{{ scores[key] }}%; background:linear-gradient(90deg,{{ color }},{{ color }}cc)"></div>
        </div>
        <div class="score-val">{{ scores[key] }}/100</div>
      </div>
      {% endfor %}
    </div>
  </div>

  <!-- STATS -->
  <section class="section" id="stats">
    <div class="section-title"><span class="icon">📊</span> Key Metrics</div>
    <div class="stat-grid">
      <div class="stat-card blue">
        <div class="stat-icon">📦</div>
        <div class="stat-value">{{ profile.public_repos }}</div>
        <div class="stat-label">Public Repos</div>
      </div>
      <div class="stat-card green">
        <div class="stat-icon">⭐</div>
        <div class="stat-value">{{ repos.total_stars }}</div>
        <div class="stat-label">Total Stars</div>
      </div>
      <div class="stat-card orange">
        <div class="stat-icon">🍴</div>
        <div class="stat-value">{{ repos.total_forks }}</div>
        <div class="stat-label">Total Forks</div>
      </div>
      <div class="stat-card blue">
        <div class="stat-icon">👥</div>
        <div class="stat-value">{{ profile.followers }}</div>
        <div class="stat-label">Followers</div>
      </div>
      <div class="stat-card purple">
        <div class="stat-icon">💚</div>
        <div class="stat-value">{{ contributions.total }}</div>
        <div class="stat-label">Contributions</div>
      </div>
      <div class="stat-card green">
        <div class="stat-icon">🔥</div>
        <div class="stat-value">{{ contributions.max_streak }}</div>
        <div class="stat-label">Max Streak</div>
      </div>
      <div class="stat-card orange">
        <div class="stat-icon">🌍</div>
        <div class="stat-value">{{ languages.total_languages }}</div>
        <div class="stat-label">Languages</div>
      </div>
      <div class="stat-card red">
        <div class="stat-icon">💾</div>
        <div class="stat-value">{{ repos.total_size_mb }}</div>
        <div class="stat-label">Repo Size (MB)</div>
      </div>
    </div>
  </section>

  <!-- CONTRIBUTIONS -->
  <section class="section" id="contributions">
    <div class="section-title"><span class="icon">🟩</span> Contribution Activity</div>
    {% if contributions.heatmap_data %}
    <div class="card" style="margin-bottom:20px">
      <div class="card-title">Contribution Heatmap (Last Year)</div>
      <div id="chart-heatmap"></div>
    </div>
    {% endif %}
    <div class="streak-box" style="margin-bottom:20px">
      <div class="streak-item">
        <div class="streak-val">{{ contributions.total }}</div>
        <div class="streak-label">Total Contributions</div>
      </div>
      <div class="streak-item">
        <div class="streak-val">{{ contributions.current_streak }}</div>
        <div class="streak-label">Current Streak</div>
      </div>
      <div class="streak-item">
        <div class="streak-val">{{ contributions.max_streak }}</div>
        <div class="streak-label">Longest Streak</div>
      </div>
      <div class="streak-item">
        <div class="streak-val">{{ contributions.active_days }}</div>
        <div class="streak-label">Active Days</div>
      </div>
    </div>
    {% if contributions.monthly_trend %}
    <div class="card">
      <div class="card-title">Monthly Contribution Trend</div>
      <div id="chart-monthly-contrib"></div>
    </div>
    {% endif %}
  </section>

  <!-- COMMIT PATTERNS -->
  <section class="section" id="commits">
    <div class="section-title"><span class="icon">🔀</span> Commit Patterns</div>
    <div class="charts-grid">
      <div class="card">
        <div class="card-title">Commits by Hour of Day</div>
        <div id="chart-hours"></div>
      </div>
      <div class="card">
        <div class="card-title">Pushes by Weekday</div>
        <div id="chart-weekdays"></div>
      </div>
    </div>
    <div style="margin-top:16px; display:flex; gap:16px; flex-wrap:wrap;">
      <div class="card" style="flex:1;min-width:200px">
        <div class="card-title">Most Active Hour</div>
        <div style="font-family:var(--mono);font-size:32px;color:var(--blue-light)">{{ '%02d'|format(commits.most_active_hour) }}:00</div>
        <div style="font-size:12px;color:var(--muted);margin-top:4px">Peak coding time</div>
      </div>
      <div class="card" style="flex:1;min-width:200px">
        <div class="card-title">Most Active Day</div>
        <div style="font-family:var(--mono);font-size:28px;color:var(--green-light)">{{ commits.most_active_day }}</div>
        <div style="font-size:12px;color:var(--muted);margin-top:4px">Most productive day</div>
      </div>
      <div class="card" style="flex:1;min-width:200px">
        <div class="card-title">Push Events (30d)</div>
        <div style="font-family:var(--mono);font-size:32px;color:var(--orange)">{{ commits.push_events }}</div>
        <div style="font-size:12px;color:var(--muted);margin-top:4px">From recent activity</div>
      </div>
    </div>
  </section>

  <!-- LANGUAGES -->
  <section class="section" id="languages">
    <div class="section-title"><span class="icon">🌐</span> Language Distribution</div>
    <div class="charts-grid">
      <div class="card">
        <div class="card-title">By Code Volume</div>
        <div id="chart-languages"></div>
      </div>
      <div class="card">
        <div class="card-title">Language Breakdown</div>
        {% for lang, pct in languages.percentages.items() %}
        <div style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;margin-bottom:4px">
            <span style="font-size:13px;font-family:var(--mono)">{{ lang }}</span>
            <span style="font-size:12px;color:var(--muted)">{{ pct }}%</span>
          </div>
          <div style="background:var(--surface2);border-radius:4px;height:6px;overflow:hidden">
            <div style="width:{{ [pct, 100]|min }}%;height:100%;border-radius:4px;background:linear-gradient(90deg,var(--blue),var(--blue-light))"></div>
          </div>
        </div>
        {% endfor %}
      </div>
    </div>
  </section>

  <!-- TECH STACK -->
  <section class="section" id="techstack">
    <div class="section-title"><span class="icon">⚙️</span> Technology Stack</div>
    <div class="card">
      <div class="card-title">Detected Technologies</div>
      <div class="tech-grid">
        {% for tech, count in tech_stack.all_tech.items() %}
        <div class="tech-tag">
          {{ tech }}
          <span class="tech-count">{{ count }}</span>
        </div>
        {% endfor %}
        {% if not tech_stack.all_tech %}
        <div style="color:var(--muted);font-size:13px">No technology files detected in public repositories.</div>
        {% endif %}
      </div>
    </div>
    {% if tech_stack.categories %}
    <div class="charts-grid" style="margin-top:16px">
      {% for cat, items in tech_stack.categories.items() %}
      {% if items %}
      <div class="card">
        <div class="card-title">{{ cat|title }}</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">
          {% for item in items %}
          <span class="badge badge-blue">{{ item }}</span>
          {% endfor %}
        </div>
      </div>
      {% endif %}
      {% endfor %}
    </div>
    {% endif %}
  </section>

  <!-- REPOSITORIES -->
  <section class="section" id="repositories">
    <div class="section-title">
      <span class="icon">📁</span> Top Repositories
      <span class="badge badge-blue" style="margin-left:8px">{{ repos.total }} total</span>
    </div>
    <div class="card" style="margin-bottom:20px">
      <div class="card-title">Repo Growth Over Time</div>
      <div id="chart-repo-growth"></div>
    </div>
    <div class="card">
      <div class="card-title">Most Starred Repositories</div>
      <table class="repo-table">
        <thead>
          <tr>
            <th>Repository</th>
            <th>Language</th>
            <th>⭐ Stars</th>
            <th>🍴 Forks</th>
          </tr>
        </thead>
        <tbody>
          {% for r in repos.top_starred %}
          <tr>
            <td class="repo-name">
              <a href="{{ r.url }}" target="_blank">{{ r.name }}</a>
              {% if r.description %}<div class="repo-desc">{{ r.description }}</div>{% endif %}
            </td>
            <td>
              {% if r.language and r.language != 'N/A' %}
              <span style="font-size:12px;font-family:var(--mono)">{{ r.language }}</span>
              {% else %}
              <span style="color:var(--muted);font-size:12px">—</span>
              {% endif %}
            </td>
            <td><span class="badge badge-orange">⭐ {{ r.stars }}</span></td>
            <td><span class="badge badge-blue">🍴 {{ r.forks }}</span></td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% if repos.top_topics %}
    <div class="card" style="margin-top:16px">
      <div class="card-title">Popular Topics</div>
      <div class="tech-grid">
        {% for topic, count in repos.top_topics %}
        <div class="tech-tag">{{ topic }}<span class="tech-count">{{ count }}</span></div>
        {% endfor %}
      </div>
    </div>
    {% endif %}
  </section>

  <!-- QUALITY -->
  <section class="section" id="quality">
    <div class="section-title"><span class="icon">✅</span> Code Quality Metrics</div>
    <div class="stat-grid" style="margin-bottom:20px">
      <div class="stat-card green">
        <div class="stat-icon">🏆</div>
        <div class="stat-value">{{ quality.average_score }}</div>
        <div class="stat-label">Avg Quality Score</div>
      </div>
      <div class="stat-card blue">
        <div class="stat-icon">🔍</div>
        <div class="stat-value">{{ quality.repos_analyzed }}</div>
        <div class="stat-label">Repos Analyzed</div>
      </div>
    </div>
    {% if quality.top_repos %}
    <div class="card">
      <div class="card-title">Highest Quality Repositories</div>
      <table class="repo-table">
        <thead>
          <tr><th>Repository</th><th>Quality Score</th></tr>
        </thead>
        <tbody>
          {% for r in quality.top_repos %}
          <tr>
            <td><a href="{{ r.url }}" target="_blank" style="color:var(--blue-light);font-family:var(--mono)">{{ r.name }}</a></td>
            <td>
              <div style="display:flex;align-items:center;gap:10px">
                <div style="flex:1;background:var(--surface2);border-radius:4px;height:6px;overflow:hidden;max-width:120px">
                  <div style="width:{{ r.score }}%;height:100%;border-radius:4px;background:linear-gradient(90deg,var(--green),var(--green-light))"></div>
                </div>
                <span style="font-family:var(--mono);font-size:13px;color:var(--green-light)">{{ r.score }}/100</span>
              </div>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% endif %}
  </section>

  <!-- COLLABORATION -->
  <section class="section" id="collaboration">
    <div class="section-title"><span class="icon">🤝</span> Collaboration & Community</div>
    <div class="stat-grid">
      <div class="stat-card blue">
        <div class="stat-icon">👥</div>
        <div class="stat-value">{{ collaboration.followers }}</div>
        <div class="stat-label">Followers</div>
      </div>
      <div class="stat-card green">
        <div class="stat-icon">👁️</div>
        <div class="stat-value">{{ collaboration.following }}</div>
        <div class="stat-label">Following</div>
      </div>
      <div class="stat-card orange">
        <div class="stat-icon">🔄</div>
        <div class="stat-value">{{ collaboration.pull_requests }}</div>
        <div class="stat-label">Pull Requests</div>
      </div>
      <div class="stat-card purple">
        <div class="stat-icon">🐛</div>
        <div class="stat-value">{{ collaboration.issues }}</div>
        <div class="stat-label">Issues Created</div>
      </div>
      <div class="stat-card blue">
        <div class="stat-icon">🍴</div>
        <div class="stat-value">{{ collaboration.forks_received }}</div>
        <div class="stat-label">Forks Received</div>
      </div>
      <div class="stat-card green">
        <div class="stat-icon">📈</div>
        <div class="stat-value">{{ collaboration.follower_to_following_ratio }}</div>
        <div class="stat-label">Follower Ratio</div>
      </div>
    </div>
  </section>

  <!-- RADAR -->
  <section class="section" id="radar">
    <div class="section-title"><span class="icon">🎯</span> Developer Expertise Radar</div>
    <div class="card">
      <div id="chart-radar"></div>
    </div>
  </section>

  <!-- RECOMMENDATIONS -->
  <section class="section" id="recommendations">
    <div class="section-title"><span class="icon">💡</span> Recommendations</div>
    <div class="rec-list" id="rec-list">
      <!-- Populated by JS -->
    </div>
  </section>

  <div class="footer">
    Generated by GitHub Analytics Dashboard · {{ generated_at }} · @{{ profile.username }}
  </div>

</main>

<script>
// ── Plotly chart rendering ──
const charts = {
  heatmap:        {{ chart_heatmap | safe }},
  monthly_contrib:{{ chart_monthly_contrib | safe }},
  hours:          {{ chart_hours | safe }},
  weekdays:       {{ chart_weekdays | safe }},
  languages:      {{ chart_languages | safe }},
  repo_growth:    {{ chart_repo_growth | safe }},
  radar:          {{ chart_radar | safe }},
};

const cfg = {responsive: true, displayModeBar: false};

function renderChart(id, data) {
  if (!data || !data.data) return;
  const el = document.getElementById(id);
  if (!el) return;
  Plotly.newPlot(el, data.data, data.layout || {}, cfg);
}

renderChart('chart-heatmap',        charts.heatmap);
renderChart('chart-monthly-contrib',charts.monthly_contrib);
renderChart('chart-hours',          charts.hours);
renderChart('chart-weekdays',       charts.weekdays);
renderChart('chart-languages',      charts.languages);
renderChart('chart-repo-growth',    charts.repo_growth);
renderChart('chart-radar',          charts.radar);

// ── Sidebar active nav ──
const navItems = document.querySelectorAll('.nav-item');
const sections = document.querySelectorAll('.section, .hero');
const observer = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      navItems.forEach(n => {
        n.classList.toggle('active', n.getAttribute('href') === '#' + e.target.id);
      });
    }
  });
}, {threshold: 0.2, rootMargin: '-60px 0px -60px 0px'});
sections.forEach(s => s.id && observer.observe(s));

// ── Recommendations ──
const data = {
  repos: {{ repos | tojson }},
  quality: {{ quality | tojson }},
  collab: {{ collaboration | tojson }},
  scores: {{ scores | tojson }},
  langs: {{ languages | tojson }},
  profile: {{ profile | tojson }},
};
const recs = [];

if (!data.profile.bio)
  recs.push({icon:'📝', title:'Add a Bio', desc:'Your GitHub bio helps visitors understand who you are and what you do.'});
if (!data.profile.website)
  recs.push({icon:'🔗', title:'Add a Personal Website', desc:'Link to your portfolio or blog to increase discoverability.'});
if (data.quality.average_score < 60)
  recs.push({icon:'📄', title:'Improve READMEs', desc:'Adding detailed READMEs, licenses, and CI/CD config significantly boosts project quality scores.'});
if (data.repos.archived_count === 0 && data.repos.total > 20)
  recs.push({icon:'🗃️', title:'Archive Inactive Repos', desc:'Archiving old projects signals good maintenance hygiene and helps visitors find your active work.'});
if (data.collab.followers < 100)
  recs.push({icon:'🤝', title:'Grow Your Community', desc:'Engage in open-source projects, respond to issues, and share your work on social media.'});
if (data.scores.productivity_score < 50)
  recs.push({icon:'⚡', title:'Increase Commit Frequency', desc:'Regular commits demonstrate continuous learning and project momentum to potential collaborators.'});
if (!data.langs.top_languages.includes('TypeScript') && data.langs.top_languages.includes('JavaScript'))
  recs.push({icon:'🔷', title:'Consider TypeScript', desc:'Adding TypeScript to JavaScript projects improves code quality and contributor onboarding.'});
if (recs.length === 0)
  recs.push({icon:'🏆', title:'Outstanding Profile!', desc:'Your GitHub profile is well-maintained. Keep up the excellent work!'});

const recList = document.getElementById('rec-list');
recs.forEach(r => {
  recList.innerHTML += `
    <div class="rec-item">
      <div class="rec-icon">${r.icon}</div>
      <div class="rec-content">
        <div class="rec-title">${r.title}</div>
        <div class="rec-desc">${r.desc}</div>
      </div>
    </div>`;
});
</script>
</body>
</html>
"""


class ReportGenerator:
    """Renders the HTML report from analysis data."""

    def __init__(self):
        self.charts = ChartGenerator()
        self.template = Template(HTML_TEMPLATE)

    def generate(self, data: dict, output_path: Path) -> Path:
        logger.info("Generating charts…")
        chart_heatmap = self.charts.commit_heatmap(
            data["contributions"]["heatmap_data"]
        )
        chart_monthly_contrib = self.charts.monthly_contributions(
            data["contributions"]["monthly_trend"]
        )
        chart_hours = self.charts.commit_hour_bar(data["commits"]["hour_distribution"])
        chart_weekdays = self.charts.weekday_bar(data["commits"]["day_distribution"])
        chart_languages = self.charts.language_donut(data["languages"])
        chart_repo_growth = self.charts.repo_growth_chart(
            data["repos"].get("creation_by_year", {})
        )
        chart_radar = self.charts.radar_chart(data["scores"])

        logger.info("Rendering HTML template…")
        html = self.template.render(
            profile=data["profile"],
            repos=data["repos"],
            languages=data["languages"],
            tech_stack=data["tech_stack"],
            commits=data["commits"],
            contributions=data["contributions"],
            quality=data["quality"],
            collaboration=data["collaboration"],
            scores=data["scores"],
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
            chart_heatmap=chart_heatmap,
            chart_monthly_contrib=chart_monthly_contrib,
            chart_hours=chart_hours,
            chart_weekdays=chart_weekdays,
            chart_languages=chart_languages,
            chart_repo_growth=chart_repo_growth,
            chart_radar=chart_radar,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info(f"Report saved to: {output_path}")
        return output_path


# ─────────────────────────────────────────────
#  PUBLIC FUNCTION
# ─────────────────────────────────────────────


def gitUserReport(
    username: str, token: str | None = None, output_dir: str = "reports"
) -> tuple[str, dict]:
    """
    Analyze a GitHub user account and generate a professional HTML analytics dashboard.

    Args:
        username: GitHub username to analyze.
        token: GitHub PAT (optional).
        output_dir: Output directory for the report.

    Returns:
        Tuple of (report_path: str, summary: dict)
    """
    if not token:
        token = get_token("GITHUB_TOKEN")
    if not token:
        logger.warning(
            "GITHUB_TOKEN not set — operating in unauthenticated mode (rate limits apply)."
        )

    fetcher = GitHubFetcher(token)
    analyzer = GitHubAnalyzer(fetcher)

    logger.info(f"Analyzing GitHub user: {username}")
    data = analyzer.analyze(username)

    output_dir_path = Path(output_dir)
    output_path = output_dir_path / f"{username}_github_report.html"

    reporter = ReportGenerator()
    reporter.generate(data, output_path)

    summary = {
        "profile_score": data["scores"]["profile_score"],
        "productivity_score": data["scores"]["productivity_score"],
        "collaboration_score": data["scores"]["collaboration_score"],
        "quality_score": data["scores"]["quality_score"],
        "overall_score": data["scores"]["overall"],
        "repositories": data["profile"]["public_repos"],
        "total_commits": data["commits"]["total_commits_from_events"],
        "total_contributions": data["contributions"]["total"],
        "followers": data["profile"]["followers"],
        "top_languages": data["languages"]["top_languages"],
        "top_technologies": data["tech_stack"]["top_tech"],
        "most_active_repository": (
            data["repos"]["top_starred"][0]["name"]
            if data["repos"].get("top_starred")
            else "N/A"
        ),
    }

    logger.info("✅ Report generation complete.")
    logger.info(f"   Path: {output_path.resolve()}")
    logger.info(f"   Summary: {summary}")

    return str(output_path.resolve()), summary


if __name__ == "__main__":
    import sys

    user = sys.argv[1] if len(sys.argv) > 1 else "torvalds"
    path, s = gitUserReport(user)
    print(f"\nReport: {path}")
    print(f"Summary: {json.dumps(s, indent=2)}")

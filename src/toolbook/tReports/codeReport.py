#!/usr/bin/env python3
"""
Code Quality Report Generator
==============================
Analyzes a Python source repository using multiple static analysis tools
and produces a professional standalone HTML dashboard, plus JSON and CSV exports.
"""

from __future__ import annotations

import ast
import collections
import csv
import hashlib
import json
import logging
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── Optional rich progress bar ──────────────────────────────────────────────
try:
    from rich.console import Console  # noqa: F401
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn  # noqa: F401
    from rich.logging import RichHandler
    _RICH = True
except ImportError:
    _RICH = False

# ─── Logging setup ────────────────────────────────────────────────────────────

def _setup_logging(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    if _RICH:
        logging.basicConfig(
            level=level,
            format="%(message)s",
            handlers=[RichHandler(rich_tracebacks=True, markup=True)],
        )
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
    return logging.getLogger("quality_report")


log = _setup_logging()

# ─── Data models ──────────────────────────────────────────────────────────────

@dataclass
class ComplexityResult:
    file: str
    function: str
    complexity: int
    rank: str          # A–F
    line: int = 0

@dataclass
class MaintainabilityResult:
    file: str
    mi_score: float    # 0–100
    rank: str          # A–C

@dataclass
class SecurityIssue:
    file: str
    line: int
    severity: str      # HIGH / MEDIUM / LOW
    confidence: str
    issue_id: str
    description: str
    tool: str          # bandit | semgrep

@dataclass
class LintIssue:
    file: str
    line: int
    column: int
    symbol: str
    message: str
    category: str      # convention | refactor | warning | error | fatal

@dataclass
class DeadCodeItem:
    file: str
    line: int
    kind: str          # unused-import | unused-variable | dead-function | …
    name: str

@dataclass
class DuplicateBlock:
    file_a: str
    start_a: int
    file_b: str
    start_b: int
    lines: int
    fingerprint: str

@dataclass
class DependencyVuln:
    package: str
    installed_version: str
    vulnerability_id: str
    severity: str
    description: str
    fix_version: str = ""

@dataclass
class AnalysisReport:
    repo_path: str
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    files_analyzed: int = 0
    total_lines: int = 0

    complexity: List[ComplexityResult] = field(default_factory=list)
    maintainability: List[MaintainabilityResult] = field(default_factory=list)
    security: List[SecurityIssue] = field(default_factory=list)
    lint: List[LintIssue] = field(default_factory=list)
    dead_code: List[DeadCodeItem] = field(default_factory=list)
    duplicates: List[DuplicateBlock] = field(default_factory=list)
    dependencies: List[DependencyVuln] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Scores 0-100
    quality_score: float = 0.0
    security_score: float = 0.0
    maintainability_score: float = 0.0
    complexity_score: float = 0.0
    pylint_score: float = 0.0


# ─── Helpers ──────────────────────────────────────────────────────────────────

SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".tox", "node_modules", "dist", "build", ".venv", "venv", "env",
    ".env", "site-packages", ".eggs", "*.egg-info",
}

def _collect_python_files(root: Path, extra_exclude: List[str] = []) -> List[Path]:
    """Recursively collect .py files, skipping known noise directories."""
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune directories in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.endswith(".egg-info")
            and not any(Path(dirpath, d).match(pat) for pat in extra_exclude)
        ]
        for fn in filenames:
            if fn.endswith(".py"):
                files.append(Path(dirpath) / fn)
    return files


def _run(cmd: List[str], cwd: Optional[str] = None, timeout: int = 120) -> Tuple[str, str, int]:
    """Run a subprocess and return (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout
        )
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        return "", f"Tool not found: {cmd[0]}", -1
    except subprocess.TimeoutExpired:
        return "", f"Timeout running: {' '.join(cmd)}", -2
    except Exception as exc:
        return "", str(exc), -3


def _tool_available(name: str) -> bool:
    out, _, rc = _run([name, "--version"])
    return rc == 0 or bool(out)


# ─── Analyzers ────────────────────────────────────────────────────────────────

class ComplexityAnalyzer:
    """Uses radon for cyclomatic complexity and maintainability index."""

    def analyze(self, files: List[Path]) -> Tuple[List[ComplexityResult], List[MaintainabilityResult]]:
        cc_results: List[ComplexityResult] = []
        mi_results: List[MaintainabilityResult] = []

        try:
            # pyrefly: ignore [missing-import]
            import radon.complexity as rc
            # pyrefly: ignore [missing-import]
            import radon.metrics as rm
            # pyrefly: ignore [missing-import]
            import radon.visitors as rv  # noqa: F401
        except ImportError:
            log.warning("radon not installed – skipping complexity analysis (pip install radon)")
            return cc_results, mi_results

        for path in files:
            try:
                source = path.read_text(encoding="utf-8", errors="ignore")
                # Cyclomatic complexity
                blocks = rc.cc_visit(source)
                for block in blocks:
                    cc_results.append(ComplexityResult(
                        file=str(path),
                        function=block.name,
                        complexity=block.complexity,
                        rank=rc.cc_rank(block.complexity),
                        line=block.lineno,
                    ))
                # Maintainability index
                mi = rm.mi_visit(source, multi=True)
                rank = "A" if mi >= 80 else ("B" if mi >= 50 else "C")
                mi_results.append(MaintainabilityResult(
                    file=str(path),
                    mi_score=round(mi, 2),
                    rank=rank,
                ))
            except Exception as exc:
                log.debug(f"Complexity error {path}: {exc}")

        return cc_results, mi_results


class SecurityAnalyzer:
    """Runs bandit and optionally semgrep."""

    def analyze(self, repo_path: Path) -> List[SecurityIssue]:
        issues: List[SecurityIssue] = []
        issues.extend(self._run_bandit(repo_path))
        issues.extend(self._run_semgrep(repo_path))
        return issues

    def _run_bandit(self, repo_path: Path) -> List[SecurityIssue]:
        issues: List[SecurityIssue] = []
        stdout, stderr, rc = _run(
            ["bandit", "-r", str(repo_path), "-f", "json", "--quiet"],
            timeout=180,
        )
        if rc == -1:
            log.warning("bandit not installed – skipping (pip install bandit)")
            return issues
        try:
            data = json.loads(stdout)
            for r in data.get("results", []):
                issues.append(SecurityIssue(
                    file=r.get("filename", ""),
                    line=r.get("line_number", 0),
                    severity=r.get("issue_severity", "LOW").upper(),
                    confidence=r.get("issue_confidence", "LOW").upper(),
                    issue_id=r.get("test_id", ""),
                    description=r.get("issue_text", ""),
                    tool="bandit",
                ))
        except (json.JSONDecodeError, KeyError) as exc:
            log.debug(f"bandit parse error: {exc}")
        return issues

    def _run_semgrep(self, repo_path: Path) -> List[SecurityIssue]:
        issues: List[SecurityIssue] = []
        stdout, _, rc = _run(
            ["semgrep", "--config=auto", "--json", "--quiet", str(repo_path)],
            timeout=300,
        )
        if rc == -1:
            log.debug("semgrep not available – skipping")
            return issues
        try:
            data = json.loads(stdout)
            for r in data.get("results", []):
                sev = r.get("extra", {}).get("severity", "WARNING").upper()
                sev_map = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "LOW"}
                issues.append(SecurityIssue(
                    file=r.get("path", ""),
                    line=r.get("start", {}).get("line", 0),
                    severity=sev_map.get(sev, "LOW"),
                    confidence="MEDIUM",
                    issue_id=r.get("check_id", ""),
                    description=r.get("extra", {}).get("message", ""),
                    tool="semgrep",
                ))
        except Exception as exc:
            log.debug(f"semgrep parse error: {exc}")
        return issues


class LintAnalyzer:
    """Runs pylint and parses JSON output."""

    def analyze(self, repo_path: Path) -> Tuple[List[LintIssue], float]:
        issues: List[LintIssue] = []
        stdout, stderr, rc = _run(
            ["pylint", str(repo_path), "--output-format=json", "--recursive=y",
             "--disable=C0114,C0115,C0116"],  # suppress missing docstrings for speed
            timeout=300,
        )
        if rc == -1:
            log.warning("pylint not installed – skipping (pip install pylint)")
            return issues, 0.0

        try:
            data = json.loads(stdout)
            for item in data:
                issues.append(LintIssue(
                    file=item.get("path", ""),
                    line=item.get("line", 0),
                    column=item.get("column", 0),
                    symbol=item.get("symbol", ""),
                    message=item.get("message", ""),
                    category=item.get("type", "convention"),
                ))
        except (json.JSONDecodeError, TypeError) as exc:
            log.debug(f"pylint parse error: {exc}")

        # Extract pylint score from stderr (Rating line)
        score = 0.0
        score_match = re.search(r"rated at ([\d.]+)/10", stderr + stdout)
        if score_match:
            score = float(score_match.group(1)) * 10  # convert to 0-100

        return issues, score


class DeadCodeAnalyzer:
    """Detects dead/unused code via vulture and AST inspection."""

    def analyze(self, files: List[Path]) -> List[DeadCodeItem]:
        items: List[DeadCodeItem] = []
        items.extend(self._run_vulture(files))
        items.extend(self._ast_unused_imports(files))
        return items

    def _run_vulture(self, files: List[Path]) -> List[DeadCodeItem]:
        items: List[DeadCodeItem] = []
        stdout, _, rc = _run(
            ["vulture"] + [str(f) for f in files] + ["--min-confidence", "60"],
            timeout=120,
        )
        if rc == -1:
            log.debug("vulture not available – skipping (pip install vulture)")
            return items
        for line in stdout.splitlines():
            # Format: path:line: message (confidence%)
            m = re.match(r"^(.+?):(\d+):\s+(.+?)\s+\((\d+)%\s+confidence\)$", line)
            if m:
                raw_msg = m.group(3)
                kind = "dead-code"
                if "unused import" in raw_msg:
                    kind = "unused-import"
                elif "unused variable" in raw_msg:
                    kind = "unused-variable"
                elif "unused function" in raw_msg:
                    kind = "dead-function"
                elif "unused class" in raw_msg:
                    kind = "dead-class"
                name_match = re.search(r"'(.+?)'", raw_msg)
                items.append(DeadCodeItem(
                    file=m.group(1),
                    line=int(m.group(2)),
                    kind=kind,
                    name=name_match.group(1) if name_match else raw_msg,
                ))
        return items

    def _ast_unused_imports(self, files: List[Path]) -> List[DeadCodeItem]:
        """Basic AST-based unused import detection as fallback."""
        items: List[DeadCodeItem] = []
        for path in files:
            try:
                source = path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(source)
                imported_names: Dict[str, int] = {}
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            name = alias.asname or alias.name.split(".")[0]
                            imported_names[name] = node.lineno
                    elif isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            name = alias.asname or alias.name
                            imported_names[name] = node.lineno

                # Collect all Name usages outside imports
                used_names: set = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name):
                        used_names.add(node.id)
                    elif isinstance(node, ast.Attribute):
                        if isinstance(node.value, ast.Name):
                            used_names.add(node.value.id)

                for name, lineno in imported_names.items():
                    if name not in used_names and name != "*":
                        items.append(DeadCodeItem(
                            file=str(path),
                            line=lineno,
                            kind="unused-import",
                            name=name,
                        ))
            except Exception:
                pass
        return items


class DuplicateAnalyzer:
    """Detects duplicate code blocks using AST fingerprinting."""

    MIN_LINES = 6

    def analyze(self, files: List[Path]) -> List[DuplicateBlock]:
        # Build fingerprint → list of (file, start_line) mapping
        fingerprints: Dict[str, List[Tuple[str, int]]] = collections.defaultdict(list)

        for path in files:
            try:
                source = path.read_text(encoding="utf-8", errors="ignore")
                lines = source.splitlines()
                # Sliding window of MIN_LINES
                for i in range(len(lines) - self.MIN_LINES + 1):
                    window = lines[i:i + self.MIN_LINES]
                    # Normalise whitespace & strip comments
                    normalized = "\n".join(
                        re.sub(r"#.*", "", line).strip() for line in window
                        if line.strip() and not line.strip().startswith("#")
                    )
                    if len(normalized) < 40:
                        continue
                    fp = hashlib.md5(normalized.encode()).hexdigest()
                    fingerprints[fp].append((str(path), i + 1))
            except Exception:
                pass

        duplicates: List[DuplicateBlock] = []
        seen: set = set()
        for fp, locations in fingerprints.items():
            if len(locations) < 2:
                continue
            for idx_a in range(len(locations)):
                for idx_b in range(idx_a + 1, len(locations)):
                    file_a, line_a = locations[idx_a]
                    file_b, line_b = locations[idx_b]
                    if file_a == file_b and abs(line_a - line_b) < self.MIN_LINES:
                        continue
                    key = tuple(sorted([(file_a, line_a), (file_b, line_b)]))
                    if key in seen:
                        continue
                    seen.add(key)
                    duplicates.append(DuplicateBlock(
                        file_a=file_a, start_a=line_a,
                        file_b=file_b, start_b=line_b,
                        lines=self.MIN_LINES,
                        fingerprint=fp,
                    ))
        # Cap results for performance
        return duplicates[:200]


class DependencyAnalyzer:
    """Runs pip-audit and/or safety to find vulnerable dependencies."""

    def analyze(self, repo_path: Path) -> List[DependencyVuln]:
        vulns: List[DependencyVuln] = []
        vulns.extend(self._run_pip_audit(repo_path))
        if not vulns:
            vulns.extend(self._run_safety(repo_path))
        return vulns

    def _run_pip_audit(self, repo_path: Path) -> List[DependencyVuln]:
        vulns: List[DependencyVuln] = []
        # Try requirements.txt first, then installed packages
        req_file = repo_path / "requirements.txt"
        cmd = ["pip-audit", "--format=json"]
        if req_file.exists():
            cmd += ["-r", str(req_file)]

        stdout, _, rc = _run(cmd, timeout=120)
        if rc == -1:
            log.debug("pip-audit not available (pip install pip-audit)")
            return vulns
        try:
            data = json.loads(stdout)
            for dep in data.get("dependencies", []):
                for vuln in dep.get("vulns", []):
                    fix = ""
                    if vuln.get("fix_versions"):
                        fix = ", ".join(vuln["fix_versions"])
                    vulns.append(DependencyVuln(
                        package=dep.get("name", ""),
                        installed_version=dep.get("version", ""),
                        vulnerability_id=vuln.get("id", ""),
                        severity="HIGH",  # pip-audit doesn't always include severity
                        description=vuln.get("description", ""),
                        fix_version=fix,
                    ))
        except Exception as exc:
            log.debug(f"pip-audit parse error: {exc}")
        return vulns

    def _run_safety(self, repo_path: Path) -> List[DependencyVuln]:
        vulns: List[DependencyVuln] = []
        req_file = repo_path / "requirements.txt"
        if not req_file.exists():
            return vulns
        stdout, _, rc = _run(
            ["safety", "check", "-r", str(req_file), "--json"],
            timeout=60,
        )
        if rc == -1:
            log.debug("safety not available (pip install safety)")
            return vulns
        try:
            data = json.loads(stdout)
            for item in data:
                vulns.append(DependencyVuln(
                    package=item[0],
                    installed_version=item[2],
                    vulnerability_id=item[4],
                    severity="MEDIUM",
                    description=item[3],
                    fix_version="",
                ))
        except Exception as exc:
            log.debug(f"safety parse error: {exc}")
        return vulns


# ─── Score calculation ─────────────────────────────────────────────────────────

def _calculate_scores(report: AnalysisReport) -> None:
    """Derive quality scores (0-100) from raw findings."""
    # Security score
    high = sum(1 for s in report.security if s.severity == "HIGH")
    med  = sum(1 for s in report.security if s.severity == "MEDIUM")
    low  = sum(1 for s in report.security if s.severity == "LOW")
    sec_penalty = high * 10 + med * 3 + low * 1
    report.security_score = max(0.0, round(100 - sec_penalty, 1))

    # Maintainability score
    if report.maintainability:
        avg_mi = sum(m.mi_score for m in report.maintainability) / len(report.maintainability)
        report.maintainability_score = round(min(100, avg_mi), 1)
    else:
        report.maintainability_score = 75.0

    # Complexity score (penalise high-complexity functions)
    complex_funcs = sum(1 for c in report.complexity if c.complexity > 10)
    if report.files_analyzed:
        ratio = complex_funcs / max(report.files_analyzed, 1)
        report.complexity_score = max(0.0, round(100 - ratio * 100, 1))
    else:
        report.complexity_score = 100.0

    # Pylint score already set externally; fall back
    if report.pylint_score == 0 and report.lint:
        errors = sum(1 for issue in report.lint if issue.category in ("error", "fatal"))
        report.pylint_score = max(0.0, round(100 - errors * 2, 1))

    # Overall
    report.quality_score = round(
        (report.security_score * 0.35
         + report.maintainability_score * 0.25
         + report.complexity_score * 0.20
         + report.pylint_score * 0.20),
        1,
    )


# ─── HTML Report ──────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Code Quality Report – {{ repo_name }}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
/* ── Reset & Variables ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #0d1117;
  --bg2: #161b22;
  --bg3: #1c2128;
  --border: #30363d;
  --text: #e6edf3;
  --muted: #7d8590;
  --accent: #58a6ff;
  --green: #3fb950;
  --yellow: #d29922;
  --red: #f85149;
  --orange: #db6d28;
  --purple: #a371f7;
  --font-mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  --font-ui: 'Inter', system-ui, sans-serif;
  --sidebar-w: 240px;
  --radius: 8px;
}
html { scroll-behavior: smooth; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-ui);
  display: flex;
  min-height: 100vh;
}

/* ── Sidebar ── */
#sidebar {
  width: var(--sidebar-w);
  background: var(--bg2);
  border-right: 1px solid var(--border);
  position: fixed;
  top: 0; left: 0;
  height: 100vh;
  overflow-y: auto;
  padding: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
}
.sidebar-brand {
  padding: 20px 16px 16px;
  border-bottom: 1px solid var(--border);
}
.sidebar-brand h1 {
  font-size: 13px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: .5px;
  text-transform: uppercase;
}
.sidebar-brand p {
  font-size: 11px;
  color: var(--muted);
  margin-top: 2px;
  word-break: break-all;
}
.sidebar-score {
  padding: 16px;
  text-align: center;
  border-bottom: 1px solid var(--border);
}
.score-circle {
  width: 72px; height: 72px;
  border-radius: 50%;
  border: 4px solid var(--accent);
  display: flex; align-items: center; justify-content: center;
  margin: 0 auto 8px;
  font-size: 22px; font-weight: 800;
}
.score-circle.green { border-color: var(--green); color: var(--green); }
.score-circle.yellow { border-color: var(--yellow); color: var(--yellow); }
.score-circle.red { border-color: var(--red); color: var(--red); }
.sidebar-score p { font-size: 11px; color: var(--muted); }
nav ul { list-style: none; padding: 8px 0; flex: 1; }
nav ul li a {
  display: flex; align-items: center; gap: 8px;
  padding: 9px 16px;
  font-size: 13px; color: var(--muted);
  text-decoration: none;
  border-left: 3px solid transparent;
  transition: all .15s;
}
nav ul li a:hover, nav ul li a.active {
  color: var(--text);
  background: var(--bg3);
  border-left-color: var(--accent);
}
nav ul li a .nav-icon { font-size: 14px; width: 18px; text-align: center; }
nav ul li a .badge {
  margin-left: auto;
  font-size: 10px;
  background: var(--bg3);
  padding: 2px 6px;
  border-radius: 10px;
  border: 1px solid var(--border);
}
.badge.red-badge { background: rgba(248,81,73,.15); border-color: var(--red); color: var(--red); }
.badge.yellow-badge { background: rgba(210,153,34,.15); border-color: var(--yellow); color: var(--yellow); }
.sidebar-footer {
  padding: 12px 16px;
  font-size: 10px;
  color: var(--muted);
  border-top: 1px solid var(--border);
}

/* ── Main content ── */
#main {
  margin-left: var(--sidebar-w);
  flex: 1;
  padding: 32px 40px;
  max-width: 1280px;
}
section { margin-bottom: 48px; scroll-margin-top: 24px; }
h2 {
  font-size: 20px; font-weight: 700;
  border-bottom: 1px solid var(--border);
  padding-bottom: 12px; margin-bottom: 20px;
  display: flex; align-items: center; gap: 10px;
}
h2 .sec-icon { font-size: 18px; }
h3 { font-size: 15px; font-weight: 600; margin-bottom: 12px; color: var(--muted); }

/* ── Cards ── */
.card-grid { display: grid; gap: 16px; }
.card-grid-4 { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }
.card-grid-2 { grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }
.card {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}
.card-stat { text-align: center; }
.card-stat .stat-value {
  font-size: 36px; font-weight: 800;
  line-height: 1; margin-bottom: 4px;
}
.card-stat .stat-label { font-size: 12px; color: var(--muted); }
.stat-green { color: var(--green); }
.stat-yellow { color: var(--yellow); }
.stat-red { color: var(--red); }
.stat-blue { color: var(--accent); }
.stat-purple { color: var(--purple); }

/* ── Tables ── */
.tbl-wrap { overflow-x: auto; }
table {
  width: 100%; border-collapse: collapse;
  font-size: 13px;
}
thead th {
  background: var(--bg3);
  padding: 10px 12px;
  text-align: left;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .5px;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
}
tbody tr {
  border-bottom: 1px solid var(--border);
  transition: background .1s;
}
tbody tr:hover { background: var(--bg3); }
tbody td { padding: 9px 12px; vertical-align: top; }
.mono { font-family: var(--font-mono); font-size: 12px; }
.path { color: var(--accent); font-family: var(--font-mono); font-size: 11px; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── Badges ── */
.sev {
  display: inline-block;
  padding: 2px 8px; border-radius: 4px;
  font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .3px;
}
.sev-high  { background: rgba(248,81,73,.2);  color: var(--red);    border: 1px solid var(--red); }
.sev-med   { background: rgba(219,109,40,.2); color: var(--orange); border: 1px solid var(--orange); }
.sev-low   { background: rgba(210,153,34,.2); color: var(--yellow); border: 1px solid var(--yellow); }
.sev-info  { background: rgba(88,166,255,.1); color: var(--accent); border: 1px solid var(--accent); }
.rank-a { color: var(--green); font-weight: 700; }
.rank-b { color: var(--yellow); font-weight: 700; }
.rank-c { color: var(--red); font-weight: 700; }

/* ── Charts ── */
.chart-card { position: relative; height: 260px; }
.chart-card canvas { height: 100% !important; }

/* ── Expandable ── */
details { border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 8px; }
summary {
  padding: 10px 14px; cursor: pointer;
  font-size: 13px; font-weight: 600;
  list-style: none; display: flex; align-items: center; gap: 8px;
  user-select: none;
}
summary::-webkit-details-marker { display: none; }
summary::before { content: '▶'; font-size: 10px; transition: transform .2s; }
details[open] summary::before { transform: rotate(90deg); }
details > div { padding: 0 14px 14px; }

/* ── Progress bar ── */
.progress-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.progress-label { min-width: 120px; font-size: 12px; color: var(--muted); }
.progress-bar-bg { flex: 1; height: 8px; background: var(--bg3); border-radius: 4px; overflow: hidden; }
.progress-bar-fill { height: 100%; border-radius: 4px; transition: width .6s; }
.fill-green { background: var(--green); }
.fill-yellow { background: var(--yellow); }
.fill-red { background: var(--red); }
.fill-blue { background: var(--accent); }
.progress-val { min-width: 40px; font-size: 12px; text-align: right; }

/* ── Recommendations ── */
.rec-item {
  display: flex; gap: 14px;
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 14px; margin-bottom: 10px;
}
.rec-icon { font-size: 20px; flex-shrink: 0; }
.rec-body h4 { font-size: 14px; margin-bottom: 4px; }
.rec-body p { font-size: 12px; color: var(--muted); line-height: 1.5; }

/* ── Empty state ── */
.empty { padding: 40px; text-align: center; color: var(--muted); font-size: 14px; }
.empty span { display: block; font-size: 32px; margin-bottom: 8px; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>

<!-- SIDEBAR -->
<aside id="sidebar">
  <div class="sidebar-brand">
    <h1>⚙ Quality Report</h1>
    <p>{{ repo_name }}</p>
  </div>
  <div class="sidebar-score">
    <div class="score-circle {{ score_class }}">{{ quality_score }}</div>
    <p>Overall Score</p>
  </div>
  <nav>
    <ul>
      <li><a href="#summary" class="active"><span class="nav-icon">📊</span>Executive Summary</a></li>
      <li><a href="#complexity"><span class="nav-icon">🔀</span>Complexity <span class="badge {{ complexity_badge_class }}">{{ complexity_count }}</span></a></li>
      <li><a href="#security"><span class="nav-icon">🔒</span>Security <span class="badge {{ security_badge_class }}">{{ security_count }}</span></a></li>
      <li><a href="#lint"><span class="nav-icon">🧹</span>Linting <span class="badge {{ lint_badge_class }}">{{ lint_count }}</span></a></li>
      <li><a href="#deadcode"><span class="nav-icon">💀</span>Dead Code <span class="badge">{{ dead_count }}</span></a></li>
      <li><a href="#duplicates"><span class="nav-icon">📋</span>Duplicates <span class="badge">{{ dup_count }}</span></a></li>
      <li><a href="#deps"><span class="nav-icon">📦</span>Dependencies <span class="badge {{ deps_badge_class }}">{{ deps_count }}</span></a></li>
      <li><a href="#recommendations"><span class="nav-icon">💡</span>Recommendations</a></li>
    </ul>
  </nav>
  <div class="sidebar-footer">Generated {{ generated_at }}</div>
</aside>

<!-- MAIN -->
<main id="main">

<!-- ╔═══════════════════════╗ -->
<!-- ║  1. Executive Summary ║ -->
<!-- ╚═══════════════════════╝ -->
<section id="summary">
  <h2><span class="sec-icon">📊</span> Executive Summary</h2>

  <div class="card-grid card-grid-4" style="margin-bottom:24px">
    <div class="card card-stat">
      <div class="stat-value {{ score_class }}">{{ quality_score }}</div>
      <div class="stat-label">Quality Score</div>
    </div>
    <div class="card card-stat">
      <div class="stat-value {{ sec_score_class }}">{{ security_score }}</div>
      <div class="stat-label">Security Score</div>
    </div>
    <div class="card card-stat">
      <div class="stat-value {{ mi_score_class }}">{{ maintainability_score }}</div>
      <div class="stat-label">Maintainability</div>
    </div>
    <div class="card card-stat">
      <div class="stat-value stat-blue">{{ files_analyzed }}</div>
      <div class="stat-label">Files Analysed</div>
    </div>
    <div class="card card-stat">
      <div class="stat-value stat-purple">{{ total_lines }}</div>
      <div class="stat-label">Total Lines</div>
    </div>
    <div class="card card-stat">
      <div class="stat-value {{ security_count_class }}">{{ security_count }}</div>
      <div class="stat-label">Security Issues</div>
    </div>
    <div class="card card-stat">
      <div class="stat-value stat-yellow">{{ lint_count }}</div>
      <div class="stat-label">Lint Warnings</div>
    </div>
    <div class="card card-stat">
      <div class="stat-value {{ deps_count_class }}">{{ deps_count }}</div>
      <div class="stat-label">Vuln Dependencies</div>
    </div>
  </div>

  <div class="card-grid card-grid-2">
    <div class="card">
      <h3>Score Breakdown</h3>
      {% for label, val, cls in score_rows %}
      <div class="progress-row">
        <span class="progress-label">{{ label }}</span>
        <div class="progress-bar-bg">
          <div class="progress-bar-fill {{ cls }}" style="width:{{ val }}%"></div>
        </div>
        <span class="progress-val">{{ val }}</span>
      </div>
      {% endfor %}
    </div>
    <div class="card chart-card">
      <canvas id="radarChart"></canvas>
    </div>
  </div>
</section>

<!-- ╔════════════════════════╗ -->
<!-- ║  2. Complexity         ║ -->
<!-- ╚════════════════════════╝ -->
<section id="complexity">
  <h2><span class="sec-icon">🔀</span> Complexity Analysis</h2>
  {% if not complexity_rows %}
  <div class="empty"><span>✅</span>No complex functions detected.</div>
  {% else %}
  <div class="card-grid card-grid-2" style="margin-bottom:24px">
    <div class="card chart-card">
      <canvas id="ccChart"></canvas>
    </div>
    <div class="card">
      <h3>Complexity Distribution</h3>
      {% for rank, cnt, cls in cc_dist %}
      <div class="progress-row">
        <span class="progress-label">Rank {{ rank }}</span>
        <div class="progress-bar-bg">
          <div class="progress-bar-fill {{ cls }}" style="width:{{ cnt }}%"></div>
        </div>
        <span class="progress-val">{{ cnt }}</span>
      </div>
      {% endfor %}
      <p style="margin-top:12px;font-size:11px;color:var(--muted)">A-B = good · C-D = moderate · E-F = critical</p>
    </div>
  </div>
  <div class="tbl-wrap">
  <table>
    <thead><tr><th>File</th><th>Function</th><th>Complexity</th><th>Rank</th><th>Line</th></tr></thead>
    <tbody>
    {% for r in complexity_rows %}
    <tr>
      <td class="path" title="{{ r.file }}">{{ r.file|basename }}</td>
      <td class="mono">{{ r.function }}</td>
      <td class="mono">{{ r.complexity }}</td>
      <td><span class="rank-{{ r.rank|lower }}">{{ r.rank }}</span></td>
      <td class="mono">{{ r.line }}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
  {% endif %}
</section>

<!-- ╔════════════════════════╗ -->
<!-- ║  3. Security           ║ -->
<!-- ╚════════════════════════╝ -->
<section id="security">
  <h2><span class="sec-icon">🔒</span> Security Analysis</h2>
  {% if not security_rows %}
  <div class="empty"><span>✅</span>No security issues detected.</div>
  {% else %}
  <div class="card-grid card-grid-2" style="margin-bottom:24px">
    <div class="card chart-card">
      <canvas id="secChart"></canvas>
    </div>
    <div class="card card-stat" style="justify-content:center;display:flex;flex-direction:column;align-items:center">
      <div class="stat-value {{ sec_score_class }}">{{ security_score }}</div>
      <div class="stat-label">Security Score</div>
      <div style="margin-top:16px;font-size:12px;color:var(--muted);text-align:center">
        {% for sev, cnt in sec_sev_counts %}
        <div>{{ sev }}: <strong>{{ cnt }}</strong></div>
        {% endfor %}
      </div>
    </div>
  </div>
  <div class="tbl-wrap">
  <table>
    <thead><tr><th>File</th><th>Line</th><th>Issue ID</th><th>Description</th><th>Severity</th><th>Tool</th></tr></thead>
    <tbody>
    {% for r in security_rows %}
    <tr>
      <td class="path" title="{{ r.file }}">{{ r.file|basename }}</td>
      <td class="mono">{{ r.line }}</td>
      <td class="mono">{{ r.issue_id }}</td>
      <td>{{ r.description }}</td>
      <td><span class="sev sev-{{ r.severity[:3]|lower }}">{{ r.severity }}</span></td>
      <td class="mono">{{ r.tool }}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
  {% endif %}
</section>

<!-- ╔════════════════════════╗ -->
<!-- ║  4. Linting            ║ -->
<!-- ╚════════════════════════╝ -->
<section id="lint">
  <h2><span class="sec-icon">🧹</span> Linting &amp; Code Quality</h2>
  <div class="card-grid card-grid-4" style="margin-bottom:24px">
    <div class="card card-stat">
      <div class="stat-value {{ pylint_score_class }}">{{ pylint_score }}<small style="font-size:16px">/100</small></div>
      <div class="stat-label">Pylint Score</div>
    </div>
    {% for cat, cnt in lint_cats %}
    <div class="card card-stat">
      <div class="stat-value stat-yellow">{{ cnt }}</div>
      <div class="stat-label">{{ cat|title }}</div>
    </div>
    {% endfor %}
  </div>
  {% if not lint_rows %}
  <div class="empty"><span>✅</span>No lint issues found.</div>
  {% else %}
  <div class="tbl-wrap">
  <table>
    <thead><tr><th>File</th><th>Line</th><th>Symbol</th><th>Message</th><th>Category</th></tr></thead>
    <tbody>
    {% for r in lint_rows %}
    <tr>
      <td class="path" title="{{ r.file }}">{{ r.file|basename }}</td>
      <td class="mono">{{ r.line }}</td>
      <td class="mono">{{ r.symbol }}</td>
      <td>{{ r.message }}</td>
      <td><span class="sev sev-{{ 'high' if r.category in ('error','fatal') else ('med' if r.category=='warning' else 'info') }}">{{ r.category }}</span></td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
  {% endif %}
</section>

<!-- ╔════════════════════════╗ -->
<!-- ║  5. Dead Code          ║ -->
<!-- ╚════════════════════════╝ -->
<section id="deadcode">
  <h2><span class="sec-icon">💀</span> Dead Code Analysis</h2>
  {% if not dead_rows %}
  <div class="empty"><span>✅</span>No dead code detected.</div>
  {% else %}
  <div class="tbl-wrap">
  <table>
    <thead><tr><th>File</th><th>Line</th><th>Type</th><th>Name</th></tr></thead>
    <tbody>
    {% for r in dead_rows %}
    <tr>
      <td class="path" title="{{ r.file }}">{{ r.file|basename }}</td>
      <td class="mono">{{ r.line }}</td>
      <td><span class="sev sev-info">{{ r.kind }}</span></td>
      <td class="mono">{{ r.name }}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
  {% endif %}
</section>

<!-- ╔════════════════════════╗ -->
<!-- ║  6. Duplicates         ║ -->
<!-- ╚════════════════════════╝ -->
<section id="duplicates">
  <h2><span class="sec-icon">📋</span> Duplicate Code Analysis</h2>
  {% if not dup_rows %}
  <div class="empty"><span>✅</span>No significant code duplication detected.</div>
  {% else %}
  <p style="margin-bottom:16px;font-size:13px;color:var(--muted)">{{ dup_count }} duplicate block(s) found. Each entry represents a repeated code segment of ≥6 lines.</p>
  <div class="tbl-wrap">
  <table>
    <thead><tr><th>File A</th><th>Line A</th><th>File B</th><th>Line B</th><th>Lines</th></tr></thead>
    <tbody>
    {% for r in dup_rows %}
    <tr>
      <td class="path" title="{{ r.file_a }}">{{ r.file_a|basename }}</td>
      <td class="mono">{{ r.start_a }}</td>
      <td class="path" title="{{ r.file_b }}">{{ r.file_b|basename }}</td>
      <td class="mono">{{ r.start_b }}</td>
      <td class="mono">{{ r.lines }}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
  {% endif %}
</section>

<!-- ╔════════════════════════╗ -->
<!-- ║  7. Dependencies       ║ -->
<!-- ╚════════════════════════╝ -->
<section id="deps">
  <h2><span class="sec-icon">📦</span> Dependency Vulnerability Analysis</h2>
  {% if not deps_rows %}
  <div class="empty"><span>✅</span>No vulnerable dependencies found.</div>
  {% else %}
  <div class="tbl-wrap">
  <table>
    <thead><tr><th>Package</th><th>Version</th><th>CVE / ID</th><th>Severity</th><th>Fix Version</th><th>Description</th></tr></thead>
    <tbody>
    {% for r in deps_rows %}
    <tr>
      <td class="mono">{{ r.package }}</td>
      <td class="mono">{{ r.installed_version }}</td>
      <td class="mono">{{ r.vulnerability_id }}</td>
      <td><span class="sev sev-{{ r.severity[:3]|lower }}">{{ r.severity }}</span></td>
      <td class="mono">{{ r.fix_version or '—' }}</td>
      <td>{{ r.description[:120] }}{% if r.description|length > 120 %}…{% endif %}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
  {% endif %}
</section>

<!-- ╔════════════════════════╗ -->
<!-- ║  8. Recommendations    ║ -->
<!-- ╚════════════════════════╝ -->
<section id="recommendations">
  <h2><span class="sec-icon">💡</span> Recommendations</h2>
  {% for r in recommendations %}
  <div class="rec-item">
    <div class="rec-icon">{{ r.icon }}</div>
    <div class="rec-body">
      <h4>{{ r.title }}</h4>
      <p>{{ r.body }}</p>
    </div>
  </div>
  {% endfor %}
</section>

</main>

<script>
// ── Radar chart ──
const radarCtx = document.getElementById('radarChart').getContext('2d');
new Chart(radarCtx, {
  type: 'radar',
  data: {
    labels: ['Quality', 'Security', 'Maintainability', 'Complexity', 'Linting'],
    datasets: [{
      label: 'Score',
      data: [{{ quality_score }}, {{ security_score }}, {{ maintainability_score }}, {{ complexity_score }}, {{ pylint_score }}],
      borderColor: '#58a6ff',
      backgroundColor: 'rgba(88,166,255,0.15)',
      pointBackgroundColor: '#58a6ff',
    }]
  },
  options: {
    scales: { r: { min: 0, max: 100, ticks: { color: '#7d8590', stepSize: 20, backdropColor: 'transparent' }, grid: { color: '#30363d' }, pointLabels: { color: '#e6edf3' } } },
    plugins: { legend: { display: false } },
    animation: { duration: 800 }
  }
});

// ── CC distribution chart ──
{% if complexity_rows %}
const ccCtx = document.getElementById('ccChart').getContext('2d');
new Chart(ccCtx, {
  type: 'bar',
  data: {
    labels: {{ cc_labels|tojson }},
    datasets: [{
      label: 'Functions',
      data: {{ cc_data }},
      backgroundColor: ['#3fb950','#3fb950','#d29922','#d29922','#f85149','#f85149'],
      borderRadius: 4,
    }]
  },
  options: {
    plugins: { legend: { display: false }, title: { display: true, text: 'Functions by Complexity Rank', color: '#e6edf3' } },
    scales: { x: { ticks: { color: '#7d8590' }, grid: { color: '#30363d' } }, y: { ticks: { color: '#7d8590' }, grid: { color: '#30363d' } } },
  }
});
{% endif %}

// ── Security severity chart ──
{% if security_rows %}
const secCtx = document.getElementById('secChart').getContext('2d');
new Chart(secCtx, {
  type: 'doughnut',
  data: {
    labels: ['HIGH', 'MEDIUM', 'LOW'],
    datasets: [{
      data: [{{ sec_high }}, {{ sec_med }}, {{ sec_low }}],
      backgroundColor: ['#f85149', '#db6d28', '#d29922'],
      borderColor: '#161b22',
      borderWidth: 3,
    }]
  },
  options: {
    plugins: { legend: { labels: { color: '#e6edf3' } }, title: { display: true, text: 'Security Issues by Severity', color: '#e6edf3' } },
    cutout: '65%',
  }
});
{% endif %}

// ── Active nav highlight on scroll ──
const sections = document.querySelectorAll('section[id]');
const navLinks = document.querySelectorAll('nav a');
const observer = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      navLinks.forEach(l => l.classList.toggle('active', l.getAttribute('href') === '#' + e.target.id));
    }
  });
}, { rootMargin: '-30% 0px -60% 0px' });
sections.forEach(s => observer.observe(s));
</script>
</body>
</html>
"""

# ─── Recommendation generator ─────────────────────────────────────────────────

@dataclass
class Recommendation:
    icon: str
    title: str
    body: str

def _build_recommendations(report: AnalysisReport) -> List[Recommendation]:
    recs: List[Recommendation] = []

    if report.security:
        high = [s for s in report.security if s.severity == "HIGH"]
        if high:
            recs.append(Recommendation(
                "🚨", "Fix Critical Security Vulnerabilities",
                f"{len(high)} HIGH-severity security issue(s) detected. Prioritise reviewing "
                f"these immediately – they may lead to remote code execution, injection attacks, "
                f"or secret leakage."
            ))
        recs.append(Recommendation(
            "🔍", "Run Security Audit in CI/CD",
            "Integrate bandit and semgrep into your CI pipeline so every pull request is scanned "
            "for security regressions before merging."
        ))

    if any(c.complexity > 10 for c in report.complexity):
        recs.append(Recommendation(
            "🔀", "Refactor Complex Functions",
            f"{sum(1 for c in report.complexity if c.complexity > 10)} function(s) exceed a "
            "cyclomatic complexity of 10. Consider breaking them into smaller single-responsibility "
            "helpers and adding unit tests."
        ))

    if report.maintainability and any(m.mi_score < 50 for m in report.maintainability):
        recs.append(Recommendation(
            "📉", "Improve Low-Maintainability Files",
            "Several files have a Maintainability Index below 50 (rank C). Improve by adding "
            "docstrings, reducing nesting depth, and extracting constants."
        ))

    if report.dead_code:
        recs.append(Recommendation(
            "🧹", "Remove Dead Code",
            f"{len(report.dead_code)} unused import(s)/variable(s)/function(s) found. "
            "Dead code increases cognitive load and can hide bugs. Remove or refactor."
        ))

    if report.duplicates:
        recs.append(Recommendation(
            "📋", "Eliminate Code Duplication",
            f"{len(report.duplicates)} duplicate block(s) detected. Extract shared logic into "
            "utility functions or base classes to follow DRY principles."
        ))

    if report.dependencies:
        recs.append(Recommendation(
            "📦", "Update Vulnerable Dependencies",
            f"{len(report.dependencies)} dependency vulnerability(ies) found. Run `pip-audit --fix` "
            "or update pinned versions in requirements.txt / pyproject.toml."
        ))

    if report.pylint_score < 70:
        recs.append(Recommendation(
            "🧹", "Improve Pylint Score",
            f"Current pylint score is {report.pylint_score:.0f}/100. Address naming conventions, "
            "missing docstrings, and unused variable warnings to raise this above 80."
        ))

    if not recs:
        recs.append(Recommendation(
            "🎉", "Looking Good!",
            "No critical issues detected. Keep the quality bar high by running these checks "
            "regularly in your CI/CD pipeline."
        ))

    return recs


# ─── Jinja2 rendering ─────────────────────────────────────────────────────────

def _score_color_class(score: float) -> str:
    if score >= 80:
        return "stat-green"
    if score >= 50:
        return "stat-yellow"
    return "stat-red"

def _score_class(score: float) -> str:
    if score >= 80:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"

def _badge_class(count: int, threshold_warn: int = 5, threshold_err: int = 20) -> str:
    if count == 0:
        return ""
    if count < threshold_warn:
        return "yellow-badge"
    return "red-badge"

def _render_html(report: AnalysisReport) -> str:
    try:
        
        # pyrefly: ignore [missing-import]
        from jinja2 import Environment, BaseLoader, pass_eval_context  # noqa: F401
        # pyrefly: ignore [missing-import]
        import markupsafe  # noqa: F401
    except ImportError:
        raise RuntimeError("jinja2 required: pip install jinja2")

    import os as _os

    env = Environment(loader=BaseLoader(), autoescape=False)
    env.filters["basename"] = lambda p: _os.path.basename(p)
    env.filters["tojson"] = lambda x: json.dumps(x)
    # Safe slice for Jinja
    env.filters["lower"] = lambda s: s.lower() if isinstance(s, str) else s

    cc_rank_counts: Dict[str, int] = collections.Counter(c.rank for c in report.complexity)
    cc_labels = list("ABCDEF")
    cc_data = [cc_rank_counts.get(r, 0) for r in cc_labels]

    sec_high = sum(1 for s in report.security if s.severity == "HIGH")
    sec_med  = sum(1 for s in report.security if s.severity == "MEDIUM")
    sec_low  = sum(1 for s in report.security if s.severity == "LOW")

    lint_cat_counter: Dict[str, int] = collections.Counter(item.category for item in report.lint)
    lint_cats = list(lint_cat_counter.most_common(4))

    score_rows = [
        ("Quality",         report.quality_score,         _fill_class(report.quality_score)),
        ("Security",        report.security_score,        _fill_class(report.security_score)),
        ("Maintainability", report.maintainability_score, _fill_class(report.maintainability_score)),
        ("Complexity",      report.complexity_score,      _fill_class(report.complexity_score)),
        ("Pylint",          report.pylint_score,          _fill_class(report.pylint_score)),
    ]

    cc_dist = [
        ("A-B", cc_rank_counts.get("A", 0) + cc_rank_counts.get("B", 0), "fill-green"),
        ("C-D", cc_rank_counts.get("C", 0) + cc_rank_counts.get("D", 0), "fill-yellow"),
        ("E-F", cc_rank_counts.get("E", 0) + cc_rank_counts.get("F", 0), "fill-red"),
    ]

    recs = _build_recommendations(report)

    top_complexity = sorted(report.complexity, key=lambda x: x.complexity, reverse=True)[:100]
    top_security   = sorted(report.security, key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(x.severity, 3))[:200]
    top_lint       = report.lint[:300]
    top_dead       = report.dead_code[:200]
    top_dup        = report.duplicates[:100]
    top_deps       = sorted(report.dependencies, key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(x.severity, 3))

    ctx = dict(
        repo_name=_os.path.basename(report.repo_path) or report.repo_path,
        generated_at=report.generated_at[:19].replace("T", " "),
        quality_score=round(report.quality_score),
        security_score=round(report.security_score),
        maintainability_score=round(report.maintainability_score),
        complexity_score=round(report.complexity_score),
        pylint_score=round(report.pylint_score),
        files_analyzed=report.files_analyzed,
        total_lines=f"{report.total_lines:,}",
        # Colour classes
        score_class=_score_class(report.quality_score),
        sec_score_class=_score_color_class(report.security_score),
        mi_score_class=_score_color_class(report.maintainability_score),
        pylint_score_class=_score_color_class(report.pylint_score),
        security_count_class=_score_color_class(max(0, 100 - len(report.security) * 5)),
        deps_count_class=_score_color_class(max(0, 100 - len(report.dependencies) * 10)),
        # Counts
        complexity_count=len(report.complexity),
        security_count=len(report.security),
        lint_count=len(report.lint),
        dead_count=len(report.dead_code),
        dup_count=len(report.duplicates),
        deps_count=len(report.dependencies),
        # Badge classes
        complexity_badge_class=_badge_class(len([c for c in report.complexity if c.rank in "EF"])),
        security_badge_class=_badge_class(len(report.security), 1, 5),
        lint_badge_class=_badge_class(len(report.lint), 10, 50),
        deps_badge_class=_badge_class(len(report.dependencies), 1, 3),
        # Data rows
        complexity_rows=top_complexity,
        security_rows=top_security,
        lint_rows=top_lint,
        dead_rows=top_dead,
        dup_rows=top_dup,
        deps_rows=top_deps,
        lint_cats=lint_cats,
        score_rows=score_rows,
        cc_labels=cc_labels,
        cc_data=cc_data,
        cc_dist=cc_dist,
        sec_sev_counts=[("HIGH", sec_high), ("MEDIUM", sec_med), ("LOW", sec_low)],
        sec_high=sec_high, sec_med=sec_med, sec_low=sec_low,
        recommendations=recs,
    )

    template = env.from_string(HTML_TEMPLATE)
    return template.render(**ctx)


def _fill_class(score: float) -> str:
    if score >= 80:
        return "fill-green"
    if score >= 50:
        return "fill-yellow"
    return "fill-red"


# ─── CSV / JSON export ────────────────────────────────────────────────────────

def _export_json(report: AnalysisReport, path: Path) -> None:
    data = asdict(report)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _export_csv(report: AnalysisReport, output_dir: Path) -> None:
    def write(name: str, rows: List[Any], fields: List[str]) -> None:
        p = output_dir / f"{name}.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for row in rows:
                w.writerow(asdict(row) if hasattr(row, "__dataclass_fields__") else row)

    write("complexity",    report.complexity,    ["file", "function", "complexity", "rank", "line"])
    write("security",      report.security,      ["file", "line", "severity", "confidence", "issue_id", "description", "tool"])
    write("lint",          report.lint,          ["file", "line", "column", "symbol", "message", "category"])
    write("dead_code",     report.dead_code,     ["file", "line", "kind", "name"])
    write("duplicates",    report.duplicates,    ["file_a", "start_a", "file_b", "start_b", "lines", "fingerprint"])
    write("dependencies",  report.dependencies,  ["package", "installed_version", "vulnerability_id", "severity", "description", "fix_version"])


# ─── Main orchestrator ────────────────────────────────────────────────────────

def codeReport(
    repo_path: str,
    output_dir: str = "reports",
    emit_html: bool = True,
    emit_json: bool = True,
    emit_csv: bool = True,
    verbose: bool = False,
    exclude: Optional[List[str]] = None,
    threads: int = 4,
) -> Tuple[str, Dict[str, Any]]:
    """
    Analyse a Python source repository and produce a standalone HTML code quality report.

    Args:
        repo_path:  Path to the repository root.
        output_dir: Where to write reports (default: 'reports').
        emit_html:  Write an HTML report.
        emit_json:  Write a JSON report.
        emit_csv:   Write CSV summaries.
        verbose:    Enable debug logging.
        exclude:    Extra glob patterns to exclude from file collection.
        threads:    Worker thread count.

    Returns:
        (html_report_path, summary_dict)
    """
    global log
    log = _setup_logging(verbose)

    repo = Path(repo_path).resolve()
    if not repo.exists():
        raise FileNotFoundError(f"Repository path not found: {repo}")

    log.info(f"Analysing repository: {repo}")
    t_start = time.time()

    # Prepare output dirs
    out = Path(output_dir)
    html_dir = out / "html"
    json_dir = out / "json"
    csv_dir  = out / "csv"
    for d in (out, html_dir, json_dir, csv_dir, out / "assets"):
        d.mkdir(parents=True, exist_ok=True)

    # Collect files
    log.info("Collecting Python files…")
    files = _collect_python_files(repo, exclude or [])
    log.info(f"  Found {len(files)} Python files")

    report = AnalysisReport(repo_path=str(repo))
    report.files_analyzed = len(files)
    report.total_lines = sum(
        len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        for p in files
    )

    # Run analysers concurrently
    def run_complexity():
        log.info("Running complexity analysis (radon)…")
        cc, mi = ComplexityAnalyzer().analyze(files)
        report.complexity = cc
        report.maintainability = mi

    def run_security():
        log.info("Running security analysis (bandit/semgrep)…")
        report.security = SecurityAnalyzer().analyze(repo)

    def run_lint():
        log.info("Running linting (pylint)…")
        issues, score = LintAnalyzer().analyze(repo)
        report.lint = issues
        report.pylint_score = score

    def run_dead_code():
        log.info("Running dead code detection (vulture/AST)…")
        report.dead_code = DeadCodeAnalyzer().analyze(files)

    def run_duplicates():
        log.info("Running duplicate detection…")
        report.duplicates = DuplicateAnalyzer().analyze(files)

    def run_deps():
        log.info("Running dependency analysis (pip-audit/safety)…")
        report.dependencies = DependencyAnalyzer().analyze(repo)

    tasks = [run_complexity, run_security, run_lint, run_dead_code, run_duplicates, run_deps]

    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {pool.submit(t): t.__name__ for t in tasks}
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as exc:
                log.warning(f"Analyser {name} failed: {exc}")
                report.errors.append(f"{name}: {exc}")

    # Score calculation
    _calculate_scores(report)

    elapsed = time.time() - t_start
    log.info(f"Analysis complete in {elapsed:.1f}s")
    log.info(f"  Quality Score:       {report.quality_score}")
    log.info(f"  Security Score:      {report.security_score}")
    log.info(f"  Maintainability:     {report.maintainability_score}")

    # Write reports
    html_path = ""
    if emit_html:
        html_path = str(html_dir / "code_quality_report.html")
        log.info(f"Generating HTML report → {html_path}")
        html = _render_html(report)
        Path(html_path).write_text(html, encoding="utf-8")
        # Also write to reports root for convenience
        (out / "code_quality_report.html").write_text(html, encoding="utf-8")

    if emit_json:
        jp = json_dir / "code_quality_report.json"
        log.info(f"Writing JSON report → {jp}")
        _export_json(report, jp)

    if emit_csv:
        log.info(f"Writing CSV summaries → {csv_dir}")
        _export_csv(report, csv_dir)

    summary: Dict[str, Any] = {
        "quality_score":         report.quality_score,
        "security_score":        report.security_score,
        "maintainability_score": report.maintainability_score,
        "complexity_score":      report.complexity_score,
        "pylint_score":          report.pylint_score,
        "files_analyzed":        report.files_analyzed,
        "total_lines":           report.total_lines,
        "security_issues":       len(report.security),
        "lint_issues":           len(report.lint),
        "dead_code_items":       len(report.dead_code),
        "duplicate_blocks":      len(report.duplicates),
        "vulnerable_dependencies": len(report.dependencies),
        "errors":                report.errors,
        "html_report":           html_path,
        "elapsed_seconds":       round(elapsed, 2),
    }

    return html_path, summary


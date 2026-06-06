# Reports

---

### `report system`
Generate an advanced system report and open it in the browser.

```bash
toolbook report system
```

**Example:**
```bash
toolbook report system
```

**Python:**
```python
from toolbook.tReports import SystemReport

# Save report to a custom path and open it automatically
output_path = SystemReport(
    output_path="my_system_report.html",
    open_report=True
)
print(output_path)
```

---

### `report webscan`
Scan a URL and generate an advanced web report, then open it in the browser.

```bash
toolbook report webscan <URL> [--delay/-d SECONDS]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `URL` | Yes | Target URL to scan |
| `-d`, `--delay` | No | Delay in seconds before scanning (default: `0`) |

**Examples:**
```bash
# Basic scan
toolbook report webscan https://example.com

# Scan with a 3-second delay
toolbook report webscan https://dashboard.grademe-ai.com/login -d 3
```

**Python:**
```python
from toolbook.tReports import webReport

# Basic scan — saves to ~/Downloads/WebReport by default
report_path, summary = webReport("https://example.com")
print(report_path)
print(summary["overall_score"])

# Custom output directory with delay and auto-open
report_path, summary = webReport(
    url="https://example.com",
    out_dir="./my-reports/web",
    delay=3,
    open_report=True
)
```

---

### `report codescan`
Generate a professional Code Quality Report for a Python repository.
Output is saved to `~/Downloads/CodeQualityReport`.

```bash
toolbook report codescan <PATH>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `PATH` | Yes | Path to the local repository to analyse |

**Example:**
```bash
toolbook report codescan C:\Users\me\projects\my-repo
```

**Python:**
```python
from toolbook.tReports import codeReport

# Analyse a repo with default settings
report_path, summary = codeReport("C:/Users/me/projects/my-repo")
print(report_path)
print(f"Quality Score: {summary['quality_score']}")

# Full control over output and analysis options
report_path, summary = codeReport(
    repo_path="C:/Users/me/projects/my-repo",
    output_dir="./reports/code",
    emit_html=True,
    emit_json=True,
    emit_csv=False,
    verbose=True,
    threads=4
)
```

---

### `report git-repo`
Generate an intelligence report for a GitHub repository.
Output is saved to `~/Downloads/GitRepoReport` by default.

```bash
toolbook report git-repo <REPO_URL> [--token TOKEN] [--output-dir DIR] [--verbose]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `REPO_URL` | Yes | GitHub repository URL |
| `--token` | No | GitHub PAT (falls back to `GITHUB_TOKEN` env var) |
| `--output-dir` | No | Custom output directory |
| `--verbose` | No | Enable verbose logging |

**Examples:**
```bash
# Using a stored token
toolbook report git-repo https://github.com/torvalds/linux

# Passing a token inline
toolbook report git-repo https://github.com/torvalds/linux --token ghp_abc123xyz456

# Custom output directory with verbose logging
toolbook report git-repo https://github.com/torvalds/linux --output-dir C:\Reports --verbose
```

**Python:**
```python
from toolbook.tReports import gitRepoReport

# Uses GITHUB_TOKEN from environment automatically
report_path, summary = gitRepoReport("https://github.com/torvalds/linux")
print(report_path)
print(f"Health Score : {summary['health_score']}")
print(f"Contributors : {summary['contributors']}")

# With explicit token and custom output
report_path, summary = gitRepoReport(
    "https://github.com/torvalds/linux",
    token="ghp_abc123xyz456",
    output_dir="./reports/repos",
    verbose=True
)
```

---

### `report git-user`
Generate an intelligence report for a GitHub user.
Output is saved to `~/Downloads/GitUserReport` by default.

```bash
toolbook report git-user <USERNAME> [--token TOKEN] [--output-dir DIR]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `USERNAME` | Yes | GitHub username |
| `--token` | No | GitHub PAT (falls back to `GITHUB_TOKEN` env var) |
| `--output-dir` | No | Custom output directory |

**Examples:**
```bash
# Using a stored token
toolbook report git-user torvalds

# Passing a token inline
toolbook report git-user torvalds --token ghp_abc123xyz456

# Custom output directory
toolbook report git-user torvalds --output-dir C:\Reports\Users
```

**Python:**
```python
from toolbook.tReports import gitUserReport

# Uses GITHUB_TOKEN from environment automatically
report_path, summary = gitUserReport("torvalds")
print(report_path)
print(f"Overall Score      : {summary['overall_score']}")
print(f"Productivity Score : {summary['productivity_score']}")
print(f"Public Repos       : {summary['repositories']}")

# With explicit token and custom output
report_path, summary = gitUserReport(
    username="torvalds",
    token="ghp_abc123xyz456",
    output_dir="./reports/users"
)
```

# Toolbook Command Book

## Token Management

### `set-token`
Store a secret token in the Toolbook environment (`~/.toolbook/.env`).

```bash
toolbook set-token <TOKEN_NAME> <TOKEN_VALUE>
```

**Example:**
```bash
toolbook set-token GITHUB_TOKEN ghp_abc123xyz456
```

---

### `show-tokens`
List all configured token names (values are never shown).

```bash
toolbook show-tokens
```

**Example:**
```bash
toolbook show-tokens
# Configured Tokens:
#   - GITHUB_TOKEN
```

---

## Reports

### `report system`
Generate an advanced system report and open it in the browser.

```bash
toolbook report system
```

**Example:**
```bash
toolbook report system
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

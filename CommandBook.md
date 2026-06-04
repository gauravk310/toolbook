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

---

## System Info

All `sys info-*` commands accept a `--json` flag to output raw JSON instead of the formatted view.

---

### `sys info`
Show complete system information — OS, CPU, memory, disk, battery, network, and uptime — in one view.

```bash
toolbook sys info [--json]
```

**Example:**
```bash
toolbook sys info
toolbook sys info --json
```

---

### `sys info-system`
Show OS and machine details (platform, node name, release, version, architecture, processor).

```bash
toolbook sys info-system [--json]
```

**Example:**
```bash
toolbook sys info-system
```

---

### `sys info-cpu`
Show CPU core count, usage percentage, per-core usage bars, clock frequencies, and load average.

```bash
toolbook sys info-cpu [--json]
```

**Example:**
```bash
toolbook sys info-cpu
```

---

### `sys info-memory`
Show total, available, and used RAM with usage percentage.

```bash
toolbook sys info-memory [--json]
```

**Example:**
```bash
toolbook sys info-memory
```

---

### `sys info-disk`
Show all disk partitions with file system type, total/used/free space, and usage percentage.

```bash
toolbook sys info-disk [--json]
```

**Example:**
```bash
toolbook sys info-disk
```

---

### `sys info-battery`
Show battery charge percentage, charging state, and estimated time remaining.

```bash
toolbook sys info-battery [--json]
```

**Example:**
```bash
toolbook sys info-battery
```

---

### `sys info-network`
Show hostname and primary IP address.

```bash
toolbook sys info-network [--json]
```

**Example:**
```bash
toolbook sys info-network
```

---

### `sys info-uptime`
Show the boot timestamp and time elapsed since last power-on in seconds, minutes, hours, and a combined `Xd XXh XXm XXs` format.

```bash
toolbook sys info-uptime [--json]
```

**Example:**
```bash
toolbook sys info-uptime
# Booted At    2026-05-30 06:23:55
# Seconds      440,684 s
# Minutes      7,344.73 min
# Hours        122.41 hr
# Total Uptime 5d 02h 24m 44s
```

---

### `sys organize-files`
Organise files in a folder into typed sub-folders: Images, Videos, Documents, PDFs, Music, Archives, Others.

```bash
toolbook sys organize-files <FOLDER_PATH>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `FOLDER_PATH` | Yes | Path to the folder to organise |

**Example:**
```bash
toolbook sys organize-files C:\Users\me\Downloads
```

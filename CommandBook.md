# Toolbook Command Book

Quick reference index for all Toolbook CLI commands.  
Each section links to a dedicated reference file in the `docs/` folder.

---

## Sections

| Section | File | Commands |
|---------|------|----------|
| [Token Management](docs/token-management.md) | `docs/token-management.md` | `set-token`, `show-tokens` |
| [Reports](docs/reports.md) | `docs/reports.md` | `report system`, `report webscan`, `report codescan`, `report git-repo`, `report git-user` |
| [System Info](docs/system-info.md) | `docs/system-info.md` | `sys info`, `sys info-*`, `sys organize-files` |
| [PDF Tools](docs/pdf-tools.md) | `docs/pdf-tools.md` | `doc pdf merge`, `doc pdf split`, `doc pdf extract-img`, `doc pdf pdf-to-docx`, `doc pdf docx-to-pdf`, `doc pdf imgs-to-pdf`, `doc pdf pdf-to-imgs` |
| [Image Tools](docs/img-tools.md) | `docs/img-tools.md` | `doc img convert-png`, `doc img convert-jpg`, `doc img convert-jpeg` |

---

## Quick Reference

### Token Management
```bash
toolbook set-token <TOKEN_NAME> <TOKEN_VALUE>
toolbook show-tokens
```

### Reports
```bash
toolbook report system
toolbook report webscan <URL> [--delay SECONDS]
toolbook report codescan <PATH>
toolbook report git-repo <REPO_URL> [--token TOKEN] [--output-dir DIR] [--verbose]
toolbook report git-user <USERNAME> [--token TOKEN] [--output-dir DIR]
```

### System Info
```bash
toolbook sys info [--json]
toolbook sys info-system [--json]
toolbook sys info-cpu [--json]
toolbook sys info-memory [--json]
toolbook sys info-disk [--json]
toolbook sys info-battery [--json]
toolbook sys info-network [--json]
toolbook sys info-uptime [--json]
toolbook sys organize-files <FOLDER_PATH>
```

### PDF Tools
```bash
toolbook doc pdf merge <PDF_DIR> <OUTPUT_DIR> [--open]
toolbook doc pdf split <PDF_FILE> [OUTPUT_PATH] [--open]
toolbook doc pdf extract-img <PDF_FILE> [OUTPUT_PATH] [--open]
toolbook doc pdf pdf-to-docx <PDF_FILE> [OUTPUT_PATH] [--open]
toolbook doc pdf docx-to-pdf <DOCX_FILE> [OUTPUT_PATH] [--open]
toolbook doc pdf imgs-to-pdf <IMAGES_DIR> [OUTPUT_PATH] [--open]
toolbook doc pdf pdf-to-imgs <PDF_FILE> [OUTPUT_PATH] [--dpi INT] [--open]
```

### Image Tools
```bash
toolbook doc img convert-png  <IMAGE_FILE> [OUTPUT_PATH] [--open]
toolbook doc img convert-jpg  <IMAGE_FILE> [OUTPUT_PATH] [--open]
toolbook doc img convert-jpeg <IMAGE_FILE> [OUTPUT_PATH] [--open]
```

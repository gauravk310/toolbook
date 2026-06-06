<div align="center">

# 🛠️ Toolbook

**A Python toolkit for document processing, system diagnostics, and intelligent reporting.**

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-orange.svg)](pyproject.toml)

</div>

---

## What is Toolbook?

Toolbook is a developer-focused Python toolkit that brings document manipulation, system diagnostics, and professional report generation together under a single, consistent interface. It is designed to work both as a CLI tool you reach for in the terminal and as an importable Python library you can embed directly into your own scripts and applications.

The core philosophy is simplicity — every capability is one import or one command away, with no configuration required to get started.

---

## Capabilities

Toolbook is organised into three functional domains:

**Documents (`tDocs`)** handles all file transformation work — merging and splitting PDFs, converting between PDF and DOCX, rendering PDF pages as images, combining images into PDFs, and converting image formats. It wraps `pypdf`, `pillow`, and the Microsoft Word COM interface into a clean, consistent API.

**Reports (`tReports`)** generates rich HTML intelligence reports. It can profile your local machine, audit a website for performance and structure, analyse the code quality of a Python repository, or produce a deep-dive report on a GitHub repository or user. It pulls together `playwright`, `PyGithub`, `pylint`, `radon`, `bandit`, and more, presenting results in a single self-contained HTML file.

**System (`tSys`)** exposes live system metrics — CPU, RAM, disk, battery, network, and uptime — as structured Python dictionaries. It also provides a file organiser that automatically sorts a messy folder into typed sub-folders.

---

## Architecture

```
toolbook/
│
├── src/toolbook/
│   │
│   ├── cli.py                  # Typer entry point, token management commands
│   │
│   ├── utils.py                # Shared helpers (e.g. get_token)
│   │
│   ├── commands/               # CLI layer — thin wrappers over the library modules
│   │   ├── doc.py              # Registers doc pdf / doc img sub-commands
│   │   ├── reports.py          # Registers report sub-commands
│   │   └── sys.py              # Registers sys sub-commands
│   │
│   ├── tDocs/                  # Document processing library
│   │   ├── PDF.py              # PDFMerger, PDFSplit, PDFToDocx, DocxToPDF, …
│   │   ├── IMG.py              # IMGConvertToPNG, IMGConvertToJPG
│   │   └── __init__.py         # Public re-exports
│   │
│   ├── tReports/               # Report generation engines
│   │   ├── systemReport.py     # HTML system health report
│   │   ├── webReport.py        # Website audit report (Playwright-based)
│   │   ├── codeReport.py       # Python code quality report
│   │   ├── gitRepoReport.py    # GitHub repository intelligence report
│   │   ├── gitUserReport.py    # GitHub user intelligence report
│   │   └── __init__.py         # Public re-exports
│   │
│   └── tSys/                   # System tools library
│       ├── sysInfo.py          # SysInfo — live hardware and OS metrics
│       ├── fileOrganizer.py    # FileOrganizer — sorts files into sub-folders
│       └── __init__.py         # Public re-exports
│
├── docs/                       # Per-module reference documentation
│   ├── pdf-tools.md
│   ├── img-tools.md
│   ├── reports.md
│   ├── system-info.md
│   └── token-management.md
│
├── tests/                      # Test suite
├── pyproject.toml              # Build configuration and dependencies
└── requirements.txt            # Pinned runtime dependencies
```

### Design Principles

**CLI and library are the same thing.** The `commands/` layer contains only argument parsing and output formatting. All real logic lives in `tDocs`, `tReports`, and `tSys`, so you can import any capability directly into your own Python code without going through the CLI.

**Modules are self-contained.** Each module in `tDocs`, `tReports`, and `tSys` operates independently. Importing `tDocs` does not pull in anything from `tReports` or `tSys`. This keeps import times low and makes the library easy to embed selectively.

**Token management is file-based.** API tokens (e.g. `GITHUB_TOKEN`) are stored in `~/.toolbook/.env` and loaded into environment variables at startup. Commands that need tokens read them from the environment, so tokens are set once and used everywhere without repeating them on the command line.

---

## Installation

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ toolbook
```

Requires Python 3.9 or higher.

---

## Documentation

Detailed reference for each module lives in the [`docs/`](docs/) folder:

- [PDF Tools](docs/pdf-tools.md)
- [Image Tools](docs/img-tools.md)
- [Reports](docs/reports.md)
- [System Info](docs/system-info.md)
- [Token Management](docs/token-management.md)

---

## License

[MIT](LICENSE) © Gaurav Kadam

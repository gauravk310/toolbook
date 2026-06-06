import os
from pathlib import Path
from typing import Optional
import typer
from toolbook import __version__
from toolbook.commands.reports import app as reports_app
from toolbook.commands.sys import app as sys_app
from toolbook.commands.doc import app as doc_app

# Load environment variables from ~/.toolbook/.env
env_file = Path.home() / ".toolbook" / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k not in os.environ:
                os.environ[k] = v.strip()

app = typer.Typer()


def _version_callback(value: bool) -> None:
    if value:
        typer.secho(f"Toolbook v{__version__}", fg=typer.colors.CYAN, bold=True)
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show the Toolbook version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Toolbook — document processing, system diagnostics, and reporting toolkit."""

app.add_typer(reports_app, name="report")

app.add_typer(sys_app, name="sys")

app.add_typer(doc_app, name="doc")


@app.command("set-token")
def set_token(
    token_name: str = typer.Argument(..., help="Name of the token (e.g. GITHUB_TOKEN)"),
    token_value: str = typer.Argument(..., help="Value of the token"),
):
    """
    Set secret tokens in the Toolbook environment.
    """
    env_dir = Path.home() / ".toolbook"
    env_dir.mkdir(parents=True, exist_ok=True)
    env_file = env_dir / ".env"

    # Read existing env
    lines = []
    found = False
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{token_name}="):
                lines.append(f"{token_name}={token_value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{token_name}={token_value}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    typer.secho(f"Successfully set {token_name}.", fg=typer.colors.GREEN)


@app.command("show-tokens")
def show_tokens():
    """
    List all configured secret token names.
    """
    env_file = Path.home() / ".toolbook" / ".env"
    if not env_file.exists():
        typer.secho("No tokens configured yet.", fg=typer.colors.YELLOW)
        return

    tokens = []
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _ = line.split("=", 1)
            tokens.append(k.strip())

    if not tokens:
        typer.secho("No tokens configured yet.", fg=typer.colors.YELLOW)
        return

    typer.secho("Configured Tokens:", fg=typer.colors.CYAN, bold=True)
    for t in tokens:
        typer.secho(f"  - {t}", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()

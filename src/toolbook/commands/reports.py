import typer
from toolbook.tReports import (
    SystemReport,
    webReport,
    codeReport,
    gitRepoReport,
    gitUserReport,
)
from pathlib import Path

app = typer.Typer()


@app.command()
def system(output: str = "system_report.html"):
    """
    Generate advanced system report
    """

    SystemReport(open_report=True)

    typer.secho("System report generated successfully", fg=typer.colors.GREEN)


@app.command()
def webscan(
    url: str = typer.Argument(..., help="Target URL, e.g. https://example.com"),
    delay: int = typer.Option(
        0, "-d", "--delay", help="Delay in seconds before scanning"
    ),
):
    """
    Generate advanced web report
    """

    webReport(url, delay=delay, open_report=True)

    typer.secho("Web report generated successfully", fg=typer.colors.GREEN)


@app.command()
def codescan(path: str = typer.Argument(..., help="Path to the repository to analyse")):
    """
    Generate professional Code Quality Report for a Python repository.
    """
    downloads_dir = str(Path.home() / "Downloads" / "CodeQualityReport")

    codeReport(repo_path=path, output_dir=downloads_dir)

    typer.secho(
        f"Code report generated successfully in {downloads_dir}", fg=typer.colors.GREEN
    )


@app.command("git-repo")
def git_repo(
    repo_url: str = typer.Argument(..., help="GitHub repository URL"),
    token: str = typer.Option(None, help="GitHub PAT (optional)"),
    output_dir: str = typer.Option(None, help="Output directory"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose logging"),
):
    """
    Generate professional Intelligence Report for a GitHub repository.
    """
    from toolbook.utils import get_token

    token = token or get_token("GITHUB_TOKEN")

    if output_dir is None:
        output_dir = str(Path.home() / "Downloads" / "GitRepoReport")

    path, summary = gitRepoReport(
        repo_url=repo_url, token=token, output_dir=output_dir, verbose=verbose
    )

    typer.secho(
        f"Git Repo report generated successfully in {path}", fg=typer.colors.GREEN
    )


@app.command("git-user")
def git_user(
    username: str = typer.Argument(..., help="GitHub username"),
    token: str = typer.Option(None, help="GitHub PAT (optional)"),
    output_dir: str = typer.Option(None, help="Output directory"),
):
    """
    Generate professional Intelligence Report for a GitHub user.
    """
    from toolbook.utils import get_token

    token = token or get_token("GITHUB_TOKEN")

    if output_dir is None:
        output_dir = str(Path.home() / "Downloads" / "GitUserReport")

    path, summary = gitUserReport(username=username, token=token, output_dir=output_dir)

    typer.secho(
        f"Git User report generated successfully in {path}", fg=typer.colors.GREEN
    )

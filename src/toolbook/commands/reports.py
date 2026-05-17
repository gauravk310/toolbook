import typer
from toolbook.tReports import SystemReport, webReport, codeReport
from pathlib import Path

app = typer.Typer()


@app.command()
def system(output: str = "system_report.html"):
    """
    Generate advanced system report
    """

    SystemReport(open_report=True)
    
    typer.secho(
        "System report generated successfully",
        fg=typer.colors.GREEN
    )

@app.command()
def webscan(
    url: str = typer.Argument(..., help="Target URL, e.g. https://example.com"),
    delay: int = typer.Option(0, "-d", "--delay", help="Delay in seconds before scanning")
):
    """
    Generate advanced web report
    """

    webReport(url, delay=delay, open_report=True)
    
    typer.secho(
        "Web report generated successfully",
        fg=typer.colors.GREEN
    )

@app.command()
def codescan(
    path: str = typer.Argument(..., help="Path to the repository to analyse")
):
    """
    Generate professional Code Quality Report for a Python repository.
    """
    downloads_dir = str(Path.home() / "Downloads" / "CodeQualityReport")
    
    codeReport(
        repo_path=path,
        output_dir=downloads_dir
    )
    
    typer.secho(
        f"Code report generated successfully in {downloads_dir}",
        fg=typer.colors.GREEN
    )
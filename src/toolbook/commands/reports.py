import typer
from toolbook.tReports import SystemReport, webReport

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
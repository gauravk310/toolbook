import typer
from toolbook.tReports import SystemReport

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
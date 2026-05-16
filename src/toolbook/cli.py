import typer
from toolbook.commands.reports import app as reports_app

app = typer.Typer()

app.add_typer(
    reports_app,
    name="report"
)


if __name__ == "__main__":
    app()
import os
import typer
from toolbook.tSys import FileOrganizer

app = typer.Typer()


@app.command("organize-files")
def organize_files(
    folder_path: str = typer.Argument(..., help="Path to the folder you want to organise"),
):
    """
    Organise files in FOLDER_PATH into typed sub-folders
    (Images, Videos, Documents, PDFs, Music, Archives, Others).
    """
    abs_path = os.path.abspath(folder_path)

    typer.secho(f"\n📂 Target Directory: {abs_path}", fg=typer.colors.CYAN, bold=True)

    confirmed = typer.confirm("Organise files in this folder?")
    if not confirmed:
        typer.secho("❌ Cancelled.", fg=typer.colors.YELLOW)
        raise typer.Exit()

    FileOrganizer(abs_path)

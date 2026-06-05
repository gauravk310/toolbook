import typer
from toolbook.tDocs import PDFMerger, PDFSplit

app = typer.Typer()

# ── pdf sub-group ─────────────────────────────────────────────────────────────
pdf_app = typer.Typer(help="PDF utilities")
app.add_typer(pdf_app, name="pdf")


@pdf_app.command("merge")
def pdf_merge(
    pdfs_dir: str = typer.Argument(..., help="Directory containing the PDF files to merge"),
    output_dir: str = typer.Argument(..., help="Directory where the merged PDF will be saved"),
):
    """
    Merge all PDFs in a directory into a single file.

    Example:
        toolbook doc pdf merge ./my-pdfs ./output
    """
    result = PDFMerger(pdfs_dir, output_dir)

    if result.startswith("Error") or result.startswith("Need"):
        typer.secho(f"❌ {result}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"✅ Merged PDF saved to: {result}", fg=typer.colors.GREEN)


@pdf_app.command("split")
def pdf_split(
    pdf_file: str = typer.Argument(..., help="Path to the PDF file to split"),
    output_path: str = typer.Argument(
        None,
        help=(
            "Base directory where the split folder will be created. "
            "Omit to use ~/Downloads, use '.' for the current directory."
        ),
    ),
):
    """
    Split a PDF into individual pages.

    Each page is saved inside a folder named after the source PDF.

    Examples:
        toolbook doc pdf split ./document.pdf
        toolbook doc pdf split ./document.pdf .
        toolbook doc pdf split ./document.pdf ./output
    """
    def _log(msg: str) -> None:
        typer.echo(msg)

    result = PDFSplit(pdf_file, output_path, log=_log)

    if result.startswith("Error"):
        typer.secho(f"\n❌ {result}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"\n✅ Done — split pages saved to: {result}", fg=typer.colors.GREEN)

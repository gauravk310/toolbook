import os
import typer
from toolbook.tDocs import PDFMerger, PDFSplit, PDFIMGExtractor, PDFToDocx

app = typer.Typer()

# ── pdf sub-group ─────────────────────────────────────────────────────────────
pdf_app = typer.Typer(help="PDF utilities")
app.add_typer(pdf_app, name="pdf")


def _open_path(path: str) -> None:
    """Open a file or folder in the OS default application / explorer."""
    os.startfile(os.path.abspath(path))


@pdf_app.command("merge")
def pdf_merge(
    pdfs_dir: str = typer.Argument(..., help="Directory containing the PDF files to merge"),
    output_dir: str = typer.Argument(..., help="Directory where the merged PDF will be saved"),
    open_doc: bool = typer.Option(False, "--open", help="Open the merged PDF after saving"),
):
    """
    Merge all PDFs in a directory into a single file.

    Examples:
        toolbook doc pdf merge ./my-pdfs ./output
        toolbook doc pdf merge ./my-pdfs ./output --open
    """
    def _log(msg: str) -> None:
        typer.echo(msg)

    result = PDFMerger(pdfs_dir, output_dir, log=_log)

    if result.startswith("Error") or result.startswith("Need"):
        typer.secho(f"\n❌ {result}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"\n✅ Done — merged PDF saved to: {result}", fg=typer.colors.GREEN)

    if open_doc:
        _open_path(result)


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
    open_doc: bool = typer.Option(False, "--open", help="Open the output folder after splitting"),
):
    """
    Split a PDF into individual pages.

    Each page is saved inside a folder named after the source PDF.

    Examples:
        toolbook doc pdf split ./document.pdf
        toolbook doc pdf split ./document.pdf . --open
        toolbook doc pdf split ./document.pdf ./output --open
    """
    def _log(msg: str) -> None:
        typer.echo(msg)

    result = PDFSplit(pdf_file, output_path, log=_log)

    if result.startswith("Error"):
        typer.secho(f"\n❌ {result}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"\n✅ Done — split pages saved to: {result}", fg=typer.colors.GREEN)

    if open_doc:
        _open_path(result)


@pdf_app.command("extract-img")
def pdf_extract_img(
    pdf_file: str = typer.Argument(..., help="Path to the PDF file to extract images from"),
    output_path: str = typer.Argument(
        None,
        help=(
            "Base directory where the images folder will be created. "
            "Omit to use ~/Downloads, use '.' for the current directory."
        ),
    ),
    open_doc: bool = typer.Option(False, "--open", help="Open the output folder after extracting"),
):
    """
    Extract all images from a PDF into individual files.

    Images are saved inside a folder named after the source PDF.

    Examples:
        toolbook doc pdf extract-img ./document.pdf
        toolbook doc pdf extract-img ./document.pdf . --open
        toolbook doc pdf extract-img ./document.pdf ./output --open
    """
    def _log(msg: str) -> None:
        typer.echo(msg)

    result = PDFIMGExtractor(pdf_file, output_path, log=_log)

    if result.startswith("Error"):
        typer.secho(f"\n❌ {result}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"\n✅ Done — images saved to: {result}", fg=typer.colors.GREEN)

    if open_doc:
        _open_path(result)


@pdf_app.command("convert-docx")
def pdf_convert_docx(
    pdf_file: str = typer.Argument(..., help="Path to the PDF file to convert"),
    output_path: str = typer.Argument(
        None,
        help=(
            "Directory where the .docx file will be saved. "
            "Omit to use ~/Downloads, use '.' for the current directory."
        ),
    ),
    open_doc: bool = typer.Option(False, "--open", help="Open the generated .docx file after conversion"),
):
    """
    Convert a PDF to DOCX format.

    Examples:
        toolbook doc pdf convert-docx ./document.pdf
        toolbook doc pdf convert-docx ./document.pdf . --open
        toolbook doc pdf convert-docx ./document.pdf ./output --open
    """
    def _log(msg: str) -> None:
        typer.echo(msg)

    result = PDFToDocx(pdf_file, output_path, log=_log)

    if result.startswith("Error"):
        typer.secho(f"\n❌ {result}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"\n✅ Done — DOCX saved to: {result}", fg=typer.colors.GREEN)

    if open_doc:
        _open_path(result)

import os
import typer
from toolbook.tDocs import (
    PDFMerger,
    PDFSplit,
    PDFIMGExtractor,
    PDFToDocx,
    DocxToPDF,
    IMGsToPDF,
    PDFToIMGs,
    IMGConvertToPNG,
    IMGConvertToJPG,
)

app = typer.Typer()

# ── pdf sub-group ─────────────────────────────────────────────────────────────
pdf_app = typer.Typer(help="PDF utilities")
app.add_typer(pdf_app, name="pdf")

# ── img sub-group ─────────────────────────────────────────────────────────────
img_app = typer.Typer(help="Image utilities")
app.add_typer(img_app, name="img")


def _open_path(path: str) -> None:
    """Open a file or folder in the OS default application / explorer."""
    os.startfile(os.path.abspath(path))


@pdf_app.command("merge")
def pdf_merge(
    pdfs_dir: str = typer.Argument(
        ..., help="Directory containing the PDF files to merge"
    ),
    output_dir: str = typer.Argument(
        ..., help="Directory where the merged PDF will be saved"
    ),
    open_doc: bool = typer.Option(
        False, "--open", help="Open the merged PDF after saving"
    ),
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
    open_doc: bool = typer.Option(
        False, "--open", help="Open the output folder after splitting"
    ),
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
    pdf_file: str = typer.Argument(
        ..., help="Path to the PDF file to extract images from"
    ),
    output_path: str = typer.Argument(
        None,
        help=(
            "Base directory where the images folder will be created. "
            "Omit to use ~/Downloads, use '.' for the current directory."
        ),
    ),
    open_doc: bool = typer.Option(
        False, "--open", help="Open the output folder after extracting"
    ),
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
    open_doc: bool = typer.Option(
        False, "--open", help="Open the generated .docx file after conversion"
    ),
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


@pdf_app.command("convert-pdf")
def pdf_convert_pdf(
    docx_file: str = typer.Argument(..., help="Path to the DOCX file to convert"),
    output_path: str = typer.Argument(
        None,
        help=(
            "Directory where the .pdf file will be saved. "
            "Omit to use ~/Downloads, use '.' for the current directory."
        ),
    ),
    open_doc: bool = typer.Option(
        False, "--open", help="Open the generated PDF after conversion"
    ),
):
    """
    Convert a DOCX file to PDF format.

    Requires Microsoft Word to be installed on Windows.

    Examples:
        toolbook doc pdf convert-pdf ./document.docx
        toolbook doc pdf convert-pdf ./document.docx . --open
        toolbook doc pdf convert-pdf ./document.docx ./output --open
    """

    def _log(msg: str) -> None:
        typer.echo(msg)

    result = DocxToPDF(docx_file, output_path, log=_log)

    if result.startswith("Error"):
        typer.secho(f"\n❌ {result}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"\n✅ Done — PDF saved to: {result}", fg=typer.colors.GREEN)

    if open_doc:
        _open_path(result)


@pdf_app.command("imgs-to-pdf")
def pdf_imgs_to_pdf(
    images_dir: str = typer.Argument(
        ..., help="Directory containing the image files to combine"
    ),
    output_path: str = typer.Argument(
        None,
        help=(
            "Directory where the PDF will be saved. "
            "Omit to use ~/Downloads, use '.' for the current directory."
        ),
    ),
    open_doc: bool = typer.Option(
        False, "--open", help="Open the generated PDF after saving"
    ),
):
    """
    Combine all images in a folder into a single PDF.

    Images are sorted alphabetically and appended in that order.
    Supported formats: JPEG, PNG, BMP, GIF, TIFF, WEBP.

    Examples:
        toolbook doc pdf imgs-to-pdf ./my-images
        toolbook doc pdf imgs-to-pdf ./my-images . --open
        toolbook doc pdf imgs-to-pdf ./my-images ./output --open
    """

    def _log(msg: str) -> None:
        typer.echo(msg)

    result = IMGsToPDF(images_dir, output_path, log=_log)

    if result.startswith("Error"):
        typer.secho(f"\n❌ {result}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"\n✅ Done — PDF saved to: {result}", fg=typer.colors.GREEN)

    if open_doc:
        _open_path(result)


@pdf_app.command("pdf-to-imgs")
def pdf_pdf_to_imgs(
    pdf_file: str = typer.Argument(..., help="Path to the PDF file to convert"),
    output_path: str = typer.Argument(
        None,
        help=(
            "Base directory where the images folder will be created. "
            "Omit to use ~/Downloads, use '.' for the current directory."
        ),
    ),
    dpi: int = typer.Option(
        150, "--dpi", help="Render resolution in DPI (default 150)"
    ),
    open_doc: bool = typer.Option(
        False, "--open", help="Open the output folder after converting"
    ),
):
    """
    Render every PDF page as a JPEG image.

    Pages are saved as page_1.jpg, page_2.jpg … inside a folder named
    after the source PDF file.

    Examples:
        toolbook doc pdf pdf-to-imgs ./document.pdf
        toolbook doc pdf pdf-to-imgs ./document.pdf . --open
        toolbook doc pdf pdf-to-imgs ./document.pdf ./output --dpi 300 --open
    """

    def _log(msg: str) -> None:
        typer.echo(msg)

    result = PDFToIMGs(pdf_file, output_path, dpi=dpi, log=_log)

    if result.startswith("Error"):
        typer.secho(f"\n❌ {result}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"\n✅ Done — images saved to: {result}", fg=typer.colors.GREEN)

    if open_doc:
        _open_path(result)


# ── img commands ──────────────────────────────────────────────────────────────


@img_app.command("convert-png")
def img_convert_png(
    image_file: str = typer.Argument(..., help="Path to the source image file"),
    output_path: str = typer.Argument(
        None,
        help=(
            "Destination directory or file path for the .png output. "
            "Omit to use ~/Downloads, use '.' for the current directory."
        ),
    ),
    open_doc: bool = typer.Option(
        False, "--open", help="Open the converted image after saving"
    ),
):
    """
    Convert an image to PNG format.

    Examples:
        toolbook doc img convert-png ./photo.jpg
        toolbook doc img convert-png ./photo.jpg . --open
        toolbook doc img convert-png ./photo.jpg ./output --open
    """

    def _log(msg: str) -> None:
        typer.echo(msg)

    result = IMGConvertToPNG(image_file, output_path, log=_log)

    if result.startswith("Error"):
        typer.secho(f"\n❌ {result}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"\n✅ Done — PNG saved to: {result}", fg=typer.colors.GREEN)

    if open_doc:
        _open_path(result)


@img_app.command("convert-jpg")
@img_app.command("convert-jpeg")
def img_convert_jpg(
    image_file: str = typer.Argument(..., help="Path to the source image file"),
    output_path: str = typer.Argument(
        None,
        help=(
            "Destination directory or file path for the .jpg output. "
            "Omit to use ~/Downloads, use '.' for the current directory."
        ),
    ),
    open_doc: bool = typer.Option(
        False, "--open", help="Open the converted image after saving"
    ),
):
    """
    Convert an image to JPEG/JPG format.

    Examples:
        toolbook doc img convert-jpg ./photo.png
        toolbook doc img convert-jpg ./photo.png . --open
        toolbook doc img convert-jpeg ./photo.png ./output --open
    """

    def _log(msg: str) -> None:
        typer.echo(msg)

    result = IMGConvertToJPG(image_file, output_path, log=_log)

    if result.startswith("Error"):
        typer.secho(f"\n❌ {result}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"\n✅ Done — JPG saved to: {result}", fg=typer.colors.GREEN)

    if open_doc:
        _open_path(result)

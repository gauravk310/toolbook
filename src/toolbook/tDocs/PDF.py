import os
from pathlib import Path
from pypdf import PdfMerger as _PdfMerger, PdfReader, PdfWriter


def PDFMerger(pdfs_dir: str, output_dir: str) -> str:
    """
    Merge all PDF files found in *pdfs_dir* into a single PDF saved in *output_dir*.

    Parameters
    ----------
    pdfs_dir  : str  Path to a directory that contains the PDF files to merge.
    output_dir: str  Directory where the merged PDF will be written.

    Returns
    -------
    str  Absolute path of the merged PDF on success, or an error message string.

    Usage (code)
    ------------
    from toolbook.tDocs import PDFMerger
    PDFMerger("/path/to/pdfs", "/path/to/output")

    Usage (CLI)
    -----------
    toolbook doc pdf --merge <pdf-dir> <output-dir>
    """
    pdfs_dir = os.path.abspath(pdfs_dir)
    output_dir = os.path.abspath(output_dir)

    if not os.path.isdir(pdfs_dir):
        return f"Error: '{pdfs_dir}' is not a valid directory"

    # Collect all PDFs in the directory (sorted for deterministic order)
    pdfs: list[str] = sorted(
        str(p) for p in Path(pdfs_dir).iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf"
    )

    if len(pdfs) < 2:
        return f"Need at least 2 PDF files in '{pdfs_dir}', found {len(pdfs)}"

    merger = _PdfMerger()
    try:
        for pdf in pdfs:
            merger.append(pdf)

        os.makedirs(output_dir, exist_ok=True)

        # Output filename is derived from the first PDF's stem
        first_stem = Path(pdfs[0]).stem
        output_name = f"{first_stem}_merged.pdf"
        output_path = os.path.join(output_dir, output_name)

        merger.write(output_path)
        return output_path
    except Exception as e:
        return f"Error merging PDFs: {e}"
    finally:
        merger.close()


def PDFSplit(
    pdf_file: str,
    output_path: str | None = None,
    log=None,
) -> str:
    """
    Split a PDF file into individual pages, saving each page as a separate PDF
    inside a folder named after the source file.

    Parameters
    ----------
    pdf_file    : str           Path to the source PDF file.
    output_path : str | None    Destination base directory for the split folder.
                                - If omitted or None  → ~/Downloads/<filename>/
                                - If "."              → ./<filename>/  (current directory)
                                - Otherwise           → <given path>/<filename>/
    log         : callable | None
                                Optional function(str) called for each progress
                                message (e.g. ``print`` or ``typer.echo``).

    Returns
    -------
    str  Absolute path of the output directory on success, or an error message string.

    Usage (code)
    ------------
    from toolbook.tDocs import PDFSplit
    PDFSplit("/path/to/file.pdf", "/path/to/output", log=print)

    Usage (CLI)
    -----------
    toolbook doc pdf split <pdf-file> [output-path]
    """
    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    if not pdf_file:
        return "Error: No file selected"

    pdf_file = os.path.abspath(pdf_file)

    if not os.path.isfile(pdf_file):
        return f"Error: '{pdf_file}' is not a valid file"

    if not pdf_file.lower().endswith(".pdf"):
        return f"Error: '{pdf_file}' is not a PDF file"

    # Resolve output directory — always a sub-folder named after the PDF
    file_stem = Path(pdf_file).stem
    if output_path is None:
        base = Path.home() / "Downloads"
    elif output_path == ".":
        base = Path.cwd()
    else:
        base = Path(os.path.abspath(output_path))

    output_dir = base / file_stem

    try:
        reader = PdfReader(pdf_file)
        total = len(reader.pages)
        os.makedirs(output_dir, exist_ok=True)

        _log(f"📂 Output folder : {output_dir}")
        _log(f"📄 Source        : {pdf_file}")
        _log(f"📑 Total pages   : {total}")
        _log("")

        for i, page in enumerate(reader.pages):
            writer = PdfWriter()
            writer.add_page(page)
            page_file = output_dir / f"page_{i + 1}.pdf"
            with open(page_file, "wb") as f:
                writer.write(f)
            _log(f"  [{i + 1}/{total}] Saved → {page_file.name}")

        return str(output_dir)
    except Exception as e:
        return f"Error splitting PDF: {e}"


def PDFWatermark():
    return "Pdf watermark tool"


def PDFInfo():
    return "Pdf info tool"


def PDFRotate():
    return "Pdf rotate tool"

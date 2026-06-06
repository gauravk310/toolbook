import os
from pathlib import Path
from pypdf import PdfWriter, PdfReader
from pdf2docx import Converter as _PdfConverter
import fitz  # pymupdf


def PDFMerger(pdfs_dir: str, output_dir: str, log=None) -> str:
    """
    Merge all PDF files found in *pdfs_dir* into a single PDF saved in *output_dir*.

    Parameters
    ----------
    pdfs_dir  : str           Path to a directory that contains the PDF files to merge.
    output_dir: str           Directory where the merged PDF will be written.
    log       : callable | None
                              Optional function(str) called for each progress message.

    Returns
    -------
    str  Absolute path of the merged PDF on success, or an error message string.

    Usage (code)
    ------------
    from toolbook.tDocs import PDFMerger
    PDFMerger("/path/to/pdfs", "/path/to/output", log=print)

    Usage (CLI)
    -----------
    toolbook doc pdf merge <pdf-dir> <output-dir>
    """
    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

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

    _log(f"📂 Source folder : {pdfs_dir}")
    _log(f"📑 PDFs found    : {len(pdfs)}")
    _log("")

    writer = PdfWriter()
    try:
        total_pages = 0
        for i, pdf in enumerate(pdfs):
            reader = PdfReader(pdf)
            pages = len(reader.pages)
            for page in reader.pages:
                writer.add_page(page)
            total_pages += pages
            _log(f"  [{i + 1}/{len(pdfs)}] {Path(pdf).name}  [{pages} page{'s' if pages > 1 else ''}]")

        os.makedirs(output_dir, exist_ok=True)

        # Output filename is derived from the source folder name
        folder_name = Path(pdfs_dir).name
        output_name = f"{folder_name}_merged.pdf"
        output_path = os.path.join(output_dir, output_name)

        with open(output_path, "wb") as f:
            writer.write(f)
        _log("")
        _log(f"📄 Total pages   : {total_pages}")
        return output_path
    except Exception as e:
        return f"Error merging PDFs: {e}"


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


def PDFIMGExtractor(
    pdf_file: str,
    output_path: str | None = None,
    log=None,
) -> str:
    """
    Extract all images from a PDF file, saving each as a separate image file
    inside a folder named after the source PDF.

    Parameters
    ----------
    pdf_file    : str           Path to the source PDF file.
    output_path : str | None    Destination base directory for the images folder.
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
    from toolbook.tDocs import PDFIMGExtractor
    PDFIMGExtractor("/path/to/file.pdf", "/path/to/output", log=print)

    Usage (CLI)
    -----------
    toolbook doc pdf extract-img <pdf-file> [output-path]
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
        doc = fitz.open(pdf_file)
        total_pages = len(doc)
        os.makedirs(output_dir, exist_ok=True)

        _log(f"📂 Output folder : {output_dir}")
        _log(f"📄 Source        : {pdf_file}")
        _log(f"📑 Total pages   : {total_pages}")
        _log("")

        image_count = 0
        for page_index in range(total_pages):
            page_images = doc.get_page_images(page_index)
            _log(f"  Page {page_index + 1}/{total_pages} — {len(page_images)} image(s) found")

            for img in page_images:
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                ext = base_image["ext"]
                image_file = output_dir / f"image_p{page_index + 1}_{xref}.{ext}"
                with open(image_file, "wb") as f:
                    f.write(image_bytes)
                image_count += 1
                _log(f"    ✔ Saved → {image_file.name}")

        _log("")
        _log(f"🖼  Total images extracted: {image_count}")

        if image_count == 0:
            return f"Error: No images found in '{pdf_file}'"

        return str(output_dir)
    except Exception as e:
        return f"Error extracting images: {e}"


def PDFToDocx(
    pdf_file: str,
    output_path: str | None = None,
    log=None,
) -> str:
    """
    Convert a PDF file to DOCX format.

    Parameters
    ----------
    pdf_file    : str           Path to the source PDF file.
    output_path : str | None    Destination directory for the .docx file.
                                - If omitted or None  → ~/Downloads/
                                - If "."              → current directory
                                - Otherwise           → the given path
    log         : callable | None
                                Optional function(str) called for progress messages.

    Returns
    -------
    str  Absolute path of the generated .docx file on success, or an error message.

    Usage (code)
    ------------
    from toolbook.tDocs import PDFToDocx
    PDFToDocx("/path/to/file.pdf", "/path/to/output", log=print)

    Usage (CLI)
    -----------
    toolbook doc pdf convert-docx <pdf-file> [output-path] [--open]
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

    # Resolve output directory
    file_stem = Path(pdf_file).stem
    if output_path is None:
        out_dir = Path.home() / "Downloads"
    elif output_path == ".":
        out_dir = Path.cwd()
    else:
        out_dir = Path(os.path.abspath(output_path))

    os.makedirs(out_dir, exist_ok=True)
    docx_file = out_dir / f"{file_stem}.docx"

    try:
        _log(f"📄 Source  : {pdf_file}")
        _log(f"📂 Output  : {docx_file}")
        _log("⏳ Converting …")

        cv = _PdfConverter(pdf_file)
        cv.convert(str(docx_file), start=0, end=None)
        cv.close()

        _log("✔  Conversion complete")
        return str(docx_file)
    except Exception as e:
        return f"Error converting PDF to DOCX: {e}"


def PDFWatermark():
    return "Pdf watermark tool"


def PDFInfo():
    return "Pdf info tool"


def PDFRotate():
    return "Pdf rotate tool"

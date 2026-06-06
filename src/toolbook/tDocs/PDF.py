import os
from pathlib import Path
from pypdf import PdfWriter, PdfReader
from pdf2docx import Converter as _PdfConverter
from docx2pdf import convert as _docx_to_pdf
import fitz  # pymupdf
from PIL import Image as Image_


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
        str(p)
        for p in Path(pdfs_dir).iterdir()
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
            _log(
                f"  [{i + 1}/{len(pdfs)}] {Path(pdf).name}  [{pages} page{'s' if pages > 1 else ''}]"
            )

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
            _log(
                f"  Page {page_index + 1}/{total_pages} — {len(page_images)} image(s) found"
            )

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


def DocxToPDF(
    docx_file: str,
    output_path: str | None = None,
    log=None,
) -> str:
    """
    Convert a DOCX file to PDF format using the MS Word backend (requires Word on Windows).

    Parameters
    ----------
    docx_file   : str           Path to the source .docx file.
    output_path : str | None    Destination directory for the .pdf file.
                                - If omitted or None  → ~/Downloads/
                                - If "."              → current directory
                                - Otherwise           → the given path
    log         : callable | None
                                Optional function(str) called for progress messages.

    Returns
    -------
    str  Absolute path of the generated .pdf file on success, or an error message.

    Usage (code)
    ------------
    from toolbook.tDocs import DocxToPDF
    DocxToPDF("/path/to/file.docx", "/path/to/output", log=print)

    Usage (CLI)
    -----------
    toolbook doc pdf convert-pdf <docx-file> [output-path] [--open]
    """

    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    if not docx_file:
        return "Error: No file selected"

    docx_file = os.path.abspath(docx_file)

    if not os.path.isfile(docx_file):
        return f"Error: '{docx_file}' is not a valid file"

    if not docx_file.lower().endswith(".docx"):
        return f"Error: '{docx_file}' is not a DOCX file"

    # Resolve output directory
    file_stem = Path(docx_file).stem
    if output_path is None:
        out_dir = Path.home() / "Downloads"
    elif output_path == ".":
        out_dir = Path.cwd()
    else:
        out_dir = Path(os.path.abspath(output_path))

    os.makedirs(out_dir, exist_ok=True)
    pdf_file = out_dir / f"{file_stem}.pdf"

    try:
        _log(f"📄 Source  : {docx_file}")
        _log(f"📂 Output  : {pdf_file}")
        _log("⏳ Converting …")

        _docx_to_pdf(docx_file, str(pdf_file))

        _log("✔  Conversion complete")
        return str(pdf_file)
    except Exception as e:
        return f"Error converting DOCX to PDF: {e}"


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


def IMGsToPDF(
    images_dir: str,
    output_path: str | None = None,
    log=None,
) -> str:
    """
    Combine all images in a folder into a single PDF file.

    Images are sorted alphabetically and appended in that order.
    Supported formats: JPEG, PNG, BMP, GIF, TIFF, WEBP.

    Parameters
    ----------
    images_dir  : str           Path to a directory containing the image files.
    output_path : str | None    Destination for the generated PDF.
                                - If omitted or None  → ~/Downloads/<folder-name>.pdf
                                - If "."              → ./<folder-name>.pdf (current directory)
                                - Otherwise           → <given path>/<folder-name>.pdf
    log         : callable | None
                                Optional function(str) called for progress messages.

    Returns
    -------
    str  Absolute path of the generated .pdf file on success, or an error message.

    Usage (code)
    ------------
    from toolbook.tDocs import IMGsToPDF
    IMGsToPDF("/path/to/images", "/path/to/output", log=print)

    Usage (CLI)
    -----------
    toolbook doc pdf imgs-to-pdf <images-dir> [output-path] [--open]
    """

    _IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif", ".webp"}

    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    if not images_dir:
        return "Error: No folder selected"

    images_dir = os.path.abspath(images_dir)

    if not os.path.isdir(images_dir):
        return f"Error: '{images_dir}' is not a valid directory"

    # Collect supported images, sorted for deterministic order
    images: list[Path] = sorted(
        p
        for p in Path(images_dir).iterdir()
        if p.is_file() and p.suffix.lower() in _IMG_EXTS
    )

    if not images:
        return f"Error: No supported images found in '{images_dir}'"

    # Resolve output path
    folder_name = Path(images_dir).name
    pdf_name = f"{folder_name}.pdf"

    if output_path is None:
        out_dir = Path.home() / "Downloads"
    elif output_path == ".":
        out_dir = Path.cwd()
    else:
        out_dir = Path(os.path.abspath(output_path))

    os.makedirs(out_dir, exist_ok=True)
    out_file = out_dir / pdf_name

    try:
        _log(f"📂 Source folder : {images_dir}")
        _log(f"🖼  Images found  : {len(images)}")
        _log(f"📄 Output        : {out_file}")
        _log("")

        frames: list[Image_] = []
        for i, img_path in enumerate(images):
            img = Image_.open(img_path).convert("RGB")
            frames.append(img)
            _log(f"  [{i + 1}/{len(images)}] {img_path.name}")

        frames[0].save(
            str(out_file),
            "PDF",
            save_all=True,
            append_images=frames[1:],
        )

        _log("")
        _log("✔  PDF created")
        return str(out_file)
    except Exception as e:
        return f"Error creating PDF from images: {e}"


def PDFToIMGs(
    pdf_file: str,
    output_path: str | None = None,
    dpi: int = 150,
    log=None,
) -> str:
    """
    Render every page of a PDF as a JPEG image.

    Each page is saved as ``page_1.jpg``, ``page_2.jpg`` … inside a folder
    named after the source PDF file.

    Parameters
    ----------
    pdf_file    : str           Path to the source PDF file.
    output_path : str | None    Destination base directory for the images folder.
                                - If omitted or None  → ~/Downloads/<filename>/
                                - If "."              → ./<filename>/  (current directory)
                                - Otherwise           → <given path>/<filename>/
    dpi         : int           Render resolution (default 150).  Higher values
                                produce sharper images but larger files.
    log         : callable | None
                                Optional function(str) called for progress messages.

    Returns
    -------
    str  Absolute path of the output folder on success, or an error message.

    Usage (code)
    ------------
    from toolbook.tDocs import PDFToIMGs
    PDFToIMGs("/path/to/file.pdf", "/path/to/output", log=print)

    Usage (CLI)
    -----------
    toolbook doc pdf pdf-to-imgs <pdf-file> [output-path] [--open]
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

    # Resolve output folder — named after the PDF stem
    file_stem = Path(pdf_file).stem
    if output_path is None:
        base = Path.home() / "Downloads"
    elif output_path == ".":
        base = Path.cwd()
    else:
        base = Path(os.path.abspath(output_path))

    output_dir = base / file_stem
    os.makedirs(output_dir, exist_ok=True)

    try:
        doc = fitz.open(pdf_file)
        total = len(doc)
        # zoom factor: 72 dpi is fitz default, so zoom = dpi / 72
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)

        _log(f"📄 Source        : {pdf_file}")
        _log(f"📂 Output folder : {output_dir}")
        _log(f"📑 Total pages   : {total}")
        _log(f"🖼  Resolution    : {dpi} dpi")
        _log("")

        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat)
            img_file = output_dir / f"page_{i + 1}.jpg"
            pix.save(str(img_file))
            _log(f"  [{i + 1}/{total}] Saved → {img_file.name}")

        doc.close()
        _log("")
        _log(f"✔  {total} image{'s' if total != 1 else ''} saved")
        return str(output_dir)
    except Exception as e:
        return f"Error converting PDF to images: {e}"


def PDFInfo():
    return "Pdf info tool"


def PDFRotate():
    return "Pdf rotate tool"

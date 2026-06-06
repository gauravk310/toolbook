import os
from pathlib import Path
from PIL import Image


# ── helpers ───────────────────────────────────────────────────────────────────


def _resolve_output_path(
    image_file: str,
    output_path: str | None,
    ext: str,
) -> str:
    """
    Build the full output file path.

    Rules (matching the project convention):
    - output_path is None  → ~/Downloads/<stem>.<ext>
    - output_path is "."   → <cwd>/<stem>.<ext>
    - output_path is a dir → <that dir>/<stem>.<ext>
    - output_path ends with .<ext> → used as-is (explicit file path)
    """
    stem = Path(image_file).stem
    filename = f"{stem}.{ext}"

    if output_path is None:
        out_dir = Path.home() / "Downloads"
    elif output_path == ".":
        out_dir = Path.cwd()
    else:
        candidate = Path(os.path.abspath(output_path))
        # If the caller passed a full file path (has a suffix), use it directly
        if candidate.suffix:
            os.makedirs(candidate.parent, exist_ok=True)
            return str(candidate)
        out_dir = candidate

    os.makedirs(out_dir, exist_ok=True)
    return str(out_dir / filename)


# ── public functions ──────────────────────────────────────────────────────────


def IMGConvertToPNG(
    image_file: str,
    output_path: str | None = None,
    log=None,
) -> str:
    """
    Convert an image file to PNG format.

    Parameters
    ----------
    image_file  : str           Path to the source image file.
    output_path : str | None    Destination for the converted file.
                                - If omitted or None  → ~/Downloads/<stem>.png
                                - If "."              → current directory
                                - Otherwise           → the given path (dir or file)
    log         : callable | None
                                Optional function(str) called for progress messages.

    Returns
    -------
    str  Absolute path of the generated .png file on success, or an error message.

    Usage (code)
    ------------
    from toolbook.tDocs import IMGConvertToPNG
    IMGConvertToPNG("/path/to/image.jpg", "/path/to/output", log=print)

    Usage (CLI)
    -----------
    toolbook doc img convert-png <image-file> [output-path] [--open]
    """

    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    if not image_file:
        return "Error: No file selected"

    image_file = os.path.abspath(image_file)

    if not os.path.isfile(image_file):
        return f"Error: '{image_file}' is not a valid file"

    out_file = _resolve_output_path(image_file, output_path, "png")

    try:
        _log(f"📄 Source  : {image_file}")
        _log(f"📂 Output  : {out_file}")
        _log("⏳ Converting …")

        with Image.open(image_file) as img:
            img.save(out_file, "PNG")

        _log("✔  Conversion complete")
        return out_file
    except Exception as e:
        return f"Error converting image to PNG: {e}"


def IMGConvertToJPG(
    image_file: str,
    output_path: str | None = None,
    log=None,
) -> str:
    """
    Convert an image file to JPEG/JPG format.

    Parameters
    ----------
    image_file  : str           Path to the source image file.
    output_path : str | None    Destination for the converted file.
                                - If omitted or None  → ~/Downloads/<stem>.jpg
                                - If "."              → current directory
                                - Otherwise           → the given path (dir or file)
    log         : callable | None
                                Optional function(str) called for progress messages.

    Returns
    -------
    str  Absolute path of the generated .jpg file on success, or an error message.

    Usage (code)
    ------------
    from toolbook.tDocs import IMGConvertToJPG
    IMGConvertToJPG("/path/to/image.png", "/path/to/output", log=print)

    Usage (CLI)
    -----------
    toolbook doc img convert-jpg <image-file> [output-path] [--open]
    toolbook doc img convert-jpeg <image-file> [output-path] [--open]
    """

    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    if not image_file:
        return "Error: No file selected"

    image_file = os.path.abspath(image_file)

    if not os.path.isfile(image_file):
        return f"Error: '{image_file}' is not a valid file"

    out_file = _resolve_output_path(image_file, output_path, "jpg")

    try:
        _log(f"📄 Source  : {image_file}")
        _log(f"📂 Output  : {out_file}")
        _log("⏳ Converting …")

        with Image.open(image_file) as img:
            img.convert("RGB").save(out_file, "JPEG")

        _log("✔  Conversion complete")
        return out_file
    except Exception as e:
        return f"Error converting image to JPG: {e}"

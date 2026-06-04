import os
import logging
from pathlib import Path

try:
    import yt_dlp
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "yt-dlp is required for video downloads. Install it with: pip install yt-dlp"
    ) from exc

logger = logging.getLogger(__name__)


def YT(url: str, path: str | None = None) -> str:
    """Download a YouTube video to *path*.

    Parameters
    ----------
    url:
        A valid YouTube video URL.  Use ``play_yt_video`` to resolve a search
        query to a canonical URL before calling this function.
    path:
        Destination directory.  When *None* the video is saved to the current
        user's ``Downloads`` folder.

    Returns
    -------
    str
        A human-readable success message containing the destination path, or an
        error description when the download fails.
    """
    write_path = path if path else str(Path.home() / "Downloads")

    # Make sure the destination directory exists
    os.makedirs(write_path, exist_ok=True)

    logger.info("Downloading YouTube video from: %s", url)

    ydl_opts = {
        "outtmpl": os.path.join(write_path, "%(title)s.%(ext)s"),
        "format": "best",
        "cookiesfrombrowser": ("chrome",),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        logger.info("Video downloaded successfully to %s", write_path)
        return f"Video Downloaded Successfully to {write_path}"
    except Exception as exc:
        logger.error("Error downloading YouTube video: %s", str(exc))
        return str(exc)

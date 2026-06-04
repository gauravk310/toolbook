from pathlib import Path

import typer

from toolbook.tMedia import VideoDL

app = typer.Typer()


@app.command("yt-vdo")
def yt_video(
    url: str = typer.Argument(..., help="YouTube video URL to download"),
    path: str = typer.Argument(
        None,
        help="Destination folder (defaults to ~/Downloads, use '.' for the current directory)",
    ),
):
    """
    Download a YouTube video from URL.

    Examples
    --------
      toolbook media yt-vdo https://youtu.be/dQw4w9WgXcQ
      toolbook media yt-vdo https://youtu.be/dQw4w9WgXcQ ./videos
      toolbook media yt-vdo https://youtu.be/dQw4w9WgXcQ .
    """
    # Resolve '.' to the real current-working-directory path
    if path == ".":
        destination = str(Path.cwd())
    elif path:
        destination = str(Path(path).resolve())
    else:
        destination = str(Path.home() / "Downloads")

    typer.secho(f"\n⬇️  Downloading video to: {destination}", fg=typer.colors.CYAN, bold=True)

    result = VideoDL.YT(url, destination)

    if result.startswith("Video Downloaded"):
        typer.secho(f"✅ {result}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"❌ Download failed: {result}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

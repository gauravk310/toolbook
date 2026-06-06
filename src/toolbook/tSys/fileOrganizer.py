import os
import shutil

FILE_TYPES = {
    "Images": [".jpg", ".jpeg", ".png", ".gif"],
    "Videos": [".mp4", ".mkv", ".avi"],
    "Documents": [".docx", ".txt", ".pptx"],
    "PDFs": [".pdf"],
    "Music": [".mp3", ".wav"],
    "Archives": [".zip", ".rar"],
}


def _safe_move(src: str, target_folder: str, filename: str) -> str:
    """Move *src* into *target_folder*, renaming to avoid collisions.

    Returns the final destination path.
    """
    target_path = os.path.join(target_folder, filename)
    if os.path.exists(target_path):
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(target_path):
            target_path = os.path.join(target_folder, f"{base}_{counter}{ext}")
            counter += 1
    shutil.move(src, target_path)
    return target_path


class FileOrganizer:
    """Organizes files in *folder_path* into typed sub-folders.

    Usage::

        from toolbook.tSys import FileOrganizer
        FileOrganizer("/path/to/folder")
    """

    def __init__(self, folder_path: str) -> None:
        self.folder_path = os.path.abspath(folder_path)
        self._organize()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_folders(self) -> None:
        """Create category sub-folders if they don't already exist."""
        for folder in list(FILE_TYPES.keys()) + ["Others"]:
            os.makedirs(os.path.join(self.folder_path, folder), exist_ok=True)

    def _organize(self) -> None:
        """Main organisation logic."""
        if not os.path.exists(self.folder_path):
            print("❌ Error: Folder path does not exist!")
            return

        self._ensure_folders()
        print("\n🚀 Organising files…\n")

        for filename in os.listdir(self.folder_path):
            file_path = os.path.join(self.folder_path, filename)

            # Skip sub-directories (including the ones we just created)
            if not os.path.isfile(file_path):
                continue

            try:
                moved = False
                for category, extensions in FILE_TYPES.items():
                    if filename.lower().endswith(tuple(extensions)):
                        target_folder = os.path.join(self.folder_path, category)
                        _safe_move(file_path, target_folder, filename)
                        print(f"  ✅ {filename} → 📂 {category}/")
                        moved = True
                        break

                if not moved:
                    target_folder = os.path.join(self.folder_path, "Others")
                    _safe_move(file_path, target_folder, filename)
                    print(f"  📦 {filename} → 📂 Others/")

            except Exception as exc:
                print(f"  ❌ Failed to move {filename}: {exc}")

        print("\n🎉 File organisation completed!")

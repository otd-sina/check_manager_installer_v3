import sys
from pathlib import Path


def resource_path(relative_path: str) -> Path:
    """
    Get absolute path to resource for dev and PyInstaller
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path

    return Path(".") / relative_path
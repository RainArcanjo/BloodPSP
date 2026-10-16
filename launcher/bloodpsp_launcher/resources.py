from pathlib import Path
import sys

from .config import ConfigDocument


def resource(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "resources" / name


def default_document(scheme: str = "current") -> ConfigDocument:
    return ConfigDocument.load(resource("default-legacy.cfg" if scheme == "legacy" else "default.cfg"))

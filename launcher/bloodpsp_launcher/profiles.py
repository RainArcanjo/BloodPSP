"""Local user presets contain mappings and axes, not video or game settings."""
from pathlib import Path
import json

from .config import ConfigDocument, ConfigError, atomic_write, backup_file
from .mappings import Mapping, chord, read_mappings, write_mappings, validate_mappings, game_actions
from .controls import actions

AXIS_KEYS = tuple(f"JoystickAnalog{kind}{axis}" for axis in range(2) for kind in ("Axes", "Scale"))


class ProfileStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("version") != 1 or not isinstance(data.get("profiles"), dict):
                raise ValueError()
            return data["profiles"]
        except (ValueError, OSError, AttributeError) as ex:
            raise ConfigError("Could not read saved control presets.") from ex

    def _write(self, profiles):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            backup_file(self.path)
        atomic_write(self.path, json.dumps({"version": 1, "profiles": profiles}, indent=2, ensure_ascii=False).encode("utf-8"))

    def save(self, name: str, doc: ConfigDocument, scheme: str):
        name = name.strip()
        if not name or len(name) > 64:
            raise ConfigError("Enter a preset name of 1 to 64 characters.")
        profiles = self.load()
        existing = next((n for n in profiles if n.casefold() == name.casefold()), None)
        if existing and existing != name:
            del profiles[existing]
        mappings = read_mappings(doc, scheme)
        validate_mappings(mappings, game_actions())
        profiles[name] = {"scheme": scheme, "mappings": [{"buttons": list(m.buttons), "action": m.action} for m in mappings],
                          "axes": {key: doc.get("Controls", key) for key in AXIS_KEYS}}
        self._write(profiles)
        return name

    def remove(self, name):
        profiles = self.load()
        profiles.pop(name, None)
        self._write(profiles)

    def apply(self, name, doc):
        data = self.load()[name]
        try:
            mappings = [Mapping(chord(m["buttons"]), m["action"]) for m in data["mappings"]]
            validate_mappings(mappings, game_actions())
            updated = doc.clone()
            write_mappings(updated, mappings)
            for key, value in data["axes"].items():
                if key in AXIS_KEYS:
                    updated.set("Controls", key, value)
        except (ValueError, TypeError, KeyError) as ex:
            raise ConfigError("This control preset is invalid.") from ex
        doc.lines = updated.lines
        doc._index()
        return data.get("scheme", "current")

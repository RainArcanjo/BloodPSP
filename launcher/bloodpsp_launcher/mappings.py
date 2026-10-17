"""Native PSP mappings, independent of the desktop editor and input devices."""
from dataclasses import dataclass
import re
from functools import lru_cache

from .config import ConfigDocument, ConfigError, quote, tokens
from .controls import SCHEMES, actions, read_bindings

BUTTONS = ("cross", "circle", "square", "triangle", "l", "r", "up", "down", "left", "right", "select")
BUTTON_NAMES = {"cross": "Cross", "circle": "Circle", "square": "Square", "triangle": "Triangle",
                "l": "L", "r": "R", "up": "Up", "down": "Down", "left": "Left", "right": "Right", "select": "Select"}
SECTION = "PSP Controls"
MAX_MAPPINGS = 64


@lru_cache(maxsize=1)
def game_actions():
    from .resources import default_document
    return tuple(a for a in actions(default_document()) if a != "Show_Console")


def chord(buttons) -> tuple[str, ...]:
    values = tuple(buttons)
    if not values or len(set(values)) != len(values) or any(b not in BUTTONS for b in values):
        raise ConfigError("Choose PSP buttons; Start and HOME are reserved for the system.")
    return tuple(b for b in BUTTONS if b in values)


def chord_text(buttons) -> str:
    return " + ".join(BUTTON_NAMES[b] for b in buttons)


@dataclass(frozen=True)
class Mapping:
    buttons: tuple[str, ...]
    action: str


def validate_mappings(mappings, available_actions):
    if len(mappings) > MAX_MAPPINGS:
        raise ConfigError(f"A preset supports up to {MAX_MAPPINGS} mappings.")
    seen = set()
    for mapping in mappings:
        normalized = chord(mapping.buttons)
        if normalized in seen:
            raise ConfigError(f"{chord_text(normalized)} already has a mapping. Edit or delete that row first.")
        if mapping.action not in available_actions or mapping.action == "Show_Console":
            raise ConfigError("Choose a supported game action.")
        seen.add(normalized)


def has_native_mappings(doc: ConfigDocument) -> bool:
    return doc.number(SECTION, "Version") == 1


def read_mappings(doc: ConfigDocument, scheme="current") -> list[Mapping]:
    if has_native_mappings(doc):
        count = doc.number(SECTION, "Count", -1)
        if not 0 <= count <= MAX_MAPPINGS:
            raise ConfigError("Invalid PSP mapping count in this CFG.")
        result = []
        for i in range(count):
            entry = tokens(doc.get(SECTION, f"Mapping{i}"))
            if len(entry) != 2:
                raise ConfigError(f"Invalid PSP mapping {i}.")
            result.append(Mapping(chord(entry[0].lower().split("+")), entry[1]))
        validate_mappings(result, game_actions())
        return result
    result = []
    bindings = read_bindings(doc, scheme)
    for button in SCHEMES[scheme]:
        buttons = (("l", "r", "cross") if scheme == "current" else ("l", "triangle")) if button.name == "secondary" else ("l", "square") if button.name == "run" else (button.name,)
        for action in bindings[button.name]:
            if action != "Show_Console":
                result.append(Mapping(chord(buttons), action))
    return result


def write_mappings(doc: ConfigDocument, mappings: list[Mapping]) -> None:
    validate_mappings(mappings, game_actions())
    for entry in list(doc.entries.values()):
        if entry.section.casefold() == SECTION.casefold() and re.fullmatch(r"Mapping\d+", entry.key, re.IGNORECASE):
            doc.remove(entry.section, entry.key)
    doc.set(SECTION, "Version", 1)
    doc.set(SECTION, "Count", len(mappings))
    for i, mapping in enumerate(mappings):
        doc.set(SECTION, f"Mapping{i}", quote("+".join(chord(mapping.buttons))) + " " + quote(mapping.action))


class ChordCapture:
    """Confirm the largest simultaneous chord 200ms after every button is up."""
    def __init__(self, settle_ms=200):
        self.settle_ms = settle_ms
        self.reset()

    def reset(self):
        self.held = frozenset()
        self.candidate = frozenset()
        self.released_at = None
        self.ready = False

    def update(self, pressed, now_ms):
        pressed = frozenset(pressed)
        if not pressed.issubset(BUTTONS):
            self.reset()
            return None
        # Ignore buttons already held when capture opens; first require neutral.
        if not self.ready:
            self.ready = not pressed
            return None
        if pressed:
            if not self.held:
                self.candidate = pressed
            elif len(pressed) >= len(self.candidate):
                self.candidate = pressed
            self.released_at = None
        elif self.held:
            self.released_at = now_ms
        self.held = pressed
        if self.candidate and self.released_at is not None and now_ms - self.released_at >= self.settle_ms:
            result = chord(self.candidate)
            self.reset()
            return result
        return None

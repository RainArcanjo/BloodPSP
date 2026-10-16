"""Map physical PSP inputs to the keyboard events emitted by the PSP port."""
from __future__ import annotations

from dataclasses import dataclass
from .config import ConfigDocument, ConfigError, tokens, quote


@dataclass(frozen=True)
class Button:
    name: str
    label: str
    keys: tuple[str, ...]
    action: str


CURRENT = (
    Button("cross", "Cross", ("RCtrl",), "Weapon_Fire"),
    Button("square", "Square", ("E",), "Open"),
    Button("triangle", "Triangle", ("Space",), "Jump"),
    Button("circle", "Circle", ("LCtrl",), "Crouch"),
    Button("l", "L", ("A",), "Strafe_Left"),
    Button("r", "R", ("D",), "Strafe_Right"),
    Button("up", "D-pad up", ("]",), "Inventory_Right"),
    Button("down", "D-pad down", ("Enter",), "Inventory_Use"),
    Button("left", "D-pad left", (";",), "Previous_Weapon"),
    Button("right", "D-pad right", ("'",), "Next_Weapon"),
    Button("select", "SELECT", ("Tab",), "Map_Toggle"),
    Button("secondary", "L + R + Cross", ("X",), "Weapon_Special_Fire"),
)
LEGACY = (
    Button("cross", "Cross", ("Space",), "Jump"),
    Button("square", "Square", ("E",), "Open"),
    Button("triangle", "Triangle", ("'",), "Next_Weapon"),
    Button("circle", "Circle", ("LCtrl",), "Crouch"),
    Button("l", "L", ("X",), "Weapon_Special_Fire"),
    Button("r", "R", ("RCtrl",), "Weapon_Fire"),
    Button("up", "D-pad up", ("W", "Up"), "Move_Forward"),
    Button("down", "D-pad down", ("S", "Down"), "Move_Backward"),
    Button("left", "D-pad left", ("Left",), "Turn_Left"),
    Button("right", "D-pad right", ("Right",), "Turn_Right"),
    Button("select", "SELECT", ("Tab",), "Map_Toggle"),
    Button("secondary", "L + Triangle", (";",), "Previous_Weapon"),
    Button("run", "L + Square", ("CapLck",), "AutoRun"),
)
SCHEMES = {"current": CURRENT, "legacy": LEGACY}
SCHEME_LABELS = {"current": "Standard 1", "legacy": "Standard 2"}

ACTION_LABELS = {
    "Move_Forward": "Move forward", "Move_Backward": "Move backward",
    "Turn_Left": "Turn left", "Turn_Right": "Turn right", "Turn_Around": "Turn around",
    "Strafe": "Strafe modifier", "Strafe_Left": "Strafe left", "Strafe_Right": "Strafe right",
    "Jump": "Jump", "Crouch": "Crouch", "Run": "Run", "AutoRun": "Toggle auto run",
    "Open": "Use / open", "Weapon_Fire": "Primary fire", "Weapon_Special_Fire": "Secondary fire",
    "Aim_Up": "Aim up", "Aim_Down": "Aim down", "Aim_Center": "Center aim",
    "Look_Up": "Look up", "Look_Down": "Look down", "Inventory_Use": "Use item",
    "Inventory_Left": "Previous item", "Inventory_Right": "Next item",
    "Map_Toggle": "Toggle map", "Map_Follow_Mode": "Map follow mode",
    "Next_Weapon": "Next weapon", "Previous_Weapon": "Previous weapon",
    "Holster_Weapon": "Holster weapon", "Toggle_Crosshair": "Toggle crosshair",
    "Shrink_Screen": "Shrink view", "Enlarge_Screen": "Enlarge view",
    "See_Chase_View": "Third-person view", "BeastVision": "Beast vision",
    "CrystalBall": "Crystal ball", "JumpBoots": "Jump boots", "MedKit": "Medkit",
    "ProximityBombs": "Proximity bombs", "RemoteBombs": "Remote bombs",
}


def actions(doc: ConfigDocument) -> list[str]:
    return [e.key for e in doc.entries.values() if e.section.casefold() == "keydefinitions"]


def read_bindings(doc: ConfigDocument, scheme: str) -> dict[str, tuple[str, ...]]:
    result = {}
    for button in SCHEMES[scheme]:
        emitted = {k.casefold() for k in button.keys}
        result[button.name] = tuple(action for action in actions(doc)
                                    if emitted.intersection(k.casefold() for k in tokens(doc.get("KeyDefinitions", action))))
    return result


def bind_button(doc: ConfigDocument, scheme: str, name: str, action: str) -> None:
    updated = doc.clone()
    _bind_button(updated, scheme, name, action)
    doc.lines = updated.lines
    doc._index()


def _bind_button(doc: ConfigDocument, scheme: str, name: str, action: str) -> None:
    button = next(b for b in SCHEMES[scheme] if b.name == name)
    if action and action not in actions(doc):
        raise ConfigError("Unknown control action.")
    # Remove every alias actually emitted by this physical button. Otherwise
    # legacy Up/W pairs can trigger the former action as well as the new one.
    emitted = {k.casefold() for k in button.keys}
    for entry in actions(doc):
        before = tokens(doc.get("KeyDefinitions", entry))[:2]
        after = [key if key.casefold() not in emitted else "" for key in before]
        if before != after:
            doc.set("KeyDefinitions", entry, " ".join(quote(k) for k in (after + ["", ""])[:2]))
    if not action:
        return
    keys = (tokens(doc.get("KeyDefinitions", action)) + ["", ""])[:2]
    if all(keys):
        physical_keys = {key.casefold() for control in SCHEMES[scheme] for key in control.keys}
        replaceable = next((i for i, key in enumerate(keys) if key.casefold() not in physical_keys), None)
        if replaceable is None:
            raise ConfigError(f"{ACTION_LABELS.get(action, action)} is already assigned to two buttons. Unassign one before adding another.")
        # This editor configures the PSP. Prefer physical PSP controls over a
        # desktop-only shortcut while keeping the other physical assignment.
        keys[replaceable] = ""
    keys[keys.index("")] = button.keys[0]
    doc.set("KeyDefinitions", action, " ".join(quote(k) for k in keys))


def reset_bindings(doc: ConfigDocument, template: ConfigDocument) -> None:
    for entry in template.entries.values():
        if entry.section.casefold() == "keydefinitions" or (entry.section.casefold() == "controls" and entry.key.startswith("JoystickAnalog")):
            doc.set(entry.section, entry.key, entry.value)

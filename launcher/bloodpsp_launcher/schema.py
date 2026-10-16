"""Curated PSP controls; all other CFG entries remain editable in the table."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    section: str
    key: str
    label: str
    kind: str = "bool"
    minimum: int = 0
    maximum: int = 1
    tip: str = ""


VIDEO = [
    Field("Screen Setup", "Gamma", "Brightness / gamma", "int", 0, 15),
    Field("Screen Setup", "Size", "View size", "int", 0, 6, "Original Size setting. The effect depends on the game HUD."),
    Field("Options", "Detail", "Detail", "int", 0, 4),
    Field("Options", "Interpolation", "Interpolation"),
    Field("Options", "ViewHBobbing", "Horizontal view bobbing"),
    Field("Options", "ViewVBobbing", "Vertical view bobbing"),
    Field("Options", "AimReticle", "Crosshair"),
    Field("Options", "SlopeTilting", "Slope tilting"),
    Field("Options", "ShowWeapon", "Show weapon"),
]
AUDIO = [
    Field("Sound Setup", "SoundToggle", "Sound effects"),
    Field("Sound Setup", "MusicToggle", "Music"),
    Field("Sound Setup", "CDAudioToggle", "Use OGG music", tip="Requires an OGG-compatible EBOOT. Tracks: music/blood02.ogg to blood09.ogg."),
    Field("Sound Setup", "FXVolume", "Effects volume", "slider", 0, 255),
    Field("Sound Setup", "MusicVolume", "Music volume", "slider", 0, 255),
    Field("Sound Setup", "NumVoices", "Sound channels", "int", 1, 32),
    Field("Sound Setup", "ReverseStereo", "Reverse stereo"),
]
GAME = [
    Field("Options", "AutoRun", "Auto run"),
    Field("Options", "FollowMap", "Follow map"),
    Field("Options", "OverlayMap", "Overlay map"),
    Field("Options", "RotateMap", "Rotate map"),
    Field("Options", "MessageState", "Show messages"),
    Field("Options", "MessageCount", "Message count", "int", 1, 16),
    Field("Options", "MessageTime", "Message duration (s)", "int", 1, 60),
    Field("Game Options", "WeaponsV10x", "Classic weapon behavior"),
]
ALL_FIELDS = VIDEO + AUDIO + GAME
BOOLEAN_FIELDS = {(f.section, f.key) for f in ALL_FIELDS if f.kind == "bool"}
BOOLEAN_FIELDS |= {("Controls", "UseJoystick"), ("Controls", "UseMouse"), ("Setup", "NoAutoLoad"), ("Setup", "ForceSetup")}
DESCRIPTIONS = {(f.section, f.key): f.label for f in ALL_FIELDS}

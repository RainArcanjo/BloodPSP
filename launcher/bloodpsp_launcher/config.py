"""Lossless NBlood INI editing, including its two-string key definitions.

ConfigParser is deliberately unsuitable: it rewrites comments and treats the
semicolon key binding as a comment. Keep the original lines and change values
in place instead. Unchanged files retain their exact encoding and newlines.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import codecs
import hashlib
import os
import re
import shutil
import tempfile
from datetime import datetime


class ConfigError(ValueError):
    pass


def fingerprint(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def backup_file(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = path.parent / ".bloodpsp-backups" / stamp / path.name
    if not backup.resolve().is_relative_to(path.parent.resolve()):
        raise ConfigError("The backup folder points outside the CFG folder.")
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    return backup


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".bloodpsp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def tokens(value: str) -> list[str]:
    """Parse JFMact's quoted strings, escapes and unquoted numeric values."""
    result: list[str] = []
    pos = 0
    while pos < len(value):
        if value[pos].isspace():
            pos += 1
            continue
        if value[pos] == ";":
            break
        if value[pos] != '"':
            match = re.match(r"[^\s;]+", value[pos:])
            if not match:
                break
            result.append(match[0])
            pos += len(match[0])
            continue
        pos += 1
        text = ""
        while pos < len(value) and value[pos] != '"':
            char = value[pos]
            pos += 1
            if char == "\\":
                if pos == len(value):
                    raise ConfigError("Incomplete escape sequence in configuration value.")
                char = {"n": "\n", "r": "\r", "t": "\t"}.get(value[pos], value[pos])
                pos += 1
            text += char
        if pos == len(value):
            raise ConfigError("Unclosed quotation marks in configuration.")
        result.append(text)
        pos += 1
    return result


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + '"'


def split_comment(value: str) -> tuple[str, str]:
    quoted, escaped = False, False
    for i, char in enumerate(value):
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == ";" and not quoted:
            end = i
            while end and value[end - 1].isspace():
                end -= 1
            return value[:end], value[end:]
    return value.rstrip(), value[len(value.rstrip()):]


@dataclass(frozen=True)
class Entry:
    section: str
    key: str
    value: str
    line: int


class ConfigDocument:
    def __init__(self, data: bytes):
        self.bom = data.startswith(codecs.BOM_UTF8)
        if self.bom:
            data = data[len(codecs.BOM_UTF8):]
        try:
            text = data.decode("utf-8")
            self.encoding = "utf-8"
        except UnicodeDecodeError:
            text = data.decode("cp1252")
            self.encoding = "cp1252"
        self.newline = "\r\n" if "\r\n" in text else "\n"
        self.lines = text.splitlines(keepends=True)
        self._index()

    @classmethod
    def load(cls, path: Path) -> ConfigDocument:
        return cls(path.read_bytes())

    def clone(self) -> ConfigDocument:
        return ConfigDocument(self.to_bytes())

    def _index(self) -> None:
        self.entries: dict[tuple[str, str], Entry] = {}
        self.sections: dict[str, tuple[str, int]] = {}
        section = ""
        for i, line in enumerate(self.lines):
            text = line.strip()
            if not text or text.startswith(";"):
                continue
            if text.startswith("["):
                match = re.fullmatch(r"\[([^\]\r\n]+)\]\s*(?:;.*)?", text)
                if not match:
                    raise ConfigError(f"Invalid section on line {i + 1}.")
                section = match[1]
                if section.casefold() in self.sections:
                    raise ConfigError(f"Duplicate section on line {i + 1}: {section}")
                self.sections[section.casefold()] = (section, i)
                continue
            match = re.match(r"\s*([A-Za-z][^=\r\n]*?)\s*=\s*(.*?)(?:\r?\n)?$", line)
            if not match or not section:
                raise ConfigError(f"Invalid entry on line {i + 1}.")
            key, raw = match[1].strip(), match[2]
            raw, _ = split_comment(raw)
            tokens(raw)
            ident = (section.casefold(), key.casefold())
            if ident in self.entries:
                raise ConfigError(f"Duplicate key on line {i + 1}: {key}")
            self.entries[ident] = Entry(section, key, raw, i)

    def get(self, section: str, key: str, default: str = "") -> str:
        entry = self.entries.get((section.casefold(), key.casefold()))
        return entry.value if entry else default

    def number(self, section: str, key: str, default: int = 0) -> int:
        try:
            return int(tokens(self.get(section, key))[0], 0)
        except (ValueError, IndexError):
            return default

    def set(self, section: str, key: str, value: str | int) -> None:
        raw = str(value)
        if "\n" in raw or "\r" in raw or "\x00" in raw:
            raise ConfigError("The value must fit on a single line.")
        tokens(raw)
        if not section.strip() or any(char in section for char in "[]\r\n"):
            raise ConfigError("Invalid section name.")
        if not re.fullmatch(r"[A-Za-z][^=;\r\n]*", key):
            raise ConfigError("Invalid key name.")
        ident = (section.casefold(), key.casefold())
        entry = self.entries.get(ident)
        if entry:
            original = self.lines[entry.line]
            match = re.match(r"(\s*[^=]+?\s*=\s*)(.*?)(\r?\n)?$", original)
            assert match
            _, comment = split_comment(match[2])
            self.lines[entry.line] = match[1] + raw + comment + (match[3] or "")
        else:
            if self.lines and not self.lines[-1].endswith(("\n", "\r")):
                self.lines[-1] += self.newline
            sec = self.sections.get(section.casefold())
            if sec:
                following = [line for _, line in self.sections.values() if line > sec[1]]
                insert = min(following, default=len(self.lines))
                self.lines.insert(insert, f"{key} = {raw}{self.newline}")
            else:
                self.lines += [self.newline, f"[{section}]{self.newline}", f"{key} = {raw}{self.newline}"]
        self._index()

    def to_bytes(self) -> bytes:
        try:
            payload = "".join(self.lines).encode(self.encoding)
        except UnicodeEncodeError as ex:
            raise ConfigError("This CFG uses Windows-1252. Use characters supported by that encoding.") from ex
        return (codecs.BOM_UTF8 if self.bom else b"") + payload

    def save(self, path: Path, expected_hash: str | None) -> Path | None:
        if fingerprint(path) != expected_hash:
            raise ConfigError("The file changed outside the launcher. Reopen the CFG before saving to preserve those changes.")
        previous = backup_file(path) if path.exists() else None
        atomic_write(path, self.to_bytes())
        return previous

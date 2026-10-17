# Third-party notices

The launcher's original source is MIT licensed. Existing BloodPSP game code is
not included in the launcher executable. The separate EBOOT retains the game's
license and credits, supplied as `BloodPSP-LICENSE.txt` and `BloodPSP-CREDITS.md`
in this folder. Corresponding source and build instructions are available at
https://github.com/RainArcanjo/BloodPSP and in the release source archive.
Default configuration files come from BloodPSP and retain the project's terms.

## Qt / PySide6 / Shiboken

This package uses dynamically linked Qt 6.12.0 libraries and PySide6/Shiboken
6.12.0 from Qt for Python. These projects are copyright The Qt Company Ltd.
and their contributors. Open-source distributions provide LGPL v3 and
alternative GPL licensing. Their license texts are supplied in
`_internal/resources/licenses/` in the executable distribution (or
`resources/licenses/` in this source tree).

You may replace the supplied Qt/PySide DLLs with compatible modified versions;
the package uses the folder form of PyInstaller and keeps those libraries
separate. Reverse engineering for debugging modifications to LGPL components
is permitted under their applicable terms.

- Qt sources and corresponding version: <https://code.qt.io/cgit/qt/qtbase.git/tree/?h=v6.12.0>
- PySide/Shiboken sources: <https://code.qt.io/cgit/pyside/pyside-setup.git/tree/?h=v6.12.0>
- Qt for Python: <https://doc.qt.io/qtforpython-6/>
- Licensing information: <https://doc.qt.io/qt-6/licensing.html>

## Python

The frozen application includes the CPython runtime and standard library,
distributed under the Python Software Foundation license and component terms.
The build includes the installed Python's `LICENSE.txt` in the license folder.
Sources and notices: <https://www.python.org/downloads/source/>.

## pygame-ce / SDL

Controller capture uses pygame-ce 2.5.8 (LGPL 2.1) with SDL 2.32.10 and its
controller mappings. pygame-ce and SDL remain separate, replaceable libraries
inside the portable package. Their license notices, including notices for
libraries included in the pygame wheel, are supplied under
`_internal/resources/licenses/pygame-ce/`.

- pygame-ce source: <https://github.com/pygame-community/pygame-ce/tree/2.5.8>
- SDL source: <https://github.com/libsdl-org/SDL/tree/release-2.32.10>
- Controller API: <https://pyga.me/docs/ref/sdl2_controller.html>

## PyInstaller

Built using PyInstaller 6.22.3, copyright its contributors. Its GPL license
includes a bootloader exception permitting distribution of frozen applications
under their own licenses. <https://pyinstaller.org/en/stable/license.html>

## Interface references

The compact desktop interface is inspired by Sandstone PS2RC:
<https://github.com/SandstoneDev/PS2RC/>. The initial layout also referenced
DuckStation: <https://github.com/stenzek/duckstation>.
No source code, artwork, icons or binaries from either project are embedded.

## Artwork and PSP button icons

`resources/assets/blood-icon.png`, `bloodpsp-header.png` and `psp.png` are
project artwork supplied by Rain as `blood logo.png`, `BloodPSPBigger.png` and
`psppng.png`. The PNGs are included unchanged. The Blood handprint is also
encoded at multiple sizes in the Windows icon. These assets retain their
respective rights; the launcher's MIT license applies to its original code.
Blood and PlayStation/PSP names and artwork belong to their respective owners.

The PSP button icons are by **VictorPines**, from Wikimedia Commons, licensed
under **Creative Commons Attribution-ShareAlike 4.0 International**:
<https://creativecommons.org/licenses/by-sa/4.0/>.
Artist: <https://commons.wikimedia.org/wiki/User:VictorPines>.
Collection: <https://commons.wikimedia.org/wiki/Category:PlayStation_controller_buttons>.

The assets include D-pad directions, L, R, Select, Start, Analog Stick, Cross,
Square, Triangle and Circle. The SVG artwork is unmodified. Face buttons and
Analog Stick use Wikimedia's 250px PNG rendering of the original SVG; only
format and display size differ. Per-file source links, license and hashes are
included in `resources/assets/buttons/SOURCES.json` (under `_internal/` in
the portable package). This attribution accompanies redistributed icons.
The CC BY-SA terms apply to these icons independently of the launcher code.

## BloodPSP contributors

Rain and the BloodPSP contributors maintain the PSP port. wa59 contributed
strafing, MIDI synthesis, save-loading fixes and native-resolution work; the
launcher edits the resulting configuration. See the main project's
`CREDITS.md` for the full game-engine and audio credits. Commercial Blood data,
SoundFonts, music recordings and user maps are not bundled with this launcher.

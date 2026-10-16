# BloodPSP Launcher

Windows installer and visual NBLOOD.CFG editor. English interface with compact
Qt tabs, light/dark themes and interactive PSP control mapping. Layout reference:
[Sandstone PS2RC](https://github.com/SandstoneDev/PS2RC/).

## Use

Extract the complete portable package and open `BloodPSPLauncher.exe`.
Keep `_internal/` beside the executable. Python is not required.

1. In **Setup**, browse for `EBOOT.PBP` or select **Download latest from GitHub**.
2. Select your Blood installation folder and the PSP memory stick or output folder.
3. Adjust **Controls**, **Video**, **Audio** and **Game**, as needed.
4. Select **Build PSP folder**.

The result is `PSP/GAME/BloodPSP/`, containing the EBOOT, `nblood.cfg`, the 25
required game data files, `music/` and `usermaps/`. Available `blood02.ogg`
through `blood09.ogg` are copied automatically from `music/` or the source root.
Maps and matching `.DEF` descriptions in `usermaps/`, including subfolders,
are also copied automatically. OGG playback requires a compatible EBOOT.
Commercial game files and music are not included in the launcher.

Original source files remain intact. Existing output saves are preserved.
Changed managed files are backed up under `PSP/GAME/.bloodpsp-backups/`.
Failed or cancelled installations restore previous files. An existing output
CFG is kept unless **Apply editor settings** is enabled. Use **Edit output CFG**
to load it first. After applying editor settings, that output CFG becomes the
active document.

For PPSSPP, configure the exported root as its Memory Stick, or copy the
`BloodPSP/` folder into `PSP/GAME/` on its configured Memory Stick.

## Configuration and controls

**Open CFG**, **Save CFG** and **File > Save CFG as** work independently of
installation. The editor preserves comments, unknown options, encoding and
line endings, and checks for external edits before saving. **Advanced** exposes
every setting, with search and direct value editing.

Click a button on the PSP image or select an action in the mapping table.
The scheme is detected from known EBOOT builds and can be selected manually:

- **Standard 1:** current builds; L/R strafe, Cross fires, Triangle jumps.
  L + R + Cross activates secondary fire and also the individual L/R actions.
- **Standard 2:** original release; R fires, Cross jumps, L + Triangle and
  L + Square are special combinations.

Mappings edit the keyboard events used by the PSP backend. Each action supports
two bindings. Start opens the game menu and cannot be remapped. Analog axis
and sensitivity settings are editable below the button table.

GitHub downloads use the latest published stable release, which may differ
from your local build. Select your local EBOOT to test unpublished changes.
Downloads validate PBP structure, size and the GitHub SHA-256 digest when
available. A ZIP must contain exactly one EBOOT; other contents are not extracted.

## Development

Requires Python 3.10-3.15 on Windows. From `launcher/`:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run.py
```

Run `Build.cmd`, or specify paths:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -Python C:\Python314\python.exe -OutputDirectory C:\build\launcher-dist
```

The build script installs pinned dependencies in an isolated environment,
runs tests and packages the executable with PyInstaller. `-BuildRoot` and
`-EnvironmentDirectory` allow reuse of an external build environment.
Distribute the complete `BloodPSPLauncher/` folder or a ZIP of it.

```powershell
python -m unittest discover -s tests -v
python run.py --self-test C:\build\launcher-smoke
BloodPSPLauncher.exe --self-test C:\build\launcher-frozen-smoke
```

Self-test validates bundled artwork and control remapping, captures the UI
and writes a JSON report. Set `BLOODPSP_SMOKE_DOWNLOAD=1` to also verify a real
GitHub download. Test data is separate from the user's installation.

## Credits

BloodPSP: Rain and contributors. wa59: PSP controls, music, save fixes and
native resolution. Supplied Blood logos and PSP image are used as provided.
PSP button icons: VictorPines / Wikimedia Commons, CC BY-SA 4.0.
See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for sources and licenses.
The launcher's original source is MIT licensed; other assets retain their terms.

<div align="center">
  <img src="docs/images/bloodpsp.png" width="512" alt="Blood PSP">
</div>

# Blood PSP

[English](README.md) | [Português Brasileiro](README.pt-BR.md)

Unofficial work-in-progress port of **Blood** for the Sony PlayStation Portable. The EBOOT appears as **Blood** in the PSP menu.

Blood PSP started from a snapshot of [jfblood-vita](https://github.com/Rinnegatamante/jfblood-vita), which follows BSzili's [NBlood-to-JFBuild](https://github.com/BSzili/NBlood-Amiga) work. The game logic ultimately comes from [NBlood](https://github.com/nukeykt/NBlood).

<div align="center">
  <img src="docs/images/running-on-psp.png" width="512" alt="Blood running on a PSP">
</div>

## Status

Tested on a PSP Slim and PPSSPP. The menu, controls, map loading, gameplay, XMB exit callback, and PCM sound effects work. The release uses the classic BUILD software renderer. It can render at 320×200 for speed or 480×272 for a sharper image.

This is not a finished port. Crashes are expected because much of the game has not been tested yet, especially map transitions, episodes, saves, and unusual content combinations.

Current limits:

- Recorded OGG tracks can play through streaming. Copy `blood02.ogg` through `blood09.ogg` from the Steam installation into a `music/` subfolder beside the EBOOT. `CDAudioToggle = 1` selects tracks using `Track` in `BLOOD.INI`; the menu uses `blood02.ogg`.
- MIDI music uses TinySoundFont. Place a small General MIDI bank named `SOUNDFONT.SF2` beside the EBOOT; without it, only the MIDI fallback is silent (OGG and sound effects still work). Prefer banks around 2 MB or smaller: samples take more RAM after loading.
- Network play, Smacker videos, and voxels are not part of the current build.
- The PSP GE world renderer is experimental and disabled in the stable release.


Contributions from **wa59** are integrated for testing. Resolution remains selectable under **Options > Display Setup > Video Mode** and in `nblood.cfg`; the supplied configuration starts at 480×272. Save loading now restores local player pointers and uses the bounded PSP preload. These changes still need PSP/PPSSPP validation.

## Install

Only the Steam release of *One Unit Whole Blood* has been tested. Copy these files from a legal Steam installation into `ms0:/PSP/GAME/BloodPSP/`, alongside `EBOOT.PBP` and `nblood.cfg`:

```text
BLOOD.INI
BLOOD.RFF
GUI.RFF
SOUNDS.RFF
SURFACE.DAT
TABLES.DAT
TILES000.ART
TILES001.ART
TILES002.ART
TILES003.ART
TILES004.ART
TILES005.ART
TILES006.ART
TILES007.ART
TILES008.ART
TILES009.ART
TILES010.ART
TILES011.ART
TILES012.ART
TILES013.ART
TILES014.ART
TILES015.ART
TILES016.ART
TILES017.ART
VOXEL.DAT
```

The tested Steam folder has no required subdirectories. Other releases and mods are untested. Do not redistribute Blood game data with this project.

## Build

The commands below use Bash. On Windows, open an MSYS2 shell; on Linux, use a normal shell. The repository does not install PSPDEV for you. Install a PSPDEV toolchain and PSPSDK first.

### 1. Required tools

The following commands must be available in `PATH`:

```text
psp-gcc        psp-g++        psp-ar          psp-ranlib
mksfoex        pack-pbp       psp-prxgen      psp-fixup-imports
```

`make`, `git`, and Bash are also required. In MSYS2, use POSIX-style paths such as `/c/pspdev`, not `C:\pspdev`, when setting the variables below.

### 2. Clone the source and libraries

```sh
git clone --recurse-submodules <your-fork-url> Blood-PSP
cd Blood-PSP
```

If the repository was cloned without submodules, fetch them before building:

```sh
git submodule update --init --recursive
```

### 3. Configure the environment

Set `PSPDEV` to the toolchain prefix. PSPSDK is expected at `$PSPDEV/psp/sdk`.

```sh
export PSPDEV=/c/pspdev
export PSPSDK="$PSPDEV/psp/sdk"
export PATH="$PSPDEV/bin:$PSPSDK/bin:$PATH"
```

Replace `/c/pspdev` with your own toolchain location. Confirm the environment before compiling:

```sh
psp-gcc --version
psp-g++ --version
command -v mksfoex pack-pbp psp-prxgen psp-fixup-imports
```

### 4. Build the recommended release

```sh
make -f Makefile.psp PSP_EXTRA_DEFINES=-DPSP_STABLE_PERFORMANCE_BUILD blood-eboot-release
```

This target forces a full release rebuild, so it does not reuse objects from a diagnostic build. It enables the stable software-renderer profile and suppresses release logging.

### 5. Output

| File | Use |
| --- | --- |
| `EBOOT.PBP` | Copy this file to the PSP. Its title is **Blood**. |
| `EBOOT-release.PBP` | Copy of the same release EBOOT. |
| `jfbloodpsp.elf` / `jfbloodpsp.prx` | Intermediate build products. |

To create an instrumented EBOOT instead:

```sh
make -f Makefile.psp blood-eboot-diagnostic
```

That command overwrites `EBOOT.PBP` and also writes `EBOOT-diagnostic.PBP`. It is intended for debugging, not performance testing.


The PSP build automatically applies `patches/jfaudiolib-psp-midi.patch` to the pinned submodule to connect wa59's native audio backend. The patch is tracked in the main repository; submodule commits do not need to change.

### Notes

- `psp-fixup-imports` may print a "stubs out of order" warning with the current SDK. The build is complete only when Make exits with code `0` and `EBOOT.PBP` exists. Test every build on a real PSP.
- Game data is not needed to compile, only to run the EBOOT.
- `rsrc/ICON0.PNG` and `rsrc/PIC1.PNG` are packed into the EBOOT during the final `pack-pbp` step.
The PSP engine uses `-fwrapv` to preserve BUILD's 32-bit fixed-point arithmetic. This prevents out-of-bounds square-root table reads on long sloped walls, including WILLARD.MAP.

## User maps

Place Blood `.MAP` files in a `usermaps/` subfolder beside `EBOOT.PBP`. The PSP build creates the folder automatically. Open **NEW GAME > USER MAP**, select a file with **Cross**, then choose the difficulty. The browser accepts `.MAP` and `.map` and can navigate subfolders. Editor `.BAK` backups are not required. See [usermaps/README.md](usermaps/README.md).

## Controls

- Analog nub: move and turn, with a center dead zone
- Cross: shoot; Square: use; Triangle: jump; Circle: crouch
- L/R: strafe left/right
- L + R + Cross: secondary fire
- D-pad: up selects the next item; down uses it; left/right changes weapon
- Select: map; Start: menu/back; HOME: return to XMB

## `nblood.cfg`

Keep this file beside the EBOOT. It is not replaced by the build.

- `ScreenWidth = 320` and `ScreenHeight = 200` is the fastest option. The image is scaled to the PSP LCD.
- `ScreenWidth = 480` and `ScreenHeight = 272` is sharper but costs more CPU time.
- `SoundToggle = 0` disables sound effects and gives the most direct audio-related performance gain.
- `NumVoices = 8` is the default. Lower values, such as `4`, may help busy scenes but can drop sounds.
- `MixRate` selects a sample rate supported by PSP audio; this configuration defaults to 22050 Hz.
- `MusicToggle = 0` disables music; `1` enables it. Sound Setup exposes MUSIC, MUSIC VOLUME and OGG TRACKS.
- `CDAudioToggle = 1` prefers recorded OGG tracks; `0` uses the level MIDI song names. Missing OGG tracks can fall back to the original MIDI music.
- OGG uses a 512 KiB decoder arena and a 32 KiB PCM ring; it never loads the full track into RAM. Output follows `MixRate`.
- `AutoRun` remains configurable in the menu and config file. The PSP default is `1`.

`PSPLog` and `PSPPerfHUD` are diagnostic-build options. The release does not write periodic logs.

## Credits and references

| Project / people | Role | Link |
| --- | --- | --- |
| Sean Barrett / stb_vorbis | Streaming Ogg Vorbis decoder (MIT / public domain) | [stb](https://github.com/nothings/stb) |
| wa59 | Strafe controls and analog dead zone, TinySoundFont MIDI music, save-load fixes, and native-resolution adjustments | Source supplied directly to the project; see [CREDITS.md](CREDITS.md) |
| Bernhard Schelling / TinySoundFont | SoundFont2 synthesizer (MIT) | [TinySoundFont](https://github.com/schellingb/TinySoundFont) |
| Monolith Productions and Blood rights holders | Original game and data | [Blood](https://www.gog.com/en/game/one_unit_whole_blood) |
| Ken Silverman | BUILD engine | [advsys.net](https://advsys.net/ken/) |
| Jonathon Fowler and JFBuild contributors | JFBuild | [JFBuild](https://github.com/jonof/jfbuild) |
| Nuke.YKT and NBlood contributors | NBlood | [NBlood](https://github.com/nukeykt/NBlood) |
| BSzili | NBlood-to-JFBuild backport, JFAudioLib, JFMact | [NBlood-Amiga](https://github.com/BSzili/NBlood-Amiga) |
| Rinnegatamante | JFBlood Vita source used to start this port | [jfblood-vita](https://github.com/Rinnegatamante/jfblood-vita) |
| Crow-bar | PSPEDuke32 and PSPQuake2 technical references | [PSPEDuke32](https://github.com/Crow-bar/PSPEDuke32) · [PSPQuake2](https://github.com/Crow-bar/PSPQuake2) |
| PSPDEV / PSPSDK contributors | PSP SDK and toolchain | [PSPSDK](https://github.com/pspdev/pspsdk) |

## License

Source code is distributed under [GPL-2.0](LICENSE), subject to the licenses of included components. Blood PSP is an unofficial fan port and is not endorsed by the Blood rights holders.
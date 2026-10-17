<div align="center">
  <img src="docs/images/bloodpsp.png" width="512" alt="Blood PSP">
</div>

# Blood PSP

[English](README.md) | [Português Brasileiro](README.pt-BR.md)

Blood for the PSP, based on [jfblood-vita](https://github.com/Rinnegatamante/jfblood-vita) and [NBlood-Amiga](https://github.com/BSzili/NBlood-Amiga).

Still in development. Tested on PSP Slim and PPSSPP.

<img src="docs/images/running-on-psp.png" width="512" alt="Blood running on PSP">

## Install

Download the [Windows GUI](https://github.com/RainArcanjo/BloodPSP/releases/latest). It builds the PSP folder from your game files and lets you edit the controls, video, sound and `nblood.cfg`.

Compatible with **Blood: Fresh Supply** and **One Unit Whole Blood**. You need your own copy of the game.

1. Extract the ZIP and open `BloodPSPLauncher.exe`.
2. Select your Blood installation folder. The EBOOT is already included; you can also select another one or download it from GitHub.
3. Select your PSP memory stick or an output folder.
4. Click **BUILD PSP FOLDER**.
5. Copy the generated `PSP` folder to your memory stick, if you built it on the PC.

Available OGG music and user maps are copied automatically. Your original game files stay where they are.

![BloodPSP GUI — setup](docs/images/launcher-setup.png)

### Manual installation

If you prefer to copy the files yourself, create `PSP/GAME/BloodPSP/` on your memory stick. Put the release `EBOOT.PBP` and [nblood.cfg](nblood.cfg) there, then copy the following files from your Blood installation into the same folder:

```text
PSP/GAME/BloodPSP/
├── EBOOT.PBP
├── nblood.cfg
├── BLOOD.INI
├── BLOOD.RFF
├── GUI.RFF
├── SOUNDS.RFF
├── SURFACE.DAT
├── TABLES.DAT
├── TILES000.ART
├── TILES001.ART
├── TILES002.ART
├── TILES003.ART
├── TILES004.ART
├── TILES005.ART
├── TILES006.ART
├── TILES007.ART
├── TILES008.ART
├── TILES009.ART
├── TILES010.ART
├── TILES011.ART
├── TILES012.ART
├── TILES013.ART
├── TILES014.ART
├── TILES015.ART
├── TILES016.ART
├── TILES017.ART
└── VOXEL.DAT
```

Copy the files directly beside `EBOOT.PBP`, without putting them inside another game folder. Keep your original files on the PC.

Optional: put `blood02.ogg` through `blood09.ogg` in `PSP/GAME/BloodPSP/music/`, keeping those names. User maps go in `PSP/GAME/BloodPSP/usermaps/`.

## Controls

Open **Controls** to change buttons and combinations. **Map button** works with a DualShock/DualSense or the on-screen PSP. Hold the buttons together, then release them.

Use **Save preset** and **Load preset** to keep your layouts. With the game closed, click **Apply controls** to save the CFG, then start the game.

![BloodPSP GUI — controls](docs/images/launcher-controls.png)

## User maps

Put `.MAP` files in `PSP/GAME/BloodPSP/usermaps/`. In the game, open **NEW GAME > USER MAP**.

OGG music, saves and native 480×272 resolution are supported. You can select 320×200 for better performance. Network play, Smacker videos and voxels are not supported yet.

## Build from source

### EBOOT

Install PSPDEV and PSPSDK first. You also need Git, Make and Bash. On Windows, use an MSYS2 shell.

Clone the project with its libraries:

```sh
git clone --recurse-submodules https://github.com/RainArcanjo/BloodPSP.git
cd BloodPSP
```

Set the toolchain path and build. Replace `/c/pspdev` with your PSPDEV folder:

```sh
export PSPDEV=/c/pspdev
export PSPSDK="$PSPDEV/psp/sdk"
export PATH="$PSPDEV/bin:$PSPSDK/bin:$PATH"
make -f Makefile.psp PSP_EXTRA_DEFINES=-DPSP_STABLE_PERFORMANCE_BUILD blood-eboot-release
```

The result is `EBOOT.PBP`, also saved as `EBOOT-release.PBP`. Select it in the GUI to build the PSP folder. Game files are not needed to compile.

If you already cloned without the libraries, run `git submodule update --init --recursive` before building.

### Windows GUI

With Python installed, run `launcher/Build.cmd`. To include your compiled EBOOT, use PowerShell from the repository folder:

```powershell
.\launcher\Build.cmd -EbootPath C:\build\EBOOT.PBP
```

Replace that path with your EBOOT. The script runs the tests and creates the executable. Keep the whole generated folder, including `_internal`.

More build options: [docs/BUILD.md](docs/BUILD.md).

## Credits

| Project / people | Contribution |
| --- | --- |
| Monolith Productions and Blood rights holders | Original game |
| [Ken Silverman](https://advsys.net/ken/) | BUILD engine |
| Jonathon Fowler and [JFBuild contributors](https://github.com/jonof/jfbuild) | JFBuild |
| Nuke.YKT and [NBlood contributors](https://github.com/nukeykt/NBlood) | NBlood |
| [BSzili](https://github.com/BSzili/NBlood-Amiga) | NBlood-Amiga, JFAudioLib and JFMact |
| [Rinnegatamante](https://github.com/Rinnegatamante/jfblood-vita) | jfblood-vita, the starting point for this port |
| **wa59** | PSP strafing, MIDI music, save fixes and native resolution |
| [Crow-bar](https://github.com/Crow-bar/PSPEDuke32) | PSPEDuke32 and PSPQuake2 references |
| [PSPDEV / PSPSDK contributors](https://github.com/pspdev/pspsdk) | PSP SDK and toolchain |
| Bernhard Schelling / Steve Folta | TinySoundFont / SFZero |
| Sean Barrett | stb_vorbis |

Component details and notices: [CREDITS.md](CREDITS.md).

## License

Source code is distributed under [GPL-2.0](LICENSE), subject to the licenses of included components. Blood PSP is an unofficial fan port.

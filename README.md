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

## Controls

Open **Controls** to change buttons and combinations. **Map button** works with a DualShock/DualSense or the on-screen PSP. Hold the buttons together, then release them.

Use **Save preset** and **Load preset** to keep your layouts. With the game closed, click **Apply controls** to save the CFG, then start the game.

![BloodPSP GUI — controls](docs/images/launcher-controls.png)

## User maps

Put `.MAP` files in `PSP/GAME/BloodPSP/usermaps/`. In the game, open **NEW GAME > USER MAP**.

OGG music, saves and native 480×272 resolution are supported. You can select 320×200 for better performance. Network play, Smacker videos and voxels are not supported yet.

Thanks to **wa59** for the controls, MIDI music, save fixes and native resolution work.

[Credits](CREDITS.md) · [Build from source](docs/BUILD.md) · [License](LICENSE)

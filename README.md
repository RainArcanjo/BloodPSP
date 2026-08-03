# NBlood-Amiga
A backport of [NBlood](https://github.com/nukeykt/NBlood) to JFBuild.

## PSP MVP builds

From an MSYS2 shell with `PSPDEV` and `PSPSDK` configured:

```sh
make -f Makefile.psp blood-eboot-release
make -f Makefile.psp blood-eboot-diagnostic
```

The release target creates `EBOOT.PBP` and `EBOOT-release.PBP`. It is silent:
it never creates or writes `nblood.log` or `jfblood.log`. The diagnostic target
fully rebuilds the objects with its instrumentation and additionally creates
`EBOOT-diagnostic.PBP`.

## PSP options

The PSP port reads `nblood.cfg` beside `EBOOT.PBP`.

```ini
[Setup]
PSPLog = 1       ; diagnostic build only: write jfblood.log and nblood.log

[Options]
PSPPerfHUD = 1   ; show the FPS counter; diagnostic additionally shows U/R/P ms
```

`PSPPerfHUD` is available in both builds through **OPTIONS → DISPLAY SETUP →
PERFORMANCE HUD**. It never enables logging in the release build. Choose the
rendering resolution through **DISPLAY SETUP → VIDEO MODE → RESOLUTION**, then
select **APPLY CHANGES**: `320 x 200` is the fast classic renderer scaled to
the 480×272 LCD, while `480 x 272` renders natively for sharper output.
## PSP default layout

| PSP input | Game action |
| --- | --- |
| Analog nub / D-pad | Move and turn |
| Cross | Jump |
| Circle | Crouch |
| Square | Use / interact |
| Triangle | Next weapon |
| L | Secondary fire |
| R | Primary fire |
| Select | Map |
| Start | ESC — open, close, or go back in menus |
| L + Square | Toggle Always Run |
| L + Triangle | Previous weapon |

The game renders at the PSP native 480×272 resolution. The horizontal nub input is 25% less sensitive by default. Button bindings are
translated by the PSP backend so stale desktop `JoystickButtonN` entries cannot
create a second action; analogue-axis settings in `nblood.cfg` remain active.
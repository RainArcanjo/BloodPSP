# NBlood-Amiga
A backport of [NBlood](https://github.com/nukeykt/NBlood) to JFBuild.

## PSP MVP configuration

The PSP port reads `nblood.cfg` beside `EBOOT.PBP`. To disable its diagnostic
file (`jfblood.log`), add this under `[Setup]`:

```ini
PSPLog = 0
```

Use `PSPLog = 1` (or omit the setting) to retain diagnostics.

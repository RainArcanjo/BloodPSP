# Build

## PSP

Install PSPDEV and PSPSDK. On Windows, run these commands in MSYS2.

```sh
git clone --recurse-submodules https://github.com/RainArcanjo/BloodPSP.git
cd BloodPSP
export PSPDEV=/path/to/pspdev
export PSPSDK="$PSPDEV/psp/sdk"
export PATH="$PSPDEV/bin:$PSPSDK/bin:$PATH"
make -f Makefile.psp PSP_EXTRA_DEFINES=-DPSP_STABLE_PERFORMANCE_BUILD blood-eboot-release
```

The output is `EBOOT.PBP`. `nblood.cfg` belongs beside it. Game files are not
needed to compile. The build applies the tracked JFAudioLib patch automatically.

For diagnostics, use `make -f Makefile.psp blood-eboot-diagnostic`.

## Windows GUI

With Python installed, run `launcher/Build.cmd`, or:

```powershell
.\launcher\build.ps1 -Python C:\Python314\python.exe -EbootPath C:\build\EBOOT.PBP
```

The script runs the tests and creates a portable Windows folder. Build files
and the Python environment are kept outside the repository. Distribute the
whole folder, including `_internal`.

To run the GUI from source:

```powershell
cd launcher
python -m pip install -r requirements.txt
python run.py
```

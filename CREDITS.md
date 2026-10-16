# Contributions and third-party code

**wa59** supplied the source changes integrated in this version: PSP shoulder-button strafing and analog dead zone, TinySoundFont MIDI playback, save-loading fixes, and native-resolution menu adjustments. The supplied work was based on commit `3810f0f` and was shared directly with Rain, without a separate fork. Credit for these contributions belongs to wa59.

Integration keeps the original project's pinned submodules, routes audio through the native PSP driver, keeps resolution and AutoRun configurable, preserves secondary fire on L + R + Cross, and cleans up MIDI threads and buffered music when playback stops. These adaptations do not change attribution for wa59's original implementation.

`platform/tsf.h` is TinySoundFont v0.9 by Bernhard Schelling, based on SFZero by Steve Folta. Its MIT copyright notice and full license are preserved in that header. Upstream: https://github.com/schellingb/TinySoundFont

The PSP JFAudioLib changes are recorded in `patches/jfaudiolib-psp-midi.patch`: native MIDI entry points, a replaceable PSP audio source, PSP sleep support, and aligned MIDI signature reads (the track-signature fix comes from wa59).

Commercial Blood data and SoundFont banks are external runtime assets, not included in the source repository. Existing project and component credits remain in the READMEs and their original source files.

`platform/stb_vorbis.c` is Sean Barrett's stb_vorbis v1.22, fetched from upstream commit `1ee679ca2ef753a528db5ba6801e1067b40481b8` (SHA256 `4c7cb2ff1f7011e9d67950446b7eb9ca044f2e464d76bfbb0b84dd2e23e65636`). Its full dual MIT/public-domain license is preserved in the source. Upstream: https://github.com/nothings/stb

`platform/psp_ogg.c` and `platform/psp_music.c` add a bounded-memory streaming path for the user's own recorded Blood soundtrack. This extends the wa59 integration; attribution for wa59's controls, MIDI synthesis and save fixes remains unchanged. Commercial OGG tracks are not included in the source repository.

#ifndef BLOOD_PSP_MUSIC_H
#define BLOOD_PSP_MUSIC_H
#ifdef __cplusplus
extern "C" {
#endif

int psp_music_play(const char *song, int loop, int output_rate);
void psp_music_stop(void);
void psp_music_shutdown(void);
void psp_music_set_volume(int volume);
int psp_music_is_playing(void);
/* Called by the PCM thread while holding PSPDrv_PCM_Lock. */
void psp_music_mix(short *stereo, int frames);

#ifdef __cplusplus
}
#endif
#endif

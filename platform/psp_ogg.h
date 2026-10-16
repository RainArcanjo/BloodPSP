/* Bounded-memory Ogg Vorbis reader. Decoder: stb_vorbis by Sean Barrett. */
#ifndef BLOOD_PSP_OGG_H
#define BLOOD_PSP_OGG_H

typedef struct psp_ogg psp_ogg;
psp_ogg *psp_ogg_open(const char *filename, int output_rate, int loop);
int psp_ogg_read(psp_ogg *stream, short *stereo, int frames);
void psp_ogg_close(psp_ogg *stream);

#endif

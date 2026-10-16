/* Read compressed data from disk in blocks; never load a whole song. */
#include <stdlib.h>
#include "psp_ogg.h"
#define STB_VORBIS_NO_PUSHDATA_API
#define STB_VORBIS_MAX_CHANNELS 2
#include "stb_vorbis.c"

#define OGG_DECODER_BYTES (512 * 1024)
#define OGG_INPUT_FRAMES 1024

struct psp_ogg {
    stb_vorbis *decoder;
    /* stb_vorbis uses this arena for setup and frame scratch allocations. */
    union { double alignment; char bytes[OGG_DECODER_BYTES]; } arena;
    short input[OGG_INPUT_FRAMES * 2];
    short current[2], next[2];
    int count, position, source_rate, output_rate, loop;
    int primed, last, finished;
    unsigned phase;
};

psp_ogg *psp_ogg_open(const char *filename, int output_rate, int loop)
{
    psp_ogg *s;
    stb_vorbis_alloc alloc;
    stb_vorbis_info info;
    int error;
    if (output_rate < 8000 || output_rate > 48000) return NULL;
    s = (psp_ogg *)calloc(1, sizeof(*s));
    if (!s) return NULL;
    alloc.alloc_buffer = s->arena.bytes;
    alloc.alloc_buffer_length_in_bytes = sizeof(s->arena.bytes);
    s->decoder = stb_vorbis_open_filename(filename, &error, &alloc);
    if (!s->decoder) { free(s); return NULL; }
    info = stb_vorbis_get_info(s->decoder);
    if (info.sample_rate < 8000 || info.sample_rate > 96000 ||
        info.channels < 1 || info.channels > 2) {
        psp_ogg_close(s);
        return NULL;
    }
    s->source_rate = (int)info.sample_rate;
    s->output_rate = output_rate;
    s->loop = !!loop;
    return s;
}

static int ogg_frame(psp_ogg *s, short frame[2])
{
    if (s->position == s->count) {
        s->count = stb_vorbis_get_samples_short_interleaved(s->decoder, 2,
            s->input, OGG_INPUT_FRAMES * 2);
        s->position = 0;
        if (!s->count && s->loop &&
            stb_vorbis_get_error(s->decoder) == VORBIS__no_error &&
            stb_vorbis_seek_start(s->decoder)) {
            s->count = stb_vorbis_get_samples_short_interleaved(s->decoder, 2,
                s->input, OGG_INPUT_FRAMES * 2);
        }
        if (!s->count) return 0; /* Includes empty/corrupt looping files. */
    }
    frame[0] = s->input[s->position * 2];
    frame[1] = s->input[s->position * 2 + 1];
    ++s->position;
    return 1;
}

int psp_ogg_read(psp_ogg *s, short *stereo, int frames)
{
    int written = 0;
    if (!s || frames <= 0 || s->finished) return 0;
    if (!s->primed) {
        if (!ogg_frame(s, s->current)) { s->finished = 1; return 0; }
        s->last = !ogg_frame(s, s->next);
        if (s->last) s->next[0] = s->current[0], s->next[1] = s->current[1];
        s->primed = 1;
    }
    while (written < frames && !s->finished) {
        int c;
        /* Exact rational phase: no drift when converting 44100 to 22050, etc.
           Weights sum to <=48000, so these signed 32-bit products fit. */
        for (c = 0; c < 2; ++c)
            stereo[written * 2 + c] = (short)((s->current[c] *
                (s->output_rate - (int)s->phase) + s->next[c] * (int)s->phase) /
                s->output_rate);
        ++written;
        s->phase += s->source_rate;
        while (s->phase >= (unsigned)s->output_rate) {
            s->phase -= s->output_rate;
            if (s->last) { s->finished = 1; break; }
            s->current[0] = s->next[0]; s->current[1] = s->next[1];
            s->last = !ogg_frame(s, s->next);
            if (s->last) s->next[0] = s->current[0], s->next[1] = s->current[1];
        }
    }
    return written;
}

void psp_ogg_close(psp_ogg *s)
{
    if (!s) return;
    stb_vorbis_close(s->decoder);
    free(s);
}

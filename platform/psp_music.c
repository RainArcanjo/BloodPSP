/* OGG streaming alongside wa59's PSP PCM/MIDI backend. */
#include <pspkernel.h>
#include <pspthreadman.h>
#include <stdio.h>
#include <string.h>
#include "psp_music.h"
#include "psp_ogg.h"

void PSPDrv_PCM_Lock(void);
void PSPDrv_PCM_Unlock(void);

#define MUSIC_RING_FRAMES 8192
#define MUSIC_CHUNK_FRAMES 256

static short music_ring[MUSIC_RING_FRAMES * 2];
static volatile unsigned music_read, music_write;
static volatile int music_volume = 255;
static psp_ogg *music_stream;
static int music_decoding, music_mutex_ready;
static SceLwMutexWorkarea music_mutex;
static SceUID music_thread = -1;
static volatile int music_run;

/* Sole producer. The PCM consumer never waits for the decoder mutex. */
static int music_pump(void)
{
    int count = 0;
    sceKernelLockLwMutex(&music_mutex, 1, NULL);
    if (music_stream && music_decoding &&
        MUSIC_RING_FRAMES - (unsigned)(music_write - music_read) >= MUSIC_CHUNK_FRAMES) {
        unsigned offset = music_write % MUSIC_RING_FRAMES;
        unsigned capacity = MUSIC_RING_FRAMES - offset;
        if (capacity > MUSIC_CHUNK_FRAMES) capacity = MUSIC_CHUNK_FRAMES;
        count = psp_ogg_read(music_stream, music_ring + offset * 2, capacity);
        if (!count) music_decoding = 0;
        __sync_synchronize();
        music_write += count;
    }
    sceKernelUnlockLwMutex(&music_mutex, 1);
    return count;
}

static int music_worker(SceSize args, void *argp)
{
    (void)args; (void)argp;
    while (music_run) {
        if (!music_pump()) sceKernelDelayThread(4000);
    }
    return 0;
}

static int music_start_worker(void)
{
    if (!music_mutex_ready) {
        if (sceKernelCreateLwMutex(&music_mutex, "bloodogg",
            PSP_LW_MUTEX_ATTR_RECURSIVE, 0, NULL) < 0) return -1;
        music_mutex_ready = 1;
    }
    if (music_thread >= 0) return 0;
    music_run = 1;
    /* Decode ahead of the game thread, sleeping when the ring is full. */
    music_thread = sceKernelCreateThread("bloodogg", music_worker, 0x1e,
        0x10000, PSP_THREAD_ATTR_USER, NULL);
    if (music_thread < 0) { music_run = 0; return -1; }
    if (sceKernelStartThread(music_thread, 0, NULL) < 0) {
        sceKernelDeleteThread(music_thread);
        music_thread = -1;
        music_run = 0;
        return -1;
    }
    return 0;
}

int psp_music_play(const char *song, int loop, int output_rate)
{
    char filename[512];
    const char *extension;
    psp_ogg *next = NULL;
    int location;
    if (!song || !song[0]) return -1;
    extension = strrchr(song, '.');
    for (location = 0; location < 2 && !next; ++location) {
        int size = snprintf(filename, sizeof(filename), "%s%s%s",
            location == 0 ? "music/" : "", song,
            extension && (!strcmp(extension, ".ogg") || !strcmp(extension, ".OGG")) ? "" : ".ogg");
        if (size < 0 || size >= (int)sizeof(filename)) continue;
        next = psp_ogg_open(filename, output_rate, loop);
    }
    if (!next) return -1;
    if (music_start_worker() < 0) { psp_ogg_close(next); return -1; }
    sceKernelLockLwMutex(&music_mutex, 1, NULL);
    psp_ogg_close(music_stream);
    music_stream = next;
    music_decoding = 1;
    PSPDrv_PCM_Lock();
    music_read = music_write = 0;
    PSPDrv_PCM_Unlock();
    sceKernelUnlockLwMutex(&music_mutex, 1);
    /* Prime a small block so playback does not wait for the next worker tick. */
    music_pump();
    return 0;
}

void psp_music_stop(void)
{
    if (!music_mutex_ready) return;
    sceKernelLockLwMutex(&music_mutex, 1, NULL);
    psp_ogg_close(music_stream);
    music_stream = NULL;
    music_decoding = 0;
    PSPDrv_PCM_Lock();
    music_read = music_write = 0;
    PSPDrv_PCM_Unlock();
    sceKernelUnlockLwMutex(&music_mutex, 1);
}

void psp_music_shutdown(void)
{
    psp_music_stop();
    music_run = 0;
    if (music_thread >= 0) {
        sceKernelWaitThreadEnd(music_thread, NULL);
        sceKernelDeleteThread(music_thread);
        music_thread = -1;
    }
}

void psp_music_set_volume(int volume)
{
    if (volume < 0) volume = 0;
    if (volume > 255) volume = 255;
    music_volume = volume;
}

int psp_music_is_playing(void)
{
    int playing;
    if (!music_mutex_ready) return 0;
    sceKernelLockLwMutex(&music_mutex, 1, NULL);
    playing = music_stream && (music_decoding || music_write != music_read);
    sceKernelUnlockLwMutex(&music_mutex, 1);
    return playing;
}

void psp_music_mix(short *stereo, int frames)
{
    unsigned read = music_read;
    unsigned available = music_write - read;
    int volume = music_volume;
    int i, c;
    __sync_synchronize();
    if (available > (unsigned)frames) available = frames;
    for (i = 0; i < (int)available; ++i) {
        const short *src = music_ring + ((read + i) % MUSIC_RING_FRAMES) * 2;
        for (c = 0; c < 2; ++c) {
            int value = stereo[i * 2 + c] + src[c] * volume / 255;
            stereo[i * 2 + c] = value > 32767 ? 32767 : value < -32768 ? -32768 : value;
        }
    }
    __sync_synchronize();
    music_read = read + available;
}

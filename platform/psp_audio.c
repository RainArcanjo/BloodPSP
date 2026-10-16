// PSP PCM/MIDI backend contributed by wa59.
// Adapted to JFAudioLib's native PSP driver slot; TinySoundFont license is in tsf.h.
#include <pspkernel.h>
#include <pspaudio.h>
#include <pspthreadman.h>
#include <string.h>
#include "../jfaudiolib/src/midifuncs.h"
#define TSF_IMPLEMENTATION
#include "tsf.h"
#include "psp_music.h"

#define PSP_AUDIO_FRAMES 1024 // multiple of 64, as required by the hardware
#define PSP_AUDIO_BYTES (PSP_AUDIO_FRAMES * 4)

void PSPDrv_PCM_Shutdown(void);
void PSPDrv_PCM_StopPlayback(void);
void PSPDrv_PCM_Lock(void);
void PSPDrv_PCM_Unlock(void);

static int g_channel = -1;
static int g_mixrate = 22050;
static short g_out[2][PSP_AUDIO_FRAMES * 2] __attribute__((aligned(64)));
static void psp_midi_mix(short *dst, int frames);
static void (*g_midi_service)(void);
static int g_initialised;
static volatile int g_playing, g_run;
static SceUID g_thread = -1;
static SceLwMutexWorkarea g_mutex;
static int g_mutex_ready;

static char *g_mixbuf;
static int g_mixsize, g_mixcount, g_mixcur, g_mixused;
static void (*g_callback)(void);
static void psp_audio_fill(char *dst, int remaining)
{
    while (remaining > 0) {
        if (g_mixused == g_mixsize) {
            g_callback();
            g_mixused = 0;
            if (++g_mixcur >= g_mixcount)
                g_mixcur -= g_mixcount;
        }
        int len = g_mixsize - g_mixused;
        if (len > remaining)
            len = remaining;
        memcpy(dst, g_mixbuf + g_mixcur * g_mixsize + g_mixused, len);
        dst += len;
        g_mixused += len;
        remaining -= len;
    }
}

static int psp_audio_thread(SceSize args, void *argp)
{
    int page = 0;
    (void)args; (void)argp;
    while (g_run) {
        sceKernelLockLwMutex(&g_mutex, 1, NULL);
        if (g_playing)
            psp_audio_fill((char *)g_out[page], PSP_AUDIO_BYTES);
        else
            memset(g_out[page], 0, PSP_AUDIO_BYTES);
        psp_midi_mix(g_out[page], PSP_AUDIO_FRAMES);
        psp_music_mix(g_out[page], PSP_AUDIO_FRAMES);
        sceKernelUnlockLwMutex(&g_mutex, 1);
        sceAudioSRCOutputBlocking(PSP_AUDIO_VOLUME_MAX, g_out[page]);
        page ^= 1;
    }
    return 0;
}

int PSPDrv_GetError(void) { return 0; }

const char *PSPDrv_ErrorString(int ErrorNumber)
{
    (void)ErrorNumber;
    return "PSP audio error.";
}

int PSPDrv_PCM_Init(int *mixrate, int *numchannels, int *samplebits, void *initdata)
{
    static const int rates[] = { 8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000 };
    int i, ok = 0;
    (void)initdata;

    if (g_initialised)
        PSPDrv_PCM_Shutdown();

    for (i = 0; i < (int)(sizeof(rates) / sizeof(rates[0])); ++i)
        if (*mixrate == rates[i]) ok = 1;
    if (!ok)
        *mixrate = 22050;
    *numchannels = 2;
    *samplebits = 16;

    if (!g_mutex_ready) {
        if (sceKernelCreateLwMutex(&g_mutex, "bloodaudio", PSP_LW_MUTEX_ATTR_RECURSIVE, 0, NULL) < 0)
            return -1;
        g_mutex_ready = 1;
    }

    g_mixrate = *mixrate;
    g_channel = sceAudioSRCChReserve(PSP_AUDIO_FRAMES, *mixrate, 2);
    if (g_channel < 0)
        return -1;

    g_initialised = 1;
    return 0;
}

void PSPDrv_PCM_Shutdown(void)
{
    if (!g_initialised)
        return;
    psp_music_shutdown();
    PSPDrv_PCM_StopPlayback();
    sceAudioSRCChRelease();
    g_channel = -1;
    g_initialised = 0;
}

int PSPDrv_PCM_BeginPlayback(char *BufferStart, int BufferSize, int NumDivisions, void (*CallBackFunc)(void))
{
    if (!g_initialised)
        return -1;
    if (g_thread >= 0)
        PSPDrv_PCM_StopPlayback();

    g_mixbuf = BufferStart;
    g_mixsize = BufferSize;
    g_mixcount = NumDivisions;
    g_mixcur = 0;
    g_mixused = 0;
    g_callback = CallBackFunc;
    g_callback(); // prime the first division

    g_playing = 1;
    g_run = 1;
    g_thread = sceKernelCreateThread("bloodaudio", psp_audio_thread, 0x12, 0x8000, PSP_THREAD_ATTR_USER, NULL);
    if (g_thread < 0) {
        g_playing = g_run = 0;
        return -1;
    }
    if (sceKernelStartThread(g_thread, 0, NULL) < 0) {
        sceKernelDeleteThread(g_thread);
        g_thread = -1;
        g_playing = g_run = 0;
        return -1;
    }
    return 0;
}

void PSPDrv_PCM_StopPlayback(void)
{
    if (g_thread < 0)
        return;
    g_run = 0;
    g_playing = 0;
    sceKernelWaitThreadEnd(g_thread, NULL);
    sceKernelDeleteThread(g_thread);
    g_thread = -1;
}

void PSPDrv_PCM_Lock(void)
{
    if (g_mutex_ready)
        sceKernelLockLwMutex(&g_mutex, 1, NULL);
}

void PSPDrv_PCM_Unlock(void)
{
    if (g_mutex_ready)
        sceKernelUnlockLwMutex(&g_mutex, 1);
}

int PSPDrv_CD_Init(void) { return -1; }
void PSPDrv_CD_Shutdown(void) {}
int PSPDrv_CD_Play(int track, int loop) { (void)track; (void)loop; return -1; }
void PSPDrv_CD_Stop(void) {}
void PSPDrv_CD_Pause(int pauseon) { (void)pauseon; }
int PSPDrv_CD_IsPlaying(void) { return 0; }
void PSPDrv_CD_SetVolume(int volume) { (void)volume; }

// ---- MIDI via TinySoundFont ----
static tsf *g_tsf;
static double g_midi_tps; // MIDI ticks per second
static double g_midi_acc;

// The synthesizer runs on its own low priority thread and feeds a ring buffer
// so that it only uses CPU time the game doesn't need.
#define RING_FRAMES 8192
static short g_ring[RING_FRAMES * 2];
static volatile unsigned g_rd, g_wr;
static SceLwMutexWorkarea g_mmutex;
static int g_mmutex_ready;
static SceUID g_mthread = -1;
static volatile int g_midi_run;
static int g_music_volume = 255;

static int psp_midi_thread(SceSize args, void *argp);
void PSPDrv_MIDI_Shutdown(void);

// The PCM thread consumes the ring without taking the MIDI mutex. Stop it
// briefly before discarding queued samples, so a new song starts cleanly.
static void psp_midi_flush(void)
{
    PSPDrv_PCM_Lock();
    g_rd = g_wr;
    PSPDrv_PCM_Unlock();
}
static void m_off(int c, int k, int v) { (void)v; if (g_tsf) tsf_channel_note_off(g_tsf, c, k); }
static void m_on(int c, int k, int v)
{
    if (!g_tsf) return;
    if (v == 0) tsf_channel_note_off(g_tsf, c, k);
    else tsf_channel_note_on(g_tsf, c, k, v / 127.0f);
}
static void m_poly(int c, int k, int p) { (void)c; (void)k; (void)p; }
static void m_cc(int c, int n, int v) { if (g_tsf) tsf_channel_midi_control(g_tsf, c, n, v); }
static void m_pc(int c, int p) { if (g_tsf) tsf_channel_set_presetnumber(g_tsf, c, p, c == 9); }
static void m_chat(int c, int p) { (void)c; (void)p; }
static void m_pb(int c, int lsb, int msb) { if (g_tsf) tsf_channel_set_pitchwheel(g_tsf, c, (msb << 7) | lsb); }
static void m_rel(void) {}
static void m_load(int n) { (void)n; }
static void m_setvol(int v)
{
    if (v < 0) v = 0;
    if (v > 255) v = 255;
    if (g_mmutex_ready) sceKernelLockLwMutex(&g_mmutex, 1, NULL);
    g_music_volume = v;
    if (g_tsf) tsf_set_volume(g_tsf, v / 255.0f);
    if (g_mmutex_ready) sceKernelUnlockLwMutex(&g_mmutex, 1);
}
static int m_getvol(void) { return g_music_volume; }
static void m_sysex(const unsigned char *d, int l) { (void)d; (void)l; }

int PSPDrv_MIDI_Init(midifuncs *funcs, const char *params)
{
    static const char *names[] = { "SOUNDFONT.SF2", "soundfont.sf2", "BLOOD.SF2", "blood.sf2", "GM.SF2", "gm.sf2" };
    int i;
    (void)params;
    if (g_tsf || g_mthread >= 0)
        PSPDrv_MIDI_Shutdown();
    if (!g_mmutex_ready) {
        if (sceKernelCreateLwMutex(&g_mmutex, "bloodmidi", PSP_LW_MUTEX_ATTR_RECURSIVE, 0, NULL) < 0)
            return -1;
        g_mmutex_ready = 1;
    }
    for (i = 0; i < 6 && !g_tsf; ++i)
        g_tsf = tsf_load_filename(names[i]);
    if (!g_tsf)
        return -1;
    tsf_set_output(g_tsf, TSF_STEREO_INTERLEAVED, g_mixrate / 2, 0);
    tsf_set_max_voices(g_tsf, 12);
    tsf_channel_set_presetnumber(g_tsf, 9, 0, 1);
    tsf_set_volume(g_tsf, g_music_volume / 255.0f);

    funcs->NoteOff = m_off;
    funcs->NoteOn = m_on;
    funcs->PolyAftertouch = m_poly;
    funcs->ControlChange = m_cc;
    funcs->ProgramChange = m_pc;
    funcs->ChannelAftertouch = m_chat;
    funcs->PitchBend = m_pb;
    funcs->ReleasePatches = m_rel;
    funcs->LoadPatch = m_load;
    funcs->SetVolume = m_setvol;
    funcs->GetVolume = m_getvol;
    funcs->SysEx = m_sysex;

    if (g_mthread < 0) {
        // Lower priority than the main game thread (0x20).
        g_midi_run = 1;
        g_mthread = sceKernelCreateThread("bloodmidi", psp_midi_thread, 0x21, 0x10000, PSP_THREAD_ATTR_USER, NULL);
        if (g_mthread < 0) {
            g_midi_run = 0;
            tsf_close(g_tsf);
            g_tsf = NULL;
            return -1;
        }
        if (sceKernelStartThread(g_mthread, 0, NULL) < 0) {
            sceKernelDeleteThread(g_mthread);
            g_mthread = -1;
            g_midi_run = 0;
            tsf_close(g_tsf);
            g_tsf = NULL;
            return -1;
        }
    }
    return 0;
}

void PSPDrv_MIDI_Shutdown(void)
{
    if (!g_mmutex_ready)
        return;
    sceKernelLockLwMutex(&g_mmutex, 1, NULL);
    g_midi_service = 0;
    g_midi_run = 0;
    sceKernelUnlockLwMutex(&g_mmutex, 1);
    if (g_mthread >= 0) {
        sceKernelWaitThreadEnd(g_mthread, NULL);
        sceKernelDeleteThread(g_mthread);
        g_mthread = -1;
    }
    if (g_tsf) { tsf_close(g_tsf); g_tsf = NULL; }
    psp_midi_flush();
}

int PSPDrv_MIDI_StartPlayback(void (*service)(void))
{
    if (!g_mmutex_ready || !g_tsf)
        return -1;
    sceKernelLockLwMutex(&g_mmutex, 1, NULL);
    psp_midi_flush();
    g_midi_acc = 0;
    g_midi_service = service;
    sceKernelUnlockLwMutex(&g_mmutex, 1);
    return 0;
}

void PSPDrv_MIDI_HaltPlayback(void)
{
    if (!g_mmutex_ready)
        return;
    sceKernelLockLwMutex(&g_mmutex, 1, NULL);
    g_midi_service = 0;
    if (g_tsf) tsf_reset(g_tsf);
    psp_midi_flush();
    sceKernelUnlockLwMutex(&g_mmutex, 1);
}

void PSPDrv_MIDI_SetTempo(int tempo, int division)
{
    g_midi_tps = (double)tempo * division / 60.0;
}

void PSPDrv_MIDI_Lock(void) { if (g_mmutex_ready) sceKernelLockLwMutex(&g_mmutex, 1, NULL); }
void PSPDrv_MIDI_Unlock(void) { if (g_mmutex_ready) sceKernelUnlockLwMutex(&g_mmutex, 1); }


static int psp_midi_thread(SceSize args, void *argp)
{
    (void)args; (void)argp;
    while (g_midi_run) {
        if (g_tsf && g_midi_service && g_midi_tps > 0 && RING_FRAMES - (int)(g_wr - g_rd) >= 256) {
            sceKernelLockLwMutex(&g_mmutex, 1, NULL);
            if (g_tsf && g_midi_service) {
                // render at half the mix rate and double the samples
                short half[128 * 2];
                short *dst = g_ring + (g_wr % RING_FRAMES) * 2;
                int k;
                g_midi_acc += 128 * g_midi_tps / (g_mixrate / 2);
                while (g_midi_acc >= 1.0) {
                    g_midi_acc -= 1.0;
                    g_midi_service();
                }
                tsf_render_short(g_tsf, half, 128, 0);
                for (k = 0; k < 128; ++k) {
                    int nl = k < 127 ? half[k * 2 + 2] : half[k * 2];
                    int nr = k < 127 ? half[k * 2 + 3] : half[k * 2 + 1];
                    dst[k * 4] = half[k * 2];
                    dst[k * 4 + 1] = half[k * 2 + 1];
                    dst[k * 4 + 2] = (half[k * 2] + nl) / 2;
                    dst[k * 4 + 3] = (half[k * 2 + 1] + nr) / 2;
                }
                __sync_synchronize();
                g_wr += 256;
            }
            sceKernelUnlockLwMutex(&g_mmutex, 1);
        } else {
            sceKernelDelayThread(4000);
        }
    }
    return 0;
}

static void psp_midi_mix(short *dst, int frames)
{
    int avail = (int)(g_wr - g_rd), k, c;
    if (avail > frames)
        avail = frames;
    for (k = 0; k < avail; ++k) {
        const short *src = g_ring + ((g_rd + k) % RING_FRAMES) * 2;
        for (c = 0; c < 2; ++c) {
            int v = dst[k * 2 + c] + src[c];
            dst[k * 2 + c] = v > 32767 ? 32767 : (v < -32768 ? -32768 : v);
        }
    }
    g_rd += avail;
}

#include "platform/psp_perf.h"

#if defined(__PSP__) && defined(PSP_DIAGNOSTIC_BUILD)

#include <pspctrl.h>

#include <stdio.h>
#include <string.h>

#define PSP_PERF_HISTORY 3600
#define PSP_PERF_AVERAGE_FRAMES 15

typedef struct PSPPerfSample
{
    uint16_t frame_us;
    uint16_t render_us;
    uint16_t present_us;
    uint16_t audio_us;
    uint32_t frame_number;
    uint8_t voices;
    uint8_t mix_callbacks;
    uint16_t reserved;
} PSPPerfSample;

static PSPPerfSample psp_perf_history[PSP_PERF_HISTORY];
static volatile uint32_t psp_perf_mix_total_us;
static volatile uint32_t psp_perf_mix_callbacks;
static volatile uint32_t psp_perf_voice_count;
static uint32_t psp_perf_last_mix_total_us;
static uint32_t psp_perf_last_mix_callbacks;
static uint32_t psp_perf_frame_number;
static unsigned int psp_perf_head;
static unsigned int psp_perf_count;
static unsigned int psp_perf_average_frames;
static uint32_t psp_perf_average_frame_us;
static uint32_t psp_perf_average_render_us;
static uint32_t psp_perf_average_present_us;
static uint32_t psp_perf_average_audio_us;
static uint32_t psp_perf_average_voices;
static uint32_t psp_perf_average_callbacks;
static PSPPerfSnapshot psp_perf_snapshot;
static int psp_perf_dump_latched;
static uint8_t psp_perf_dump_status;

static uint16_t psp_perf_clamp_u16(uint32_t value)
{
    return (uint16_t)(value > 65535u ? 65535u : value);
}

void psp_perf_reset(void)
{
    memset(psp_perf_history, 0, sizeof(psp_perf_history));
    psp_perf_mix_total_us = 0;
    psp_perf_mix_callbacks = 0;
    psp_perf_voice_count = 0;
    psp_perf_last_mix_total_us = 0;
    psp_perf_last_mix_callbacks = 0;
    psp_perf_frame_number = 0;
    psp_perf_head = 0;
    psp_perf_count = 0;
    psp_perf_average_frames = 0;
    psp_perf_average_frame_us = 0;
    psp_perf_average_render_us = 0;
    psp_perf_average_present_us = 0;
    psp_perf_average_audio_us = 0;
    psp_perf_average_voices = 0;
    psp_perf_average_callbacks = 0;
    memset(&psp_perf_snapshot, 0, sizeof(psp_perf_snapshot));
    psp_perf_dump_latched = 0;
    psp_perf_dump_status = 0;
}

void psp_perf_mixer_record(uint32_t mix_us)
{
    psp_perf_mix_total_us += mix_us;
    psp_perf_mix_callbacks++;
}

void psp_perf_record_frame(uint32_t frame_us, uint32_t render_us, uint32_t present_us, uint32_t voices)
{
    PSPPerfSample *sample;
    uint32_t mix_total = psp_perf_mix_total_us;
    uint32_t mix_callbacks = psp_perf_mix_callbacks;
    uint32_t audio_us = mix_total - psp_perf_last_mix_total_us;
    uint32_t callbacks = mix_callbacks - psp_perf_last_mix_callbacks;
    psp_perf_voice_count = voices;

    psp_perf_last_mix_total_us = mix_total;
    psp_perf_last_mix_callbacks = mix_callbacks;
    sample = &psp_perf_history[psp_perf_head];
    sample->frame_us = psp_perf_clamp_u16(frame_us);
    sample->render_us = psp_perf_clamp_u16(render_us);
    sample->present_us = psp_perf_clamp_u16(present_us);
    sample->audio_us = psp_perf_clamp_u16(audio_us);
    sample->frame_number = ++psp_perf_frame_number;
    sample->voices = (uint8_t)(voices > 255u ? 255u : voices);
    sample->mix_callbacks = (uint8_t)(callbacks > 255u ? 255u : callbacks);
    sample->reserved = 0;
    if (++psp_perf_head == PSP_PERF_HISTORY)
        psp_perf_head = 0;
    if (psp_perf_count < PSP_PERF_HISTORY)
        psp_perf_count++;

    psp_perf_average_frame_us += sample->frame_us;
    psp_perf_average_render_us += sample->render_us;
    psp_perf_average_present_us += sample->present_us;
    psp_perf_average_audio_us += sample->audio_us;
    psp_perf_average_voices += sample->voices;
    psp_perf_average_callbacks += sample->mix_callbacks;
    if (++psp_perf_average_frames == PSP_PERF_AVERAGE_FRAMES)
    {
        psp_perf_snapshot.frame_us = (uint16_t)(psp_perf_average_frame_us / PSP_PERF_AVERAGE_FRAMES);
        psp_perf_snapshot.render_us = (uint16_t)(psp_perf_average_render_us / PSP_PERF_AVERAGE_FRAMES);
        psp_perf_snapshot.present_us = (uint16_t)(psp_perf_average_present_us / PSP_PERF_AVERAGE_FRAMES);
        psp_perf_snapshot.audio_us = (uint16_t)(psp_perf_average_audio_us / PSP_PERF_AVERAGE_FRAMES);
        psp_perf_snapshot.voices = (uint8_t)(psp_perf_average_voices / PSP_PERF_AVERAGE_FRAMES);
        psp_perf_snapshot.mix_callbacks = (uint8_t)(psp_perf_average_callbacks / PSP_PERF_AVERAGE_FRAMES);
        psp_perf_snapshot.dump_status = psp_perf_dump_status;
        psp_perf_average_frames = 0;
        psp_perf_average_frame_us = 0;
        psp_perf_average_render_us = 0;
        psp_perf_average_present_us = 0;
        psp_perf_average_audio_us = 0;
        psp_perf_average_voices = 0;
        psp_perf_average_callbacks = 0;
    }
    if (psp_perf_dump_status)
        psp_perf_dump_status--;
}

int psp_perf_get_snapshot(PSPPerfSnapshot *snapshot)
{
    if (!snapshot || !psp_perf_count)
        return 0;
    *snapshot = psp_perf_snapshot;
    snapshot->dump_status = psp_perf_dump_status;
    return 1;
}

static void psp_perf_dump(void)
{
    FILE *file = fopen("jfblood-perf.csv", "wb");
    unsigned int start;
    unsigned int index;
    unsigned int i;

    if (!file)
        return;
    fputs("frame,frame_us,render_us,present_us,audio_us,voices,mix_callbacks\n", file);
    start = (psp_perf_head + PSP_PERF_HISTORY - psp_perf_count) % PSP_PERF_HISTORY;
    for (i = 0, index = start; i < psp_perf_count; ++i)
    {
        PSPPerfSample const *sample = &psp_perf_history[index];
        fprintf(file, "%lu,%u,%u,%u,%u,%u,%u\n", (unsigned long)sample->frame_number,
                (unsigned int)sample->frame_us, (unsigned int)sample->render_us,
                (unsigned int)sample->present_us, (unsigned int)sample->audio_us,
                (unsigned int)sample->voices, (unsigned int)sample->mix_callbacks);
        if (++index == PSP_PERF_HISTORY)
            index = 0;
    }
    fclose(file);
    psp_perf_dump_status = 120;
}

int psp_perf_consume_dump_chord(uint32_t buttons)
{
    uint32_t const chord = PSP_CTRL_LTRIGGER | PSP_CTRL_RTRIGGER | PSP_CTRL_SELECT;
    if ((buttons & chord) != chord)
    {
        psp_perf_dump_latched = 0;
        return 0;
    }
    if (!psp_perf_dump_latched)
    {
        psp_perf_dump();
        psp_perf_dump_latched = 1;
    }
    return 1;
}

#endif

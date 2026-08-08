#ifndef JFBLOOD_PSP_PERF_H
#define JFBLOOD_PSP_PERF_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct PSPPerfSnapshot
{
    uint16_t frame_us;
    uint16_t render_us;
    uint16_t present_us;
    uint16_t audio_us;
    uint8_t voices;
    uint8_t mix_callbacks;
    uint8_t dump_status;
    uint8_t reserved;
} PSPPerfSnapshot;

#if defined(__PSP__) && defined(PSP_DIAGNOSTIC_BUILD)
extern uint32_t psp_present_us;
void psp_perf_reset(void);
void psp_perf_mixer_record(uint32_t mix_us);
void psp_perf_record_frame(uint32_t frame_us, uint32_t render_us, uint32_t present_us, uint32_t voices);
int psp_perf_get_snapshot(PSPPerfSnapshot *snapshot);
int psp_perf_consume_dump_chord(uint32_t buttons);
#else
static inline void psp_perf_reset(void) {}
static inline void psp_perf_mixer_record(uint32_t mix_us) { (void)mix_us; }
static inline void psp_perf_record_frame(uint32_t frame_us, uint32_t render_us, uint32_t present_us, uint32_t voices) { (void)frame_us; (void)render_us; (void)present_us; (void)voices; }
static inline int psp_perf_get_snapshot(PSPPerfSnapshot *snapshot) { (void)snapshot; return 0; }
static inline int psp_perf_consume_dump_chord(uint32_t buttons) { (void)buttons; return 0; }
#endif

#ifdef __cplusplus
}
#endif

#endif

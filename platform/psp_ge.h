#ifndef JFBLOOD_PSP_GE_H
#define JFBLOOD_PSP_GE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * First GE backend stage: present the indexed BUILD framebuffer as a T8
 * texture with a hardware CLUT. World geometry still comes from the
 * classic renderer, but scaling and palette expansion are performed by the
 * Graphics Engine in VRAM.
 */
int psp_ge_init(void);
void psp_ge_shutdown(void);
int psp_ge_active(void);
int psp_ge_present(const uint8_t *pixels, int width, int height,
                   const uint16_t *palette565);

#ifdef __cplusplus
}
#endif

#endif

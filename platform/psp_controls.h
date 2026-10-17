#ifndef BLOODPSP_CONTROLS_H
#define BLOODPSP_CONTROLS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PSP_CONTROLS_MAX_BINDINGS 64
#define PSP_CONTROLS_MAX_ACTIONS 63

extern const char psp_controls_capability[];
void psp_controls_reset(void);
void psp_controls_begin(void);
int psp_controls_enabled(void);
int psp_controls_scan(int action);
uint32_t psp_controls_parse_buttons(const char *text);
int psp_controls_add(uint32_t buttons, int action);
void psp_controls_evaluate(uint32_t buttons, unsigned char actions[PSP_CONTROLS_MAX_ACTIONS]);

#ifdef __cplusplus
}
#endif
#endif

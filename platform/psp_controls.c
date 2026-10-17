/* Native PSP mappings from [PSP Controls] in NBLOOD.CFG. */
#include "psp_controls.h"
#include <ctype.h>
#include <string.h>

/* Kept in the EBOOT so the launcher can detect this capability. */
const char psp_controls_capability[] = "BloodPSP.Controls.v1";

typedef struct { uint32_t buttons; int action; } PspMapping;
static PspMapping mappings[PSP_CONTROLS_MAX_BINDINGS];
static int mapping_count, enabled;

void psp_controls_reset(void) { mapping_count = 0; enabled = 0; }
void psp_controls_begin(void) { mapping_count = 0; enabled = 1; }
int psp_controls_enabled(void) { return enabled; }
int psp_controls_scan(int action)
{
    /* Unused scan ranges: skip keypad Enter, right Ctrl, keypad Slash,
       Print Screen, right Alt and every navigation/menu key. */
    return action < 28 ? 0x80 + action : action < 51 ? 0x9e + action - 28 : 0xb9 + action - 51;
}

uint32_t psp_controls_parse_buttons(const char *text)
{
    /* PSP_CTRL values; kept portable so the matcher can be tested on a host. */
    static const struct { const char *name; uint32_t mask; } buttons[] = {
        {"select", 0x000001}, {"up", 0x000010}, {"right", 0x000020},
        {"down", 0x000040}, {"left", 0x000080}, {"l", 0x000100},
        {"r", 0x000200}, {"triangle", 0x001000}, {"circle", 0x002000},
        {"cross", 0x004000}, {"square", 0x008000}
    };
    uint32_t result = 0;
    if (!text || !*text) return 0;
    while (*text)
    {
        char token[16];
        int n = 0, found = 0;
        while (*text && *text != '+')
        {
            if (n >= (int)sizeof(token) - 1) return 0;
            token[n++] = (char)tolower((unsigned char)*text++);
        }
        token[n] = 0;
        for (unsigned int i = 0; i < sizeof(buttons) / sizeof(buttons[0]); ++i)
            if (!strcmp(token, buttons[i].name))
            {
                if (result & buttons[i].mask) return 0;
                result |= buttons[i].mask;
                found = 1;
                break;
            }
        if (!found) return 0;
        if (*text == '+' && !*++text) return 0;
    }
    return result;
}

int psp_controls_add(uint32_t buttons, int action)
{
    const uint32_t allowed = 0xf3f1; /* No Start, HOME, volume or analog axes. */
    if (!enabled || !buttons || (buttons & ~allowed) || action < 0 ||
        action >= PSP_CONTROLS_MAX_ACTIONS || mapping_count >= PSP_CONTROLS_MAX_BINDINGS)
        return 0;
    for (int i = 0; i < mapping_count; ++i)
        if (mappings[i].buttons == buttons) return 0;
    mappings[mapping_count].buttons = buttons;
    mappings[mapping_count++].action = action;
    return 1;
}

void psp_controls_evaluate(uint32_t buttons, unsigned char actions[PSP_CONTROLS_MAX_ACTIONS])
{
    memset(actions, 0, PSP_CONTROLS_MAX_ACTIONS);
    if (!enabled) return;
    for (int i = 0; i < mapping_count; ++i)
    {
        uint32_t mask = mappings[i].buttons;
        int suppressed = 0;
        if ((buttons & mask) != mask) continue;
        /* A held combination replaces its constituent single-button bindings.
           Independent buttons and overlapping, non-subset combinations remain. */
        for (int j = 0; j < mapping_count; ++j)
            if (mask != mappings[j].buttons && (mask & mappings[j].buttons) == mask &&
                (buttons & mappings[j].buttons) == mappings[j].buttons)
            {
                suppressed = 1;
                break;
            }
        if (!suppressed) actions[mappings[i].action] = 1;
    }
}

// PSP interface layer for the JFBuild backport used by JFBlood.
// MVP: software renderer, indexed 320x200 surface, no audio.

#include <pspkernel.h>
#include <pspctrl.h>
#include <pspdisplay.h>
#include <pspge.h>
#include <psprtc.h>

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "build.h"
#include "baselayer.h"
#include "compat.h"

// jfmact/keyboard.h needs internal typedefs not exposed to this C platform
// layer.  These are the stable PC scan codes used by the Blood defaults.
enum {
    PSP_SC_ESCAPE = 0x01,
    PSP_SC_W = 0x11,
    PSP_SC_S = 0x1f,
    PSP_SC_E = 0x12,
    PSP_SC_RETURN = 0x1c,
    PSP_SC_LEFTCTRL = 0x1d,
    PSP_SC_LEFTALT = 0x38,
    PSP_SC_LEFTSHIFT = 0x2a,
    PSP_SC_UP = 0xc8,
    PSP_SC_DOWN = 0xd0,
    PSP_SC_LEFT = 0xcb,
    PSP_SC_RIGHT = 0xcd,
};

extern int g_useCwd;

PSP_MODULE_INFO("JFBlood PSP", PSP_MODULE_USER, 1, 0);
PSP_MAIN_THREAD_ATTR(PSP_THREAD_ATTR_USER | PSP_THREAD_ATTR_VFPU);

int _buildargc = 0;
const char **_buildargv = NULL;
char quitevent = 0, appactive = 1;
int xres = -1, yres = -1, bpp = 0, fullscreen = 1, bytesperline = 0, imageSize = 0;
char offscreenrendering = 0;
intptr_t frameplace = 0;
char modechange = 1;
char videomodereset = 0;

int inputdevices = 0;
char keystatus[256];
int keyfifo[KEYFIFOSIZ];
unsigned char keyasciififo[KEYFIFOSIZ];
int keyfifoplc = 0, keyfifoend = 0, keyasciififoplc = 0, keyasciififoend = 0;
int mousex = 0, mousey = 0, mouseb = 0;
int joyaxis[4], joyb = 0;
char joynumaxes = 0, joynumbuttons = 0;

// Keep the indexed game surface out of the fragmented runtime heap.  The
// JFBuild cache is allocated before video setup and is intentionally large.
static uint8_t framebuffer_storage[320 * 200];
static uint8_t *framebuffer;
static uint16_t palette565[256];
static uint32_t *vram;
static int drawbuffer;
static FILE *psp_log;
static int psp_log_enabled = 1;
static uint64_t timerlastsample;
static int timerfreq, timerticspersec;
static void (*usertimercallback)(void);
static void (*keypresscallback)(int, int);
static void (*mousepresscallback)(int, int);
static void (*joypresscallback)(int, int);

#define PSP_FB_STRIDE 512
#define PSP_FB_HEIGHT 272
#define PSP_FB_SIZE (PSP_FB_STRIDE * PSP_FB_HEIGHT * 2)

static uint64_t psp_ticks(void)
{
    uint64_t ticks = 0;
    sceRtcGetCurrentTick(&ticks);
    return ticks;
}

static void shutdownvideo(void)
{
    framebuffer = NULL;
    frameplace = 0;
}

static void psp_read_options(void)
{
    FILE *cfg = fopen("nblood.cfg", "rt");
    char line[128];
    int enabled;

    if (!cfg)
        return;
    while (fgets(line, sizeof(line), cfg))
    {
        if (sscanf(line, " PSPLog = %d", &enabled) == 1 ||
            sscanf(line, "PSPLog=%d", &enabled) == 1)
        {
            psp_log_enabled = enabled != 0;
            break;
        }
    }
    fclose(cfg);
}

int initsystem(void)
{
    // The game data and configuration belong beside EBOOT.PBP.  This avoids
    // the desktop-oriented HOME/.config relocation in the shared game code.
    g_useCwd = 1;
    psp_read_options();
    if (psp_log_enabled && !psp_log)
    {
        psp_log = fopen("jfblood.log", "w");
        if (psp_log) { fputs("JFBlood PSP startup\n", psp_log); fflush(psp_log); }
    }
    sceCtrlSetSamplingCycle(0);
    sceCtrlSetSamplingMode(PSP_CTRL_MODE_ANALOG);
    sceDisplaySetMode(0, 480, 272);
    vram = (uint32_t *)sceGeEdramGetAddr();
    drawbuffer = 0;
    sceDisplaySetFrameBuf(vram, PSP_FB_STRIDE, PSP_DISPLAY_PIXEL_FORMAT_565,
                          PSP_DISPLAY_SETBUF_IMMEDIATE);
    return 0;
}

int main(int argc, char *argv[])
{
    int result;
    _buildargc = argc;
    _buildargv = (const char **)argv;
    if (initsystem() != 0) return 1;
    baselayer_init();
    result = app_main(_buildargc, (char const * const *)_buildargv);
    uninitsystem();
    return result;
}

void uninitsystem(void)
{
    uninitinput();
    uninittimer();
    shutdownvideo();
    if (psp_log) { fclose(psp_log); psp_log = NULL; }
}

void initputs(const char *str)
{
    fputs(str, stderr);
    if (psp_log) { fputs(str, psp_log); fflush(psp_log); }
}
void debugprintf(const char *fmt, ...)
{
    va_list va;
    va_start(va, fmt);
    vfprintf(stderr, fmt, va);
    va_end(va);

    if (psp_log)
    {
        va_start(va, fmt);
        vfprintf(psp_log, fmt, va);
        va_end(va);
        fflush(psp_log);
    }
}

int initinput(void)
{
    inputdevices = 4;
    joynumaxes = 2;
    joynumbuttons = 16;
    return 0;
}
void uninitinput(void) { releaseallbuttons(); }
void releaseallbuttons(void) { joyb = 0; memset(keystatus, 0, sizeof(keystatus)); }
void setkeypresscallback(void (*callback)(int, int)) { keypresscallback = callback; }
void setmousepresscallback(void (*callback)(int, int)) { mousepresscallback = callback; }
void setjoypresscallback(void (*callback)(int, int)) { joypresscallback = callback; }
const char *getkeyname(int UNUSED(num)) { return NULL; }
const char *getjoyname(int what, int num)
{
    static const char *const names[] = { "Cross", "Circle", "Square", "Triangle", "L", "R", "Start", "Select", "Up", "Down", "Left", "Right", "Home", "Hold", "Vol+", "Vol-" };
    static char axisname[16];
    if (what == 0 && num >= 0 && num < joynumaxes) { snprintf(axisname, sizeof(axisname), "Axis %d", num); return axisname; }
    if (what == 1 && num >= 0 && num < joynumbuttons) return names[num];
    return NULL;
}
unsigned char bgetchar(void) { return 0; }
int bkbhit(void) { return 0; }
void bflushchars(void) {}
int initmouse(void) { return 0; }
void uninitmouse(void) {}
void grabmouse(int UNUSED(a)) {}
void readmousexy(int *x, int *y) { *x = mousex; *y = mousey; mousex = mousey = 0; }
void readmousebstatus(int *b) { *b = mouseb; }

int inittimer(int tickspersecond)
{
    if (timerfreq) return 0;
    timerfreq = 1000000;
    timerticspersec = tickspersecond;
    timerlastsample = psp_ticks() * (uint64_t)tickspersecond / timerfreq;
    totalclock = 0;
    usertimercallback = NULL;
    return 0;
}
void uninittimer(void) { timerfreq = 0; }
void sampletimer(void)
{
    uint64_t now;
    int elapsed;
    if (!timerfreq) return;
    now = psp_ticks() * (uint64_t)timerticspersec / timerfreq;
    elapsed = (int)(now - timerlastsample);
    if (elapsed <= 0) return;
    totalclock += elapsed;
    timerlastsample += elapsed;
    while (elapsed-- && usertimercallback) usertimercallback();
}
unsigned int getticks(void) { return (unsigned int)(psp_ticks() / 1000); }
unsigned int getusecticks(void) { return (unsigned int)psp_ticks(); }
int gettimerfreq(void) { return timerfreq; }
void (*installusertimercallback(void (*callback)(void)))(void)
{
    void (*oldcallback)(void) = usertimercallback;
    usertimercallback = callback;
    return oldcallback;
}

static int modeschecked;
#define ADDMODE(w,h,c,f) do { validmode[validmodecnt].xdim = (w); validmode[validmodecnt].ydim = (h); validmode[validmodecnt].bpp = (c); validmode[validmodecnt].fs = (f); validmode[validmodecnt++].extra = -1; } while (0)
void getvalidmodes(void)
{
    if (modeschecked) return;
    validmodecnt = 0;
    ADDMODE(320, 200, 8, 1);
    modeschecked = 1;
}
int checkvideomode(int *x, int *y, int c, int fs, int UNUSED(forced))
{
    getvalidmodes();
    // JFBuild's fallback probes a windowed mode.  PSP only has the display
    // framebuffer, so accept either request and expose the same 320x200
    // indexed surface in both cases.
    if (c != 8) return -1;
    *x = 320; *y = 200;
    return 0;
}
int setvideomode(int x, int y, int c, int fs)
{
    if (checkvideomode(&x, &y, c, fs, 1) < 0) return -1;
    shutdownvideo();
    framebuffer = framebuffer_storage;
    memset(framebuffer, 0, sizeof(framebuffer_storage));
    xres = x; yres = y; bpp = c; fullscreen = 1;
    bytesperline = x; imageSize = x * y; numpages = 1;
    modechange = 1;
    videomodereset = 0;
    return 0;
}
void resetvideomode(void) { videomodereset = 1; modeschecked = 0; }
void begindrawing(void) { if (!offscreenrendering) { frameplace = (intptr_t)framebuffer; modechange = 0; } }
void enddrawing(void) {}
void showframe(void)
{
    uint16_t *dst;
    int x, y;
    if (offscreenrendering || !framebuffer || !vram) return;
    drawbuffer ^= 1;
    dst = (uint16_t *)((uint8_t *)vram + drawbuffer * PSP_FB_SIZE);
    // The renderer remains 320x200 (fast and faithful to classic BUILD),
    // while the presentation pass fills the 480x272 LCD.  Nearest-neighbour
    // scaling keeps the original indexed pixels crisp and has no extra cache
    // allocation.
    for (y = 0; y < PSP_FB_HEIGHT; ++y)
    {
        int sy = (y * yres) / PSP_FB_HEIGHT;
        uint8_t *src = framebuffer + sy * xres;
        uint16_t *row = dst + y * PSP_FB_STRIDE;
        for (x = 0; x < 480; ++x)
            row[x] = palette565[src[(x * xres) / 480]];
    }
    sceDisplayWaitVblankStart();
    sceDisplaySetFrameBuf(dst, PSP_FB_STRIDE, PSP_DISPLAY_PIXEL_FORMAT_565, PSP_DISPLAY_SETBUF_NEXTFRAME);
}
int setpalette(int UNUSED(start), int UNUSED(num), unsigned char * UNUSED(dapal))
{
    int i;
    for (i = 0; i < 256; ++i) {
        // PSP_DISPLAY_PIXEL_FORMAT_565 stores red in the low five bits and
        // blue in the high five bits (the reverse of conventional RGB565).
        palette565[i] = (uint16_t)((curpalettefaded[i].r >> 3) |
                                   ((curpalettefaded[i].g & 0xfc) << 3) |
                                   ((curpalettefaded[i].b & 0xf8) << 8));
    }
    return 0;
}
int setgamma(float UNUSED(gamma)) { return 0; }

static int psp_buttons(uint32_t buttons)
{
    static const uint32_t masks[] = { PSP_CTRL_CROSS, PSP_CTRL_CIRCLE, PSP_CTRL_SQUARE, PSP_CTRL_TRIANGLE, PSP_CTRL_LTRIGGER, PSP_CTRL_RTRIGGER, PSP_CTRL_START, PSP_CTRL_SELECT, PSP_CTRL_UP, PSP_CTRL_DOWN, PSP_CTRL_LEFT, PSP_CTRL_RIGHT, PSP_CTRL_HOME, PSP_CTRL_HOLD, PSP_CTRL_VOLUP, PSP_CTRL_VOLDOWN };
    int i, result = 0;
    for (i = 0; i < 16; ++i) if (buttons & masks[i]) result |= 1 << i;
    return result;
}

// The JFMact joystick binding table is useful for configuration, but its
// historical polling path is not reliable on the PSP backend yet.  Mirror
// the handheld controls into the established keyboard path as well.  This
// makes the in-game menus and the original Blood movement bindings work
// without changing the user's cfg file.
static void psp_set_key(int scan, int down)
{
    if (keystatus[scan] == down)
        return;
    keystatus[scan] = down;
    if (keypresscallback)
        keypresscallback(scan, down);
}

static void psp_apply_keyboard_controls(uint32_t buttons)
{
    int up = !!(buttons & PSP_CTRL_UP);
    int down = !!(buttons & PSP_CTRL_DOWN);
    int left = !!(buttons & PSP_CTRL_LEFT);
    int right = !!(buttons & PSP_CTRL_RIGHT);

    psp_set_key(PSP_SC_W, up);
    psp_set_key(PSP_SC_UP, up);
    psp_set_key(PSP_SC_S, down);
    psp_set_key(PSP_SC_DOWN, down);
    psp_set_key(PSP_SC_LEFT, left);
    psp_set_key(PSP_SC_RIGHT, right);

    psp_set_key(PSP_SC_LEFTCTRL, !!(buttons & PSP_CTRL_CROSS));
    psp_set_key(PSP_SC_RETURN, !!(buttons & PSP_CTRL_CROSS));
    psp_set_key(PSP_SC_LEFTALT, !!(buttons & PSP_CTRL_CIRCLE));
    psp_set_key(PSP_SC_LEFTSHIFT, !!(buttons & PSP_CTRL_SQUARE));
    psp_set_key(PSP_SC_E, !!(buttons & PSP_CTRL_TRIANGLE));
    psp_set_key(PSP_SC_ESCAPE, !!(buttons & PSP_CTRL_START));
}

int handleevents(void)
{
    SceCtrlData pad;
    int buttons, changed, i;
    sceCtrlReadBufferPositive(&pad, 1);
    buttons = psp_buttons(pad.Buttons);
    changed = buttons ^ joyb;
    if (changed)
        debugprintf("PSP input: raw=%08x mapped=%08x changed=%08x\n",
                    (unsigned int)pad.Buttons, (unsigned int)buttons, (unsigned int)changed);
    for (i = 0; i < 16; ++i)
        if ((changed & (1 << i)) && joypresscallback) joypresscallback(i, !!(buttons & (1 << i)));
    psp_apply_keyboard_controls(pad.Buttons);
    joyb = buttons;
    joyaxis[0] = ((int)pad.Lx - 128) * 256;
    joyaxis[1] = ((int)pad.Ly - 128) * 256;
    // Do not consume HOME: firmware/PPSSPP owns it for the XMB system menu.
    sampletimer();
    return quitevent;
}

int wm_msgbox(const char *UNUSED(name), const char *fmt, ...) { va_list va; va_start(va, fmt); vfprintf(stderr, fmt, va); va_end(va); return 0; }
int wm_ynbox(const char *UNUSED(name), const char *UNUSED(fmt), ...) { return 1; }
int wm_filechooser(const char *UNUSED(initialdir), const char *UNUSED(initialfile), const char *UNUSED(type), int UNUSED(foropen), char **UNUSED(choice)) { return -1; }
int wm_idle(void *UNUSED(data)) { return 0; }
void wm_setapptitle(const char *UNUSED(name)) {}
void wm_setwindowtitle(const char *UNUSED(name)) {}

// The PSP MVP has no native startup dialog. The game begins immediately and
// its regular in-game menus remain available.
int startwin_open(void) { return 0; }
int startwin_close(void) { return 0; }
int startwin_puts(const char *UNUSED(msg)) { return 0; }
int startwin_settitle(const char *UNUSED(title)) { return 0; }
int startwin_idle(void *UNUSED(data)) { return 0; }
int startwin_run(struct startwin_settings *UNUSED(settings)) { return STARTWIN_RUN; }

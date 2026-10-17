// PSP interface layer for the JFBuild backport used by JFBlood.
// Native indexed software renderer and PSP input backend.
// Strafe controls and analog dead zone contributed by wa59.

#include <pspkernel.h>
#include <pspctrl.h>
#include <pspdisplay.h>
#include <pspge.h>
#include <psppower.h>
#include <psprtc.h>
#include <pspsdk.h>

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "build.h"
#include "baselayer.h"
#include "compat.h"
#include "platform/psp_ge.h"
#include "platform/psp_ge_world.h"
#include "platform/psp_paths.h"
#include "platform/psp_controls.h"

// jfmact/keyboard.h needs internal typedefs not exposed to this C platform
// layer.  These are the stable PC scan codes used by the Blood defaults.
enum {
    PSP_SC_ESCAPE = 0x01,
    PSP_SC_TAB = 0x0f,
    PSP_SC_W = 0x11,
    PSP_SC_RIGHT_BRACKET = 0x1b,
    PSP_SC_E = 0x12,
    PSP_SC_A = 0x1e,
    PSP_SC_D = 0x20,
    PSP_SC_ENTER = 0x1c,
    PSP_SC_LEFTCTRL = 0x1d,
    PSP_SC_LEFTALT = 0x38,
    PSP_SC_SPACE = 0x39,
    PSP_SC_X = 0x2d,
    PSP_SC_RIGHTCTRL = 0x9d,
    PSP_SC_SEMICOLON = 0x27,
    PSP_SC_APOSTROPHE = 0x28,
};

extern int g_useCwd;

PSP_MODULE_INFO("JFBlood PSP", PSP_MODULE_USER, 1, 0);
PSP_MAIN_THREAD_ATTR(PSP_THREAD_ATTR_USER | PSP_THREAD_ATTR_VFPU);
PSP_HEAP_SIZE_KB(-1280);
PSP_HEAP_THRESHOLD_SIZE_KB(1280);

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
static uint8_t framebuffer_storage[480 * 272];
static uint8_t *framebuffer;
static uint16_t palette565[256];
static uint16_t display_buffers[2][512 * 272] __attribute__((aligned(64)));
static int drawbuffer;
static FILE *psp_log;
/* Diagnostics use RAM telemetry by default; file logging is opt-in. */
static int psp_log_enabled = 0;
static int psp_ge_enabled;
#if defined(PSP_DIAGNOSTIC_BUILD)
int psp_perf_hud = 1;

unsigned int psp_present_us;
#endif

static uint64_t timerlastsample;
static int timerfreq, timerticspersec;
static void (*usertimercallback)(void);
static void (*keypresscallback)(int, int);
static void (*mousepresscallback)(int, int);
static void (*joypresscallback)(int, int);


#define PSP_FB_WIDTH 480
#define PSP_FB_STRIDE 512
#define PSP_FB_HEIGHT 272
#define PSP_FB_SIZE (PSP_FB_STRIDE * PSP_FB_HEIGHT * 2)

static uint16_t psp_scale_x[PSP_FB_WIDTH];
static uint16_t psp_scale_y[PSP_FB_HEIGHT];

static uint64_t psp_ticks(void)
{
    uint64_t ticks = 0;
    sceRtcGetCurrentTick(&ticks);
    return ticks;
}

// The VSH quit request is delivered asynchronously. A callback thread that
// sleeps with the CB variant is required for the HOME/XMB flow on real PSPs.
static int psp_exit_callback(int arg1, int arg2, void *common)
{
    (void)arg1;
    (void)arg2;
    (void)common;
    sceKernelExitGame();
    return 0;
}

static int psp_callback_thread(SceSize args, void *argp)
{
    SceUID callback;
    (void)args;
    (void)argp;

    callback = sceKernelCreateCallback("Exit Callback", psp_exit_callback, NULL);
    if (callback >= 0)
    {
        sceKernelRegisterExitCallback(callback);
        sceKernelSleepThreadCB();
    }
    return 0;
}

static void psp_setup_callbacks(void)
{
    SceUID thread = sceKernelCreateThread("Exit Callback Thread", psp_callback_thread,
                                          0x11, 0x1000, PSP_THREAD_ATTR_USER, NULL);
    if (thread >= 0)
        sceKernelStartThread(thread, 0, NULL);
}

static void shutdownvideo(void)
{
    psp_ge_shutdown();
    framebuffer = NULL;
    frameplace = 0;
}

static void psp_read_options(void)
{
    FILE *cfg = fopen("nblood.cfg", "rt");
    char line[128];
    int enabled;
    char renderer[16];

    if (!cfg)
        return;
    while (fgets(line, sizeof(line), cfg))
    {
        if (sscanf(line, " PSPLog = %d", &enabled) == 1 ||
            sscanf(line, "PSPLog=%d", &enabled) == 1)
        {
            psp_log_enabled = enabled != 0;
        }
        else if (sscanf(line, " PSPRenderer = %15s", renderer) == 1 ||
                 sscanf(line, "PSPRenderer=%15s", renderer) == 1)
        {
            if (strcmp(renderer, "GE") == 0)
            {
                psp_ge_enabled = 1;
                psp_ge_world_set_enabled(1);
                psp_ge_world_set_textures_enabled(1);
                psp_ge_world_set_replace_walls(0);
                psp_ge_world_set_sector3d_enabled(1);
                /* Native 3D stays opt-in for diagnostics; the hybrid path uses
                   validated projected GE geometry. */
                psp_ge_world_set_sector3d_native_enabled(0);
                psp_ge_world_set_replace_opaque_enabled(1);
            }
            else if (strcmp(renderer, "GEWalls") == 0)
            {
                /* Transitional renderer: BUILD keeps portal traversal and all
                   non-wall rendering; GE rasterizes only opaque wall spans. */
                psp_ge_enabled = 1;
                psp_ge_world_set_enabled(1);
                psp_ge_world_set_textures_enabled(1);
                psp_ge_world_set_replace_walls(1);
                psp_ge_world_set_sector3d_enabled(0);
                psp_ge_world_set_sector3d_native_enabled(0);
                psp_ge_world_set_replace_opaque_enabled(0);
            }
            else if (strcmp(renderer, "Software") == 0)
            {
                psp_ge_world_set_replace_opaque_enabled(0);
                psp_ge_world_set_replace_walls(0);
                psp_ge_world_set_enabled(0);
                psp_ge_enabled = 0;
            }
        }
#if defined(PSP_DIAGNOSTIC_BUILD)
        else if (sscanf(line, " PSPPerfHUD = %d", &enabled) == 1 ||
                 sscanf(line, "PSPPerfHUD=%d", &enabled) == 1)
        {
            psp_perf_hud = enabled != 0;
        }
#endif
        else if (sscanf(line, " PSPGE = %d", &enabled) == 1 ||
                 sscanf(line, "PSPGE=%d", &enabled) == 1)
        {
            psp_ge_enabled = enabled != 0;
        }
        else if (sscanf(line, " PSPGEWorld = %d", &enabled) == 1 ||
                 sscanf(line, "PSPGEWorld=%d", &enabled) == 1)
        {
            psp_ge_world_set_enabled(enabled);
        }
        else if (sscanf(line, " PSPGEWorldTextures = %d", &enabled) == 1 ||
                 sscanf(line, "PSPGEWorldTextures=%d", &enabled) == 1)
        {
            psp_ge_world_set_textures_enabled(enabled);
        }
        else if (sscanf(line, " PSPGEWorldReplaceWalls = %d", &enabled) == 1 ||
                 sscanf(line, "PSPGEWorldReplaceWalls=%d", &enabled) == 1)
        {
            psp_ge_world_set_replace_walls(enabled);
        }
        else if (sscanf(line, " PSPGEWorldPlanes = %d", &enabled) == 1 ||
                 sscanf(line, "PSPGEWorldPlanes=%d", &enabled) == 1)
        {
            psp_ge_world_set_planes_enabled(enabled);
        }
        else if (sscanf(line, " PSPGEWorldPlanesFill = %d", &enabled) == 1 ||
                 sscanf(line, "PSPGEWorldPlanesFill=%d", &enabled) == 1)
        {
            psp_ge_world_set_planes_fill_enabled(enabled);
        }
        else if (sscanf(line, " PSPGEWorldSector3D = %d", &enabled) == 1 ||
                 sscanf(line, "PSPGEWorldSector3D=%d", &enabled) == 1)
        {
            psp_ge_world_set_sector3d_enabled(enabled);
        }
        else if (sscanf(line, " PSPGEWorldSector3DNative = %d", &enabled) == 1 ||
                 sscanf(line, "PSPGEWorldSector3DNative=%d", &enabled) == 1)
        {
            psp_ge_world_set_sector3d_native_enabled(enabled);
        }
    }
    fclose(cfg);
}
int initsystem(void)
{
    // The game data and configuration belong beside EBOOT.PBP.  This avoids
    // the desktop-oriented HOME/.config relocation in the shared game code.
    g_useCwd = 1;
    // Keep custom maps beside the EBOOT, separate from the base game data.
    // An existing folder is fine; the file picker can fall back if unwritable.
    (void)mkdir(PSP_USERMAP_DIR, 0777);
#if defined(PSP_RELEASE_BUILD)
    // A release must not open, create, or update a diagnostic file.
    psp_read_options();
    psp_log_enabled = 0;
#else
    // Performance diagnostics default to RAM-only telemetry. The older
    // file logger can be explicitly enabled with PSPLog=1 in nblood.cfg.
    psp_log_enabled = 0;
    psp_read_options();
#endif
#if defined(PSP_GE_NATIVE_PROBE_BUILD)
    /* Self-contained GE diagnostic: do not depend on a user cfg entry. */
    psp_ge_enabled = 1;
    psp_ge_world_set_enabled(1);
    psp_ge_world_set_textures_enabled(1);
    psp_ge_world_set_sector3d_enabled(1);
    psp_ge_world_set_sector3d_native_enabled(1);
    psp_ge_world_set_replace_opaque_enabled(1);
#endif
#if defined(PSP_STABLE_PERFORMANCE_BUILD)
    /* A release safety profile: configuration experiments must never select
       a partially migrated GE path for the stable gameplay EBOOT. */
    psp_ge_world_set_replace_opaque_enabled(0);
    psp_ge_world_set_replace_walls(0);
    psp_ge_world_set_sector3d_enabled(0);
    psp_ge_world_set_enabled(0);
    psp_ge_enabled = 0;
#endif
    if (psp_log_enabled && !psp_log)
    {
        psp_log = fopen("jfblood.log", "w");
        if (psp_log) { fputs("JFBlood PSP startup\n", psp_log); fflush(psp_log); }
    }
    sceCtrlSetSamplingCycle(0);
    sceCtrlSetSamplingMode(PSP_CTRL_MODE_ANALOG);
    scePowerSetClockFrequency(333, 333, 166);
    sceDisplaySetMode(0, PSP_FB_WIDTH, PSP_FB_HEIGHT);
    for (int i = 0; i < PSP_FB_WIDTH; ++i)
        psp_scale_x[i] = (uint16_t)((i * 320) / PSP_FB_WIDTH);
    for (int i = 0; i < PSP_FB_HEIGHT; ++i)
        psp_scale_y[i] = (uint16_t)((i * 200) / PSP_FB_HEIGHT);
    drawbuffer = 0;
    sceDisplaySetFrameBuf(display_buffers[drawbuffer], PSP_FB_STRIDE, PSP_DISPLAY_PIXEL_FORMAT_565,
                          PSP_DISPLAY_SETBUF_IMMEDIATE);
    return 0;
}

int main(int argc, char *argv[])
{
    int result;

    // Match established PSP ports: do not let an IEEE-754 status flag turn
    // into an unhandled hardware exception in the main game thread.
    pspSdkDisableFPUExceptions();
    psp_setup_callbacks();

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
#if defined(PSP_RELEASE_BUILD)
    (void)str;
#else
    fputs(str, stderr);
    if (psp_log) { fputs(str, psp_log); fflush(psp_log); }
#endif
}
void debugprintf(const char *fmt, ...)
{
#if defined(PSP_RELEASE_BUILD)
    (void)fmt;
#else
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
#endif
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
    ADDMODE(PSP_FB_WIDTH, PSP_FB_HEIGHT, 8, 1);
    modeschecked = 1;
}
int checkvideomode(int *x, int *y, int c, int fs, int UNUSED(forced))
{
    getvalidmodes();
    // PSP always presents at 480x272, but classic BUILD can render either
    // directly at that size or at 320x200 and use the fast indexed scaler.
    (void)fs;
    if (c != 8) return -1;
    if ((*x == 320 && *y == 200) || (*x == PSP_FB_WIDTH && *y == PSP_FB_HEIGHT))
        return 0;
    return -1;
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
#if defined(PSP_DIAGNOSTIC_BUILD)
    uint64_t const presentStart = psp_ticks();
#endif

    if (offscreenrendering || !framebuffer) return;

    if (psp_ge_enabled && !psp_ge_active())
        psp_ge_enabled = psp_ge_init();
    if (psp_ge_enabled && psp_ge_active())
    {
        if (psp_ge_present(framebuffer, xres, yres, palette565))
        {
#if defined(PSP_DIAGNOSTIC_BUILD)
            psp_present_us = (unsigned int)(psp_ticks() - presentStart);
#endif
            return;
        }

        // A failed GE frame must never make the game unplayable.
        psp_ge_shutdown();
        psp_ge_enabled = 0;
    }

    drawbuffer ^= 1;
    dst = display_buffers[drawbuffer];

    if (xres == PSP_FB_WIDTH && yres == PSP_FB_HEIGHT)
    {
        // Native PSP mode: indexed renderer at 480x272, then RGB565 conversion.
        for (int y = 0; y < PSP_FB_HEIGHT; ++y)
        {
            const uint8_t *src = framebuffer + y * PSP_FB_WIDTH;
            uint16_t *row = dst + y * PSP_FB_STRIDE;
            for (int x = 0; x < PSP_FB_WIDTH; ++x)
                row[x] = palette565[src[x]];
        }
    }
    else
    {
        // Performance mode: classic 320x200 renderer scaled to the PSP LCD.
        for (int y = 0; y < PSP_FB_HEIGHT; ++y)
        {
            const uint8_t *src = framebuffer + psp_scale_y[y] * 320;
            uint16_t *row = dst + y * PSP_FB_STRIDE;
            for (int x = 0; x < PSP_FB_WIDTH; ++x)
                row[x] = palette565[src[psp_scale_x[x]]];
        }
    }

    sceKernelDcacheWritebackRange(dst, PSP_FB_SIZE);
#if defined(PSP_DIAGNOSTIC_BUILD)
    // This is CPU presentation work only: scaling and cache writeback. VBlank
    // pacing is intentionally excluded so the HUD identifies real hotspots.
    psp_present_us = (unsigned int)(psp_ticks() - presentStart);
#endif
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
    if (down)
    {
        keyfifo[keyfifoend] = scan;
        keyfifo[(keyfifoend + 1) & (KEYFIFOSIZ - 1)] = down;
        keyfifoend = (keyfifoend + 2) & (KEYFIFOSIZ - 1);
    }
    if (keypresscallback)
        keypresscallback(scan, down);
}

static uint32_t psp_filter_joystick_buttons(uint32_t buttons)
{
    // PSP face/trigger inputs use the keyboard path below. The JFMact
    // joystick table is retained for analogue axes only: old cfg files have
    // incompatible button entries and would otherwise inject two actions.
    (void)buttons;
    return 0;
}

#define PSP_STICK_DEADZONE 26 // 20% of the 128-step stick radius

// Zero the dead zone and rescale the rest so full deflection is unchanged.
static int psp_stick_axis(int v)
{
    int a = v < 0 ? -v : v;
    if (a <= PSP_STICK_DEADZONE) return 0;
    a = (a - PSP_STICK_DEADZONE) * 128 / (128 - PSP_STICK_DEADZONE);
    return v < 0 ? -a : a;
}

static void psp_apply_keyboard_controls(uint32_t buttons)
{
    int up = !!(buttons & PSP_CTRL_UP);
    int down = !!(buttons & PSP_CTRL_DOWN);
    int left = !!(buttons & PSP_CTRL_LEFT);
    int right = !!(buttons & PSP_CTRL_RIGHT);
    int const secondary = (buttons & (PSP_CTRL_LTRIGGER | PSP_CTRL_RTRIGGER | PSP_CTRL_CROSS)) ==
        (PSP_CTRL_LTRIGGER | PSP_CTRL_RTRIGGER | PSP_CTRL_CROSS);

    // L/R strafe left/right; face buttons shoot/use/jump/crouch; D-pad up/down next/use item, left/right previous/next weapon.
    psp_set_key(PSP_SC_A, !!(buttons & PSP_CTRL_LTRIGGER));
    psp_set_key(PSP_SC_D, !!(buttons & PSP_CTRL_RTRIGGER));
    psp_set_key(PSP_SC_RIGHTCTRL, !!(buttons & PSP_CTRL_CROSS) && !secondary);
    psp_set_key(PSP_SC_X, secondary);
    psp_set_key(PSP_SC_E, !!(buttons & PSP_CTRL_SQUARE));
    psp_set_key(PSP_SC_SPACE, !!(buttons & PSP_CTRL_TRIANGLE));
    psp_set_key(PSP_SC_ENTER, down);
    psp_set_key(PSP_SC_RIGHT_BRACKET, up);
    psp_set_key(PSP_SC_SEMICOLON, left);
    psp_set_key(PSP_SC_APOSTROPHE, right);

    psp_set_key(PSP_SC_LEFTCTRL, !!(buttons & PSP_CTRL_CIRCLE));
    psp_set_key(PSP_SC_TAB, !!(buttons & PSP_CTRL_SELECT));
    psp_set_key(PSP_SC_ESCAPE, !!(buttons & PSP_CTRL_START));
    if (psp_controls_enabled())
    {
        unsigned char actions[PSP_CONTROLS_MAX_ACTIONS];
        psp_controls_evaluate(buttons, actions);
        for (int i = 0; i < PSP_CONTROLS_MAX_ACTIONS; ++i)
            psp_set_key(psp_controls_scan(i), actions[i]);
    }
}

int handleevents(void)
{
    SceCtrlData pad;
    int buttons, changed, i;
    sceCtrlReadBufferPositive(&pad, 1);
    buttons = psp_buttons(psp_filter_joystick_buttons(pad.Buttons));
    changed = buttons ^ joyb;
#if defined(PSP_DIAGNOSTIC_BUILD)
    if (changed)
        debugprintf("PSP input: raw=%08x mapped=%08x changed=%08x\n",
                    (unsigned int)pad.Buttons, (unsigned int)buttons, (unsigned int)changed);
#endif
    for (i = 0; i < 16; ++i)
        if ((changed & (1 << i)) && joypresscallback) joypresscallback(i, !!(buttons & (1 << i)));
    psp_apply_keyboard_controls(pad.Buttons);
    joyb = buttons;
    // The PSP's single analogue nub controls turning. Keep movement at the
    // expected full range while reducing horizontal turn sensitivity by 75%.
    joyaxis[0] = psp_stick_axis((int)pad.Lx - 128) * 48;
    joyaxis[1] = psp_stick_axis((int)pad.Ly - 128) * 256;
    // Do not consume HOME: firmware/PPSSPP owns it for the XMB system menu.
    sampletimer();
    return quitevent;
}

int wm_msgbox(const char *UNUSED(name), const char *fmt, ...)
{
#if defined(PSP_RELEASE_BUILD)
    (void)fmt;
#else
    va_list va;
    va_start(va, fmt);
    vfprintf(stderr, fmt, va);
    va_end(va);
#endif
    return 0;
}
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

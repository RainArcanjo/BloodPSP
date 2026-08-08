#include "platform/psp_ge.h"
#include "platform/psp_ge_world.h"

#include <pspdisplay.h>
#include <pspgu.h>
#include <pspkernel.h>

#include <string.h>

#define PSP_GE_SCREEN_WIDTH 480
#define PSP_GE_SCREEN_HEIGHT 272
#define PSP_GE_BUFFER_WIDTH 512
#define PSP_GE_FRAME_BYTES (PSP_GE_BUFFER_WIDTH * PSP_GE_SCREEN_HEIGHT * 2)
#define PSP_GE_TEXTURE_WIDTH 512
#define PSP_GE_TEXTURE_HEIGHT 512

typedef struct PSPGEVertex
{
    float u, v;
    float x, y, z;
} PSPGEVertex;

/* The portal-scene diagnostic can submit more geometry than a full-screen
   blit. This regular-RAM command list remains small versus PSP user memory. */
static unsigned int psp_ge_list[65536] __attribute__((aligned(64)));
static unsigned char psp_ge_texture[PSP_GE_TEXTURE_WIDTH * PSP_GE_TEXTURE_HEIGHT]
    __attribute__((aligned(64)));
static unsigned short psp_ge_clut[256] __attribute__((aligned(64)));
/* RGBA4444 version used to overlay CPU sprites/HUD with index 0 transparent. */
static unsigned short psp_ge_overlay_clut[256] __attribute__((aligned(64)));
static int psp_ge_ready;

int psp_ge_active(void)
{
    return psp_ge_ready;
}

int psp_ge_init(void)
{
    if (psp_ge_ready)
        return 1;

    sceGuInit();
    sceGuStart(GU_DIRECT, psp_ge_list);
    sceGuDrawBuffer(GU_PSM_5650, (void *)0, PSP_GE_BUFFER_WIDTH);
    sceGuDispBuffer(PSP_GE_SCREEN_WIDTH, PSP_GE_SCREEN_HEIGHT,
                    (void *)PSP_GE_FRAME_BYTES, PSP_GE_BUFFER_WIDTH);
    /* The third EDRAM surface is reserved for the experimental 3D pass. */
    sceGuDepthBuffer((void *)(PSP_GE_FRAME_BYTES * 2), PSP_GE_BUFFER_WIDTH);
    sceGuDepthRange(65535, 0);
    sceGuDepthFunc(GU_GEQUAL);
    sceGuOffset(2048 - PSP_GE_SCREEN_WIDTH / 2, 2048 - PSP_GE_SCREEN_HEIGHT / 2);
    sceGuViewport(2048, 2048, PSP_GE_SCREEN_WIDTH, PSP_GE_SCREEN_HEIGHT);
    sceGuScissor(0, 0, PSP_GE_SCREEN_WIDTH, PSP_GE_SCREEN_HEIGHT);
    sceGuEnable(GU_SCISSOR_TEST);
    sceGuDisable(GU_DEPTH_TEST);
    sceGuDisable(GU_BLEND);
    sceGuEnable(GU_TEXTURE_2D);
    sceGuTexFilter(GU_NEAREST, GU_NEAREST);
    sceGuFinish();
    sceGuSync(GU_SYNC_FINISH, GU_SYNC_WHAT_DONE);
    sceDisplayWaitVblankStart();
    sceGuDisplay(GU_TRUE);

    psp_ge_ready = 1;
    return 1;
}

void psp_ge_shutdown(void)
{
    if (!psp_ge_ready)
        return;

    sceGuDisplay(GU_FALSE);
    sceGuTerm();
    psp_ge_ready = 0;
}

int psp_ge_present(const uint8_t *pixels, int width, int height,
                   const uint16_t *palette565)
{
    PSPGEVertex *vertices;

    if (!psp_ge_ready || !pixels || !palette565 || width <= 0 || height <= 0 ||
        width > PSP_GE_SCREEN_WIDTH || height > PSP_GE_SCREEN_HEIGHT)
        return 0;

    for (int y = 0; y < height; ++y)
        memcpy(psp_ge_texture + y * PSP_GE_TEXTURE_WIDTH, pixels + y * width, (size_t)width);

    memcpy(psp_ge_clut, palette565, sizeof(psp_ge_clut));
    for (int i = 0; i < 256; ++i)
    {
        unsigned int const color = palette565[i];
        unsigned int const red = (color & 0x1f) >> 1;
        unsigned int const green = (color >> 5) & 0x3f;
        unsigned int const blue = (color >> 11) & 0x1f;
        psp_ge_overlay_clut[i] = (uint16_t)((i ? 0xf000 : 0) |
                                             red | ((green >> 2) << 4) |
                                             ((blue >> 1) << 8));
    }
    sceKernelDcacheWritebackRange(psp_ge_texture,
                                  PSP_GE_TEXTURE_WIDTH * (height <= 256 ? 256 : 512));
    sceKernelDcacheWritebackRange(psp_ge_clut, sizeof(psp_ge_clut));
    sceKernelDcacheWritebackRange(psp_ge_overlay_clut, sizeof(psp_ge_overlay_clut));

    sceGuStart(GU_DIRECT, psp_ge_list);
    sceGuClearColor(0);
    /* GU_GEQUAL uses a reversed Z range. The clear value must be explicit
       or a previous GU state can reject every 3D fragment. */
    sceGuClearDepth(0);
    sceGuDepthMask(0xffff);
    sceGuDisable(GU_DEPTH_TEST);
    sceGuDisable(GU_ALPHA_TEST);
    sceGuClear(GU_COLOR_BUFFER_BIT | GU_DEPTH_BUFFER_BIT);
    sceGuTexMode(GU_PSM_T8, 0, 0, 0);
    sceGuTexImage(0, PSP_GE_TEXTURE_WIDTH,
                  height <= 256 ? 256 : PSP_GE_TEXTURE_HEIGHT,
                  PSP_GE_TEXTURE_WIDTH, psp_ge_texture);
    sceGuTexFilter(GU_NEAREST, GU_NEAREST);
    sceGuTexScale(1.f, 1.f);
    sceGuTexOffset(0.f, 0.f);
    sceGuColor(0xffffffff);

    if (psp_ge_world_replace_opaque_enabled())
    {
        psp_ge_world_render(psp_ge_clut);

        /* CPU only drew masks/sprites/HUD into this surface. Preserve the
           color key by using a zero-alpha CLUT entry for palette index 0. */
        sceGuClutMode(GU_PSM_4444, 0, 0xff, 0);
        sceGuClutLoad(256 / 8, psp_ge_overlay_clut);
        sceGuTexFunc(GU_TFX_REPLACE, GU_TCC_RGBA);
        sceGuDisable(GU_BLEND);
        sceGuEnable(GU_ALPHA_TEST);
        sceGuAlphaFunc(GU_GREATER, 0, 0xff);
        vertices = (PSPGEVertex *)sceGuGetMemory(2 * sizeof(*vertices));
        if (vertices)
        {
            vertices[0].u = 0.f;     vertices[0].v = 0.f;
            vertices[0].x = 0.f;     vertices[0].y = 0.f;     vertices[0].z = 0.f;
            vertices[1].u = width;   vertices[1].v = height;
            vertices[1].x = PSP_GE_SCREEN_WIDTH;
            vertices[1].y = PSP_GE_SCREEN_HEIGHT; vertices[1].z = 0.f;
            sceGuDrawArray(GU_SPRITES, GU_TEXTURE_32BITF | GU_VERTEX_32BITF | GU_TRANSFORM_2D,
                           2, NULL, vertices);
        }
        sceGuDisable(GU_ALPHA_TEST);
    }
    else
    {
        sceGuClutMode(GU_PSM_5650, 0, 0xff, 0);
        sceGuClutLoad(256 / 8, psp_ge_clut);
        sceGuTexFunc(GU_TFX_REPLACE, GU_TCC_RGB);
        vertices = (PSPGEVertex *)sceGuGetMemory(2 * sizeof(*vertices));
        if (vertices)
        {
            vertices[0].u = 0.f;     vertices[0].v = 0.f;
            vertices[0].x = 0.f;     vertices[0].y = 0.f;     vertices[0].z = 0.f;
            vertices[1].u = width;   vertices[1].v = height;
            vertices[1].x = PSP_GE_SCREEN_WIDTH;
            vertices[1].y = PSP_GE_SCREEN_HEIGHT; vertices[1].z = 0.f;
            sceGuDrawArray(GU_SPRITES, GU_TEXTURE_32BITF | GU_VERTEX_32BITF | GU_TRANSFORM_2D,
                           2, NULL, vertices);
        }
        psp_ge_world_render(psp_ge_clut);
    }
    sceGuFinish();
    sceGuSync(GU_SYNC_FINISH, GU_SYNC_WHAT_DONE);
    sceDisplayWaitVblankStart();
    sceGuSwapBuffers();

    return 1;
}

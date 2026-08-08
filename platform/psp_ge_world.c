#include "platform/psp_ge_world.h"

#include "build.h"

#include <pspgu.h>
#include <pspgum.h>
#include <pspkernel.h>

#include <stdint.h>
#include <string.h>

#define PSP_GE_WORLD_MAX_WALLS 256
#define PSP_GE_WORLD_MAX_SAMPLES 9
#define PSP_GE_WORLD_MAX_PLANES 32
#define PSP_GE_WORLD_MAX_SECTOR_WALLS 128
#define PSP_GE_WORLD_MAX_SECTOR_VERTICES 2048
#define PSP_GE_WORLD_MAX_VISIBLE_SECTORS 32
#define PSP_GE_WORLD_NEAR_CLIP 0.125f
#define PSP_GE_WORLD_UNIT_SCALE (1.0f / 1024.0f)
#define PSP_GE_WORLD_ANGLE_SCALE (1.0f / 16384.0f)
#define PSP_GE_WORLD_FOCAL_LENGTH 240.0f
#define PSP_GE_SCREEN_WIDTH 480
#define PSP_GE_SCREEN_HEIGHT 272

typedef struct PSPGEWorldWireWall
{
    int x1, x2;
    int top1, top2;
    int bottom1, bottom2;
} PSPGEWorldWireWall;

typedef struct PSPGEWorldSample
{
    float x;
    float top, bottom;
    float s_top, s_bottom;
    float t;
} PSPGEWorldSample;

typedef struct PSPGEWorldTexturedWall
{
    const uint8_t *texture;
    int texture_width;
    int texture_height;
    int palette;
    int shade;
    int samples;
    PSPGEWorldSample sample[PSP_GE_WORLD_MAX_SAMPLES];
} PSPGEWorldTexturedWall;

typedef struct PSPGEWorldWireVertex
{
    float x, y, z;
} PSPGEWorldWireVertex;

typedef struct PSPGEWorldTexturedVertex
{
    float s, t;
    float x, y, z;
} PSPGEWorldTexturedVertex;

typedef struct PSPGEWorldPlaneSample
{
    float x;
    float top;
    float bottom;
} PSPGEWorldPlaneSample;

typedef struct PSPGEWorldPlane
{
    int samples;
    PSPGEWorldPlaneSample sample[PSP_GE_WORLD_MAX_SAMPLES];
} PSPGEWorldPlane;

typedef struct PSPGEWorldViewVertex
{
    float x, y, z;
} PSPGEWorldViewVertex;

typedef struct PSPGEWorldSectorCapture
{
    int sectnum;
    int camera_x, camera_y, camera_z;
    int camera_cos, camera_sin;
} PSPGEWorldSectorCapture;

static PSPGEWorldWireWall psp_ge_world_wires[PSP_GE_WORLD_MAX_WALLS];
static PSPGEWorldTexturedWall psp_ge_world_textured[PSP_GE_WORLD_MAX_WALLS];
static PSPGEWorldPlane psp_ge_world_ceilings[PSP_GE_WORLD_MAX_PLANES];
static PSPGEWorldPlane psp_ge_world_floors[PSP_GE_WORLD_MAX_PLANES];
static PSPGEWorldTexturedVertex
    psp_ge_world_vertices[PSP_GE_WORLD_MAX_WALLS * PSP_GE_WORLD_MAX_SAMPLES * 2]
    __attribute__((aligned(64)));
static uint16_t psp_ge_world_cluts[PSP_GE_WORLD_MAX_WALLS][256]
    __attribute__((aligned(64)));
static int psp_ge_world_width;
static int psp_ge_world_height;
static int psp_ge_world_wire_count;
static int psp_ge_world_textured_count;
static int psp_ge_world_ceiling_count;
static int psp_ge_world_floor_count;
static int psp_ge_world_is_enabled;
static int psp_ge_world_textures_enabled;
static int psp_ge_world_replace_walls_enabled;
static int psp_ge_world_planes_are_enabled;
static int psp_ge_world_planes_fill_is_enabled;
static int psp_ge_world_sector3d_is_enabled;
static int psp_ge_world_sector3d_native_is_enabled;
static int psp_ge_world_replace_opaque_is_enabled;
static PSPGEWorldSectorCapture psp_ge_world_sector3d;
static int psp_ge_world_visible_sectors[PSP_GE_WORLD_MAX_VISIBLE_SECTORS];
static int psp_ge_world_visible_sector_count;
static PSPGEWorldWireVertex
    psp_ge_world_sector_vertices[PSP_GE_WORLD_MAX_SECTOR_VERTICES]
    __attribute__((aligned(64)));

static float psp_ge_world_clamp(float value, float maximum)
{
    if (value < 0.f)
        return 0.f;
    if (value > maximum)
        return maximum;
    return value;
}

static int psp_ge_world_is_power_of_two(int value)
{
    return value > 0 && (value & (value - 1)) == 0;
}

static int psp_ge_world_mod(int value, int modulus)
{
    value %= modulus;
    return value < 0 ? value + modulus : value;
}

static int psp_ge_world_vcoord(int swall, int y, int horiz,
                               int yscale, int zd, int shift)
{
    int64_t value = (int64_t)zd + (int64_t)swall * yscale * (y - horiz + 1);

    if (shift > 0)
        return (int)(value >> shift);
    return (int)(value << -shift);
}

void psp_ge_world_set_enabled(int enabled)
{
    psp_ge_world_is_enabled = enabled != 0;
    psp_ge_world_wire_count = 0;
    psp_ge_world_textured_count = 0;
}

void psp_ge_world_set_textures_enabled(int enabled)
{
    psp_ge_world_textures_enabled = enabled != 0;
}

void psp_ge_world_set_replace_walls(int enabled)
{
    psp_ge_world_replace_walls_enabled = enabled != 0;
}

void psp_ge_world_set_planes_enabled(int enabled)
{
    psp_ge_world_planes_are_enabled = enabled != 0;
}

void psp_ge_world_set_planes_fill_enabled(int enabled)
{
    psp_ge_world_planes_fill_is_enabled = enabled != 0;
}

void psp_ge_world_set_sector3d_enabled(int enabled)
{
    psp_ge_world_sector3d_is_enabled = enabled != 0;
    psp_ge_world_sector3d.sectnum = -1;
}

void psp_ge_world_set_sector3d_native_enabled(int enabled)
{
    psp_ge_world_sector3d_native_is_enabled = enabled != 0;
}

void psp_ge_world_set_replace_opaque_enabled(int enabled)
{
    psp_ge_world_replace_opaque_is_enabled = enabled != 0;
}

int psp_ge_world_replace_walls(void)
{
    return psp_ge_world_is_enabled && psp_ge_world_textures_enabled &&
           psp_ge_world_replace_walls_enabled;
}
int psp_ge_world_enabled(void)
{
    return psp_ge_world_is_enabled;
}

int psp_ge_world_planes_enabled(void)
{
    return psp_ge_world_is_enabled && psp_ge_world_planes_are_enabled;
}

int psp_ge_world_planes_fill_enabled(void)
{
    return psp_ge_world_planes_enabled() && psp_ge_world_planes_fill_is_enabled;
}

int psp_ge_world_sector3d_enabled(void)
{
    return psp_ge_world_is_enabled && psp_ge_world_sector3d_is_enabled;
}

int psp_ge_world_sector3d_native_enabled(void)
{
    return psp_ge_world_sector3d_enabled() && psp_ge_world_sector3d_native_is_enabled;
}

int psp_ge_world_replace_opaque_enabled(void)
{
    return psp_ge_world_sector3d_enabled() &&
           psp_ge_world_replace_opaque_is_enabled;
}

void psp_ge_world_begin(int width, int height)
{
    if (!psp_ge_world_is_enabled)
        return;

    psp_ge_world_width = width;
    psp_ge_world_height = height;
    psp_ge_world_wire_count = 0;
    psp_ge_world_textured_count = 0;
    psp_ge_world_ceiling_count = 0;
    psp_ge_world_floor_count = 0;
    psp_ge_world_sector3d.sectnum = -1;
    psp_ge_world_visible_sector_count = 0;
}

void psp_ge_world_capture_sector(int sectnum, int camera_x, int camera_y,
                                 int camera_z, int camera_cos, int camera_sin)
{
    if (!psp_ge_world_sector3d_enabled() || sectnum < 0 || sectnum >= numsectors)
        return;

    psp_ge_world_sector3d.sectnum = sectnum;
    psp_ge_world_sector3d.camera_x = camera_x;
    psp_ge_world_sector3d.camera_y = camera_y;
    psp_ge_world_sector3d.camera_z = camera_z;
    psp_ge_world_sector3d.camera_cos = camera_cos;
    psp_ge_world_sector3d.camera_sin = camera_sin;
    psp_ge_world_capture_visible_sector(sectnum);
}

void psp_ge_world_capture_visible_sector(int sectnum)
{
    int i;

    if (!psp_ge_world_sector3d_enabled() || sectnum < 0 || sectnum >= numsectors)
        return;
    for (i = 0; i < psp_ge_world_visible_sector_count; ++i)
        if (psp_ge_world_visible_sectors[i] == sectnum)
            return;
    if (psp_ge_world_visible_sector_count < PSP_GE_WORLD_MAX_VISIBLE_SECTORS)
        psp_ge_world_visible_sectors[psp_ge_world_visible_sector_count++] = sectnum;
}

void psp_ge_world_capture_wall(int x1, int x2,
                               int top1, int top2,
                               int bottom1, int bottom2)
{
    PSPGEWorldWireWall *wall;

    if (!psp_ge_world_is_enabled || psp_ge_world_wire_count >= PSP_GE_WORLD_MAX_WALLS ||
        psp_ge_world_width <= 0 || psp_ge_world_height <= 0 || x2 <= x1)
        return;

    if ((bottom1 <= top1) && (bottom2 <= top2))
        return;

    wall = &psp_ge_world_wires[psp_ge_world_wire_count++];
    wall->x1 = x1;
    wall->x2 = x2;
    wall->top1 = top1;
    wall->top2 = top2;
    wall->bottom1 = bottom1;
    wall->bottom2 = bottom2;
}

void psp_ge_world_capture_textured_wall(int x1, int x2,
                                        const short *uwal, const short *dwal,
                                        const int *swal, const int *lwal,
                                        const short *umost, const short *dmost,
                                        int horiz, int picnum, int pal, int shade,
                                        int xpanning, int yscale, int zd, int shift)
{
    PSPGEWorldTexturedWall *wall;
    int i, segments, span;
    int const tex_width = tilesizy[picnum];
    int const tex_height = tilesizx[picnum];

    if (!psp_ge_world_is_enabled || !psp_ge_world_textures_enabled ||
        psp_ge_world_textured_count >= PSP_GE_WORLD_MAX_WALLS || x2 <= x1 ||
        !uwal || !dwal || !swal || !lwal || !umost || !dmost ||
        (unsigned)picnum >= (unsigned)MAXTILES || !waloff[picnum])
        return;

    /* The GE's T8 surface is row-major; BUILD art is column-major. Swapping
       width/height makes the original tile bytes directly usable. */
    if (tex_width > 512 || tex_height > 512 ||
        !psp_ge_world_is_power_of_two(tex_width) ||
        !psp_ge_world_is_power_of_two(tex_height))
        return;

    span = x2 - x1;
    segments = (span + 7) / 8;
    if (segments < 1)
        segments = 1;
    if (segments >= PSP_GE_WORLD_MAX_SAMPLES)
        segments = PSP_GE_WORLD_MAX_SAMPLES - 1;

    wall = &psp_ge_world_textured[psp_ge_world_textured_count++];
    wall->texture = (const uint8_t *)(uintptr_t)waloff[picnum];
    wall->texture_width = tex_width;
    wall->texture_height = tex_height;
    wall->palette = pal;
    wall->shade = shade;
    wall->samples = segments + 1;

    for (i = 0; i <= segments; ++i)
    {
        PSPGEWorldSample *sample = &wall->sample[i];
        int const x = x1 + (span * i) / segments;
        int const top = uwal[x] > umost[x] ? uwal[x] : umost[x];
        int const bottom = dwal[x] < dmost[x] ? dwal[x] : dmost[x];
        int const u = lwal[x] + xpanning;

        sample->x = (float)x;
        sample->top = (float)top;
        sample->bottom = (float)bottom;
        sample->s_top = (float)psp_ge_world_vcoord(swal[x], top, horiz,
                                                    yscale, zd, shift);
        sample->s_bottom = (float)psp_ge_world_vcoord(swal[x], bottom, horiz,
                                                       yscale, zd, shift);
        sample->t = (float)u;
    }
}

static void psp_ge_world_capture_plane(PSPGEWorldPlane *planes, int *count,
                                       int x1, int x2, const short *umost,
                                       const short *dmost, const short *clip,
                                       int floor)
{
    PSPGEWorldPlane *plane;
    int i, segments, span;
    int visible = 0;

    if (!psp_ge_world_planes_are_enabled || *count >= PSP_GE_WORLD_MAX_PLANES ||
        x2 <= x1 || !umost || !dmost || !clip)
        return;

    span = x2 - x1;
    segments = (span + 7) / 8;
    if (segments < 1)
        segments = 1;
    if (segments >= PSP_GE_WORLD_MAX_SAMPLES)
        segments = PSP_GE_WORLD_MAX_SAMPLES - 1;

    plane = &planes[*count];
    plane->samples = segments + 1;
    for (i = 0; i <= segments; ++i)
    {
        PSPGEWorldPlaneSample *sample = &plane->sample[i];
        int const x = x1 + (span * i) / segments;
        int const top = floor ? (clip[x] > umost[x] ? clip[x] : umost[x]) : umost[x];
        int const bottom = floor ? dmost[x] : (clip[x] < dmost[x] ? clip[x] : dmost[x]);

        sample->x = (float)x;
        sample->top = (float)top;
        sample->bottom = (float)bottom;
        if (bottom > top + 1)
            visible = 1;
    }

    if (visible)
        ++*count;
}

void psp_ge_world_capture_ceiling(int x1, int x2, const short *umost,
                                  const short *dmost, const short *uplc)
{
    psp_ge_world_capture_plane(psp_ge_world_ceilings, &psp_ge_world_ceiling_count,
                               x1, x2, umost, dmost, uplc, 0);
}

void psp_ge_world_capture_floor(int x1, int x2, const short *umost,
                                const short *dmost, const short *dplc)
{
    psp_ge_world_capture_plane(psp_ge_world_floors, &psp_ge_world_floor_count,
                               x1, x2, umost, dmost, dplc, 1);
}

static void psp_ge_world_render_textures(const uint16_t *palette565)
{
    int i;
    int vertex_offset = 0;

    if (!palette565)
        return;

    sceGuEnable(GU_TEXTURE_2D);
    sceGuDisable(GU_BLEND);
    sceGuTexMode(GU_PSM_T8, 0, 0, 0);
    sceGuTexFunc(GU_TFX_REPLACE, GU_TCC_RGB);
    sceGuTexFilter(GU_NEAREST, GU_NEAREST);
    sceGuTexWrap(GU_REPEAT, GU_REPEAT);
    sceGuTexScale(1.f, 1.f);
    sceGuTexOffset(0.f, 0.f);
    sceGuColor(0xffffffff);

    for (i = 0; i < psp_ge_world_textured_count; ++i)
    {
        PSPGEWorldTexturedWall const *wall = &psp_ge_world_textured[i];
        PSPGEWorldTexturedVertex *vertices = &psp_ge_world_vertices[vertex_offset];
        uint16_t *clut = psp_ge_world_cluts[i];
        const uint8_t *lookup;
        int shade = wall->shade;
        int j;

        if (vertex_offset + wall->samples * 2 >
            PSP_GE_WORLD_MAX_WALLS * PSP_GE_WORLD_MAX_SAMPLES * 2)
            break;

        if ((unsigned)wall->palette < (unsigned)MAXPALOOKUPS)
            lookup = palookup[wall->palette];
        else
            lookup = NULL;
        if (!lookup)
            lookup = palookup[0];
        if (!lookup)
            continue;

        if (shade < 0)
            shade = 0;
        else if (shade >= numpalookups)
            shade = numpalookups - 1;

        for (j = 0; j < 256; ++j)
            clut[j] = palette565[lookup[(shade << 8) + j]];

        for (j = 0; j < wall->samples; ++j)
        {
            PSPGEWorldSample const *sample = &wall->sample[j];
            PSPGEWorldTexturedVertex *top = &vertices[j * 2];
            PSPGEWorldTexturedVertex *bottom = top + 1;
            float const x = psp_ge_world_clamp(sample->x * PSP_GE_SCREEN_WIDTH /
                                                psp_ge_world_width, PSP_GE_SCREEN_WIDTH);

            top->s = sample->s_top;
            top->t = sample->t;
            top->x = x;
            top->y = psp_ge_world_clamp(sample->top * PSP_GE_SCREEN_HEIGHT /
                                        psp_ge_world_height, PSP_GE_SCREEN_HEIGHT);
            top->z = 0.f;
            bottom->s = sample->s_bottom;
            bottom->t = sample->t;
            bottom->x = x;
            bottom->y = psp_ge_world_clamp(sample->bottom * PSP_GE_SCREEN_HEIGHT /
                                           psp_ge_world_height, PSP_GE_SCREEN_HEIGHT);
            bottom->z = 0.f;
        }

        sceKernelDcacheWritebackRange((void *)wall->texture,
                                      (unsigned int)(wall->texture_width * wall->texture_height));
        sceKernelDcacheWritebackRange(clut, sizeof(psp_ge_world_cluts[0]));
        sceKernelDcacheWritebackRange(vertices,
                                      (unsigned int)(wall->samples * 2 * sizeof(*vertices)));
        sceGuClutMode(GU_PSM_5650, 0, 0xff, 0);
        sceGuClutLoad(256 / 8, clut);
        sceGuTexImage(0, wall->texture_width, wall->texture_height,
                      wall->texture_width, wall->texture);
        sceGuDrawArray(GU_TRIANGLE_STRIP,
                       GU_TEXTURE_32BITF | GU_VERTEX_32BITF | GU_TRANSFORM_2D,
                       wall->samples * 2, NULL, vertices);
        vertex_offset += wall->samples * 2;
    }
}

static void psp_ge_world_render_wireframe(void)
{
    PSPGEWorldWireVertex *vertices;
    float sx, sy;
    int i;

    if (psp_ge_world_wire_count <= 0)
        return;

    vertices = (PSPGEWorldWireVertex *)sceGuGetMemory(
        (unsigned int)(psp_ge_world_wire_count * 8 * (int)sizeof(*vertices)));
    if (!vertices)
        return;

    sx = (float)PSP_GE_SCREEN_WIDTH / (float)psp_ge_world_width;
    sy = (float)PSP_GE_SCREEN_HEIGHT / (float)psp_ge_world_height;

    for (i = 0; i < psp_ge_world_wire_count; ++i)
    {
        PSPGEWorldWireWall const *wall = &psp_ge_world_wires[i];
        float const x1 = psp_ge_world_clamp((float)wall->x1 * sx, PSP_GE_SCREEN_WIDTH);
        float const x2 = psp_ge_world_clamp((float)wall->x2 * sx, PSP_GE_SCREEN_WIDTH);
        float const top1 = psp_ge_world_clamp((float)wall->top1 * sy, PSP_GE_SCREEN_HEIGHT);
        float const top2 = psp_ge_world_clamp((float)wall->top2 * sy, PSP_GE_SCREEN_HEIGHT);
        float const bottom1 = psp_ge_world_clamp((float)wall->bottom1 * sy, PSP_GE_SCREEN_HEIGHT);
        float const bottom2 = psp_ge_world_clamp((float)wall->bottom2 * sy, PSP_GE_SCREEN_HEIGHT);
        PSPGEWorldWireVertex *line = vertices + i * 8;

        line[0].x = x1; line[0].y = top1;    line[0].z = 0.f;
        line[1].x = x2; line[1].y = top2;    line[1].z = 0.f;
        line[2].x = x1; line[2].y = bottom1; line[2].z = 0.f;
        line[3].x = x2; line[3].y = bottom2; line[3].z = 0.f;
        line[4].x = x1; line[4].y = top1;    line[4].z = 0.f;
        line[5].x = x1; line[5].y = bottom1; line[5].z = 0.f;
        line[6].x = x2; line[6].y = top2;    line[6].z = 0.f;
        line[7].x = x2; line[7].y = bottom2; line[7].z = 0.f;
    }

    sceGuDisable(GU_TEXTURE_2D);
    sceGuEnable(GU_BLEND);
    sceGuBlendFunc(GU_ADD, GU_SRC_ALPHA, GU_ONE_MINUS_SRC_ALPHA, 0, 0);
    sceGuColor(0xa000ff00);
    sceGuDrawArray(GU_LINES, GU_VERTEX_32BITF | GU_TRANSFORM_2D,
                   psp_ge_world_wire_count * 8, NULL, vertices);
    sceGuDisable(GU_BLEND);
    sceGuEnable(GU_TEXTURE_2D);
}

static void psp_ge_world_render_plane_fill(const PSPGEWorldPlane *planes,
                                           int count, unsigned int color)
{
    int i;

    if (count <= 0)
        return;

    sceGuDisable(GU_TEXTURE_2D);
    sceGuEnable(GU_BLEND);
    sceGuBlendFunc(GU_ADD, GU_SRC_ALPHA, GU_ONE_MINUS_SRC_ALPHA, 0, 0);
    sceGuColor(color);

    for (i = 0; i < count; ++i)
    {
        PSPGEWorldPlane const *plane = &planes[i];
        PSPGEWorldWireVertex *vertices;
        int j;

        if (plane->samples < 2)
            continue;
        vertices = (PSPGEWorldWireVertex *)sceGuGetMemory(
            (unsigned int)(plane->samples * 2 * (int)sizeof(*vertices)));
        if (!vertices)
            break;

        for (j = 0; j < plane->samples; ++j)
        {
            PSPGEWorldPlaneSample const *sample = &plane->sample[j];
            PSPGEWorldWireVertex *top = &vertices[j * 2];
            PSPGEWorldWireVertex *bottom = top + 1;
            float const x = psp_ge_world_clamp(sample->x * PSP_GE_SCREEN_WIDTH /
                                               psp_ge_world_width, PSP_GE_SCREEN_WIDTH);
            float const y_top = psp_ge_world_clamp(sample->top * PSP_GE_SCREEN_HEIGHT /
                                                   psp_ge_world_height, PSP_GE_SCREEN_HEIGHT);
            float y_bottom = psp_ge_world_clamp(sample->bottom * PSP_GE_SCREEN_HEIGHT /
                                                psp_ge_world_height, PSP_GE_SCREEN_HEIGHT);

            if (y_bottom < y_top)
                y_bottom = y_top;
            top->x = x;
            top->y = y_top;
            top->z = 0.f;
            bottom->x = x;
            bottom->y = y_bottom;
            bottom->z = 0.f;
        }

        sceGuDrawArray(GU_TRIANGLE_STRIP, GU_VERTEX_32BITF | GU_TRANSFORM_2D,
                       plane->samples * 2, NULL, vertices);
    }

    sceGuDisable(GU_BLEND);
    sceGuEnable(GU_TEXTURE_2D);
}

static void psp_ge_world_render_plane_lines(const PSPGEWorldPlane *planes,
                                            int count, unsigned int color)
{
    PSPGEWorldWireVertex *vertices;
    int i, j, vertex_count = 0;

    if (count <= 0)
        return;

    for (i = 0; i < count; ++i)
        vertex_count += (planes[i].samples - 1) * 4 + 4;
    if (vertex_count <= 0)
        return;

    vertices = (PSPGEWorldWireVertex *)sceGuGetMemory(
        (unsigned int)(vertex_count * (int)sizeof(*vertices)));
    if (!vertices)
        return;

    vertex_count = 0;
    for (i = 0; i < count; ++i)
    {
        PSPGEWorldPlane const *plane = &planes[i];
        for (j = 0; j < plane->samples - 1; ++j)
        {
            PSPGEWorldPlaneSample const *a = &plane->sample[j];
            PSPGEWorldPlaneSample const *b = &plane->sample[j + 1];
            PSPGEWorldWireVertex *line = &vertices[vertex_count];

            line[0].x = psp_ge_world_clamp(a->x * PSP_GE_SCREEN_WIDTH / psp_ge_world_width, PSP_GE_SCREEN_WIDTH);
            line[0].y = psp_ge_world_clamp(a->top * PSP_GE_SCREEN_HEIGHT / psp_ge_world_height, PSP_GE_SCREEN_HEIGHT);
            line[0].z = 0.f;
            line[1].x = psp_ge_world_clamp(b->x * PSP_GE_SCREEN_WIDTH / psp_ge_world_width, PSP_GE_SCREEN_WIDTH);
            line[1].y = psp_ge_world_clamp(b->top * PSP_GE_SCREEN_HEIGHT / psp_ge_world_height, PSP_GE_SCREEN_HEIGHT);
            line[1].z = 0.f;
            line[2].x = psp_ge_world_clamp(a->x * PSP_GE_SCREEN_WIDTH / psp_ge_world_width, PSP_GE_SCREEN_WIDTH);
            line[2].y = psp_ge_world_clamp(a->bottom * PSP_GE_SCREEN_HEIGHT / psp_ge_world_height, PSP_GE_SCREEN_HEIGHT);
            line[2].z = 0.f;
            line[3].x = psp_ge_world_clamp(b->x * PSP_GE_SCREEN_WIDTH / psp_ge_world_width, PSP_GE_SCREEN_WIDTH);
            line[3].y = psp_ge_world_clamp(b->bottom * PSP_GE_SCREEN_HEIGHT / psp_ge_world_height, PSP_GE_SCREEN_HEIGHT);
            line[3].z = 0.f;
            vertex_count += 4;
        }

        {
            PSPGEWorldPlaneSample const *a = &plane->sample[0];
            PSPGEWorldPlaneSample const *b = &plane->sample[plane->samples - 1];
            PSPGEWorldWireVertex *line = &vertices[vertex_count];
            line[0].x = line[1].x = psp_ge_world_clamp(a->x * PSP_GE_SCREEN_WIDTH / psp_ge_world_width, PSP_GE_SCREEN_WIDTH);
            line[0].y = psp_ge_world_clamp(a->top * PSP_GE_SCREEN_HEIGHT / psp_ge_world_height, PSP_GE_SCREEN_HEIGHT);
            line[1].y = psp_ge_world_clamp(a->bottom * PSP_GE_SCREEN_HEIGHT / psp_ge_world_height, PSP_GE_SCREEN_HEIGHT);
            line[0].z = line[1].z = 0.f;
            line[2].x = line[3].x = psp_ge_world_clamp(b->x * PSP_GE_SCREEN_WIDTH / psp_ge_world_width, PSP_GE_SCREEN_WIDTH);
            line[2].y = psp_ge_world_clamp(b->top * PSP_GE_SCREEN_HEIGHT / psp_ge_world_height, PSP_GE_SCREEN_HEIGHT);
            line[3].y = psp_ge_world_clamp(b->bottom * PSP_GE_SCREEN_HEIGHT / psp_ge_world_height, PSP_GE_SCREEN_HEIGHT);
            line[2].z = line[3].z = 0.f;
            vertex_count += 4;
        }
    }

    sceGuDisable(GU_TEXTURE_2D);
    sceGuEnable(GU_BLEND);
    sceGuBlendFunc(GU_ADD, GU_SRC_ALPHA, GU_ONE_MINUS_SRC_ALPHA, 0, 0);
    sceGuColor(color);
    sceGuDrawArray(GU_LINES, GU_VERTEX_32BITF | GU_TRANSFORM_2D,
                   vertex_count, NULL, vertices);
    sceGuDisable(GU_BLEND);
    sceGuEnable(GU_TEXTURE_2D);
}

static PSPGEWorldViewVertex psp_ge_world_view_from_build(int x, int y, int z)
{
    PSPGEWorldViewVertex vertex;
    PSPGEWorldSectorCapture const *camera = &psp_ge_world_sector3d;
    float const dx = (float)(x - camera->camera_x);
    float const dy = (float)(y - camera->camera_y);
    float const cosine = (float)camera->camera_cos * PSP_GE_WORLD_ANGLE_SCALE;
    float const sine = (float)camera->camera_sin * PSP_GE_WORLD_ANGLE_SCALE;

    vertex.x = (dy * cosine - dx * sine) * PSP_GE_WORLD_UNIT_SCALE;
    vertex.y = (float)(camera->camera_z - z) * PSP_GE_WORLD_UNIT_SCALE;
    vertex.z = (dx * cosine + dy * sine) * PSP_GE_WORLD_UNIT_SCALE;
    return vertex;
}

static PSPGEWorldViewVertex psp_ge_world_view_lerp(PSPGEWorldViewVertex a,
                                                    PSPGEWorldViewVertex b,
                                                    float t)
{
    PSPGEWorldViewVertex result;
    result.x = a.x + (b.x - a.x) * t;
    result.y = a.y + (b.y - a.y) * t;
    result.z = a.z + (b.z - a.z) * t;
    return result;
}

static int psp_ge_world_project(PSPGEWorldViewVertex vertex,
                                PSPGEWorldWireVertex *result)
{
    float inverse_depth;

    if (vertex.z < PSP_GE_WORLD_NEAR_CLIP)
        return 0;

    inverse_depth = 1.f / vertex.z;
    result->x = PSP_GE_SCREEN_WIDTH * 0.5f + vertex.x * PSP_GE_WORLD_FOCAL_LENGTH * inverse_depth;
    result->y = PSP_GE_SCREEN_HEIGHT * 0.5f - vertex.y * PSP_GE_WORLD_FOCAL_LENGTH * inverse_depth;
    /* GU_GEQUAL with a cleared Z buffer: nearer geometry receives a larger Z. */
    result->z = 65535.f / (1.f + vertex.z);
    return 1;
}

static int psp_ge_world_emit_clipped_triangle(PSPGEWorldViewVertex a,
                                              PSPGEWorldViewVertex b,
                                              PSPGEWorldViewVertex c,
                                              PSPGEWorldWireVertex *output,
                                              int count, int maximum)
{
    PSPGEWorldViewVertex input[3];
    PSPGEWorldViewVertex clipped[4];
    PSPGEWorldViewVertex previous;
    int previous_inside;
    int clipped_count = 0;
    int i;

    input[0] = a;
    input[1] = b;
    input[2] = c;
    previous = input[2];
    previous_inside = previous.z >= PSP_GE_WORLD_NEAR_CLIP;
    for (i = 0; i < 3; ++i)
    {
        PSPGEWorldViewVertex const current = input[i];
        int const current_inside = current.z >= PSP_GE_WORLD_NEAR_CLIP;

        if (current_inside != previous_inside)
        {
            float const ratio = (PSP_GE_WORLD_NEAR_CLIP - previous.z) /
                                (current.z - previous.z);
            clipped[clipped_count++] = psp_ge_world_view_lerp(previous, current, ratio);
        }
        if (current_inside)
            clipped[clipped_count++] = current;
        previous = current;
        previous_inside = current_inside;
    }

    for (i = 1; i + 1 < clipped_count; ++i)
    {
        if (count + 3 > maximum)
            break;
        if (!psp_ge_world_project(clipped[0], &output[count]) ||
            !psp_ge_world_project(clipped[i], &output[count + 1]) ||
            !psp_ge_world_project(clipped[i + 1], &output[count + 2]))
            continue;
        count += 3;
    }
    return count;
}

static int psp_ge_world_emit_native_clipped_triangle(PSPGEWorldViewVertex a,
                                                     PSPGEWorldViewVertex b,
                                                     PSPGEWorldViewVertex c,
                                                     PSPGEWorldWireVertex *output,
                                                     int count, int maximum)
{
    PSPGEWorldViewVertex input[3] = { a, b, c };
    PSPGEWorldViewVertex clipped[4];
    PSPGEWorldViewVertex previous = input[2];
    int previous_inside = previous.z >= PSP_GE_WORLD_NEAR_CLIP;
    int clipped_count = 0;
    int i;

    for (i = 0; i < 3; ++i)
    {
        PSPGEWorldViewVertex const current = input[i];
        int const current_inside = current.z >= PSP_GE_WORLD_NEAR_CLIP;
        if (current_inside != previous_inside)
        {
            float const ratio = (PSP_GE_WORLD_NEAR_CLIP - previous.z) /
                                (current.z - previous.z);
            clipped[clipped_count++] = psp_ge_world_view_lerp(previous, current, ratio);
        }
        if (current_inside)
            clipped[clipped_count++] = current;
        previous = current;
        previous_inside = current_inside;
    }
    for (i = 1; i + 1 < clipped_count && count + 3 <= maximum; ++i)
    {
        output[count].x = clipped[0].x;
        output[count].y = clipped[0].y;
        /* gumPerspective follows the OpenGL-style convention: the camera
           looks down -Z. BUILD's visibility transform uses positive depth. */
        output[count++].z = -clipped[0].z;
        output[count].x = clipped[i].x;
        output[count].y = clipped[i].y;
        output[count++].z = -clipped[i].z;
        output[count].x = clipped[i + 1].x;
        output[count].y = clipped[i + 1].y;
        output[count++].z = -clipped[i + 1].z;
    }
    return count;
}

static int psp_ge_world_emit_sector_triangle(PSPGEWorldViewVertex a,
                                             PSPGEWorldViewVertex b,
                                             PSPGEWorldViewVertex c,
                                             PSPGEWorldWireVertex *output,
                                             int count, int maximum)
{
    if (psp_ge_world_sector3d_native_enabled())
        return psp_ge_world_emit_native_clipped_triangle(a, b, c, output, count, maximum);
    return psp_ge_world_emit_clipped_triangle(a, b, c, output, count, maximum);
}
static int64_t psp_ge_world_cross(const sectortype *sector_ptr,
                                  int first, int second, int third)
{
    walltype const *a = &wall[sector_ptr->wallptr + first];
    walltype const *b = &wall[sector_ptr->wallptr + second];
    walltype const *c = &wall[sector_ptr->wallptr + third];
    return (int64_t)(b->x - a->x) * (c->y - a->y) -
           (int64_t)(b->y - a->y) * (c->x - a->x);
}

static int psp_ge_world_point_in_triangle(const sectortype *sector_ptr, int point,
                                          int first, int second, int third,
                                          int orientation)
{
    int64_t const a = psp_ge_world_cross(sector_ptr, first, second, point);
    int64_t const b = psp_ge_world_cross(sector_ptr, second, third, point);
    int64_t const c = psp_ge_world_cross(sector_ptr, third, first, point);

    if (orientation > 0)
        return a >= 0 && b >= 0 && c >= 0;
    return a <= 0 && b <= 0 && c <= 0;
}

static PSPGEWorldViewVertex psp_ge_world_sector_vertex(int sectnum,
                                                        const sectortype *sector_ptr,
                                                        int local_wall, int floor)
{
    walltype const *wall_ptr = &wall[sector_ptr->wallptr + local_wall];
    int const z = floor ? getflorzofslope(sectnum, wall_ptr->x, wall_ptr->y)
                        : getceilzofslope(sectnum, wall_ptr->x, wall_ptr->y);
    return psp_ge_world_view_from_build(wall_ptr->x, wall_ptr->y, z);
}

static int psp_ge_world_build_sector_surface(int sectnum, const sectortype *sector_ptr, int floor)
{
    int indices[PSP_GE_WORLD_MAX_SECTOR_WALLS];
    int64_t area = 0;
    int count = 0;
    int remaining;
    int guard = 0;
    int i;

    if (sector_ptr->wallnum < 3 || sector_ptr->wallnum > PSP_GE_WORLD_MAX_SECTOR_WALLS)
        return 0;

    for (i = 0; i < sector_ptr->wallnum; ++i)
    {
        walltype const *first = &wall[sector_ptr->wallptr + i];
        walltype const *second = &wall[sector_ptr->wallptr + ((i + 1) % sector_ptr->wallnum)];
        indices[i] = i;
        area += (int64_t)first->x * second->y - (int64_t)first->y * second->x;
    }
    if (area == 0)
        return 0;

    remaining = sector_ptr->wallnum;
    while (remaining > 2 && guard++ < sector_ptr->wallnum * sector_ptr->wallnum)
    {
        int ear_found = 0;

        for (i = 0; i < remaining; ++i)
        {
            int const previous = indices[(i + remaining - 1) % remaining];
            int const current = indices[i];
            int const next = indices[(i + 1) % remaining];
            int j;
            int contains_vertex = 0;
            int64_t const cross = psp_ge_world_cross(sector_ptr, previous, current, next);

            if ((area > 0 && cross <= 0) || (area < 0 && cross >= 0))
                continue;
            for (j = 0; j < remaining; ++j)
            {
                int const candidate = indices[j];
                if (candidate == previous || candidate == current || candidate == next)
                    continue;
                if (psp_ge_world_point_in_triangle(sector_ptr, candidate,
                                                   previous, current, next,
                                                   area > 0 ? 1 : -1))
                {
                    contains_vertex = 1;
                    break;
                }
            }
            if (contains_vertex)
                continue;

            count = psp_ge_world_emit_sector_triangle(
                psp_ge_world_sector_vertex(sectnum, sector_ptr, previous, floor),
                psp_ge_world_sector_vertex(sectnum, sector_ptr, current, floor),
                psp_ge_world_sector_vertex(sectnum, sector_ptr, next, floor),
                psp_ge_world_sector_vertices, count, PSP_GE_WORLD_MAX_SECTOR_VERTICES);
            memmove(&indices[i], &indices[i + 1],
                    (size_t)(remaining - i - 1) * sizeof(indices[0]));
            --remaining;
            ear_found = 1;
            break;
        }
        if (!ear_found)
            break;
    }

    /* Malformed or self-intersecting editor sectors are left for the CPU path.
       This fan is only a bounded visual fallback for the diagnostic pass. */
    if (remaining > 2)
    {
        for (i = 1; i + 1 < remaining; ++i)
            count = psp_ge_world_emit_sector_triangle(
                psp_ge_world_sector_vertex(sectnum, sector_ptr, indices[0], floor),
                psp_ge_world_sector_vertex(sectnum, sector_ptr, indices[i], floor),
                psp_ge_world_sector_vertex(sectnum, sector_ptr, indices[i + 1], floor),
                psp_ge_world_sector_vertices, count, PSP_GE_WORLD_MAX_SECTOR_VERTICES);
    }
    return count;
}

static int psp_ge_world_emit_wall_quad(walltype const *first, walltype const *second,
                                       int top_left_z, int top_right_z,
                                       int bottom_left_z, int bottom_right_z,
                                       int count)
{
    PSPGEWorldViewVertex const top_left = psp_ge_world_view_from_build(first->x, first->y, top_left_z);
    PSPGEWorldViewVertex const top_right = psp_ge_world_view_from_build(second->x, second->y, top_right_z);
    PSPGEWorldViewVertex const bottom_left = psp_ge_world_view_from_build(first->x, first->y, bottom_left_z);
    PSPGEWorldViewVertex const bottom_right = psp_ge_world_view_from_build(second->x, second->y, bottom_right_z);

    count = psp_ge_world_emit_sector_triangle(top_left, top_right, bottom_right,
                                                psp_ge_world_sector_vertices, count,
                                                PSP_GE_WORLD_MAX_SECTOR_VERTICES);
    return psp_ge_world_emit_sector_triangle(top_left, bottom_right, bottom_left,
                                              psp_ge_world_sector_vertices, count,
                                              PSP_GE_WORLD_MAX_SECTOR_VERTICES);
}

static int psp_ge_world_build_sector_walls(int sectnum, const sectortype *sector_ptr)
{
    int count = 0;
    int i;

    for (i = 0; i < sector_ptr->wallnum; ++i)
    {
        walltype const *first = &wall[sector_ptr->wallptr + i];
        walltype const *second;
        int top_left, top_right, bottom_left, bottom_right;

        if (first->point2 < 0 || first->point2 >= numwalls)
            continue;
        second = &wall[first->point2];
        top_left = getceilzofslope(sectnum, first->x, first->y);
        top_right = getceilzofslope(sectnum, second->x, second->y);
        bottom_left = getflorzofslope(sectnum, first->x, first->y);
        bottom_right = getflorzofslope(sectnum, second->x, second->y);

        if (first->nextsector < 0 || first->nextsector >= numsectors)
        {
            count = psp_ge_world_emit_wall_quad(first, second, top_left, top_right,
                                                bottom_left, bottom_right, count);
        }
        else
        {
            int const next_top_left = getceilzofslope(first->nextsector, first->x, first->y);
            int const next_top_right = getceilzofslope(first->nextsector, second->x, second->y);
            int const next_bottom_left = getflorzofslope(first->nextsector, first->x, first->y);
            int const next_bottom_right = getflorzofslope(first->nextsector, second->x, second->y);

            /* A portal is open between its lower ceiling and higher floor.
               Draw only the opaque upper/lower bands belonging to this sector. */
            if (next_top_left > top_left || next_top_right > top_right)
                count = psp_ge_world_emit_wall_quad(first, second, top_left, top_right,
                                                    next_top_left > top_left ? next_top_left : top_left,
                                                    next_top_right > top_right ? next_top_right : top_right,
                                                    count);
            if (next_bottom_left < bottom_left || next_bottom_right < bottom_right)
                count = psp_ge_world_emit_wall_quad(first, second,
                                                    next_bottom_left < bottom_left ? next_bottom_left : bottom_left,
                                                    next_bottom_right < bottom_right ? next_bottom_right : bottom_right,
                                                    bottom_left, bottom_right, count);
        }
    }
    return count;
}

static void psp_ge_world_draw_sector_vertices(int count, unsigned int color)
{
    PSPGEWorldWireVertex *vertices;

    if (count <= 0)
        return;
    vertices = (PSPGEWorldWireVertex *)sceGuGetMemory(
        (unsigned int)(count * (int)sizeof(*vertices)));
    if (!vertices)
        return;
    memcpy(vertices, psp_ge_world_sector_vertices,
           (size_t)count * sizeof(*vertices));
    sceGuColor(color);
    sceGuDrawArray(GU_TRIANGLES, GU_VERTEX_32BITF |
                   (psp_ge_world_sector3d_native_enabled() ? GU_TRANSFORM_3D : GU_TRANSFORM_2D),
                   count, NULL, vertices);
}

static void psp_ge_world_render_sector3d(const uint16_t *palette565)
{
    ScePspFMatrix4 identity;
    ScePspFMatrix4 projection;
    int native = psp_ge_world_sector3d_native_enabled();
    int count;
    int i;

    if (psp_ge_world_visible_sector_count <= 0)
        return;

    sceGuDisable(GU_TEXTURE_2D);
    sceGuDisable(GU_BLEND);
    /* BUILD sectors do not share a guaranteed winding. Keep both sides while
       the native path is being validated, matching the software renderer. */
    sceGuDisable(GU_CULL_FACE);
    sceGuEnable(GU_CLIP_PLANES);
    sceGuEnable(GU_DEPTH_TEST);
    sceGuDepthMask(0);
    sceGuClear(GU_DEPTH_BUFFER_BIT);

    if (native)
    {
        gumLoadIdentity(&identity);
        gumLoadIdentity(&projection);
        gumPerspective(&projection, 59.0f,
                       (float)PSP_GE_SCREEN_WIDTH / (float)PSP_GE_SCREEN_HEIGHT,
                       PSP_GE_WORLD_NEAR_CLIP, 1024.0f);
        sceGuSetMatrix(GU_PROJECTION, &projection);
        sceGuSetMatrix(GU_VIEW, &identity);
        sceGuSetMatrix(GU_MODEL, &identity);
    }

    for (i = 0; i < psp_ge_world_visible_sector_count; ++i)
    {
        int const sectnum = psp_ge_world_visible_sectors[i];
        sectortype const *sector_ptr = &sector[sectnum];

        if (sector_ptr->wallnum < 3 || sector_ptr->wallnum > PSP_GE_WORLD_MAX_SECTOR_WALLS)
            continue;
        if (!(sector_ptr->ceilingstat & 1))
        {
            count = psp_ge_world_build_sector_surface(sectnum, sector_ptr, 0);
            psp_ge_world_draw_sector_vertices(count, 0x38ff8040);
        }
        if (!(sector_ptr->floorstat & 1))
        {
            count = psp_ge_world_build_sector_surface(sectnum, sector_ptr, 1);
            psp_ge_world_draw_sector_vertices(count, 0x384080ff);
        }
        count = psp_ge_world_build_sector_walls(sectnum, sector_ptr);
        psp_ge_world_draw_sector_vertices(count, 0x5080ff40);
    }

    sceGuDepthMask(0xffff);
    sceGuDisable(GU_DEPTH_TEST);

    if (psp_ge_world_replace_opaque_enabled() && psp_ge_world_textures_enabled)
        psp_ge_world_render_textures(palette565);
#if defined(PSP_GE_NATIVE_PROBE_BUILD)
    if (native)
    {
        PSPGEWorldWireVertex *probe = (PSPGEWorldWireVertex *)sceGuGetMemory(3 * sizeof(*probe));
        if (probe)
        {
            probe[0].x = -1.5f; probe[0].y = -1.0f; probe[0].z = -3.0f;
            probe[1].x =  1.5f; probe[1].y = -1.0f; probe[1].z = -3.0f;
            probe[2].x =  0.0f; probe[2].y =  1.2f; probe[2].z = -3.0f;
            sceGuDisable(GU_TEXTURE_2D);
            sceGuColor(0xff00ffff);
            sceGuDrawArray(GU_TRIANGLES, GU_VERTEX_32BITF | GU_TRANSFORM_3D,
                           3, NULL, probe);
        }
    }
#endif
    if (native)
    {
        sceGuSetMatrix(GU_PROJECTION, &identity);
        sceGuSetMatrix(GU_VIEW, &identity);
        sceGuSetMatrix(GU_MODEL, &identity);
    }
    sceGuDisable(GU_BLEND);
    sceGuEnable(GU_TEXTURE_2D);
}

void psp_ge_world_render(const unsigned short *palette565)
{
    if (!psp_ge_world_is_enabled || psp_ge_world_width <= 0 ||
        psp_ge_world_height <= 0)
        return;

    if (psp_ge_world_sector3d_enabled())
    {
        psp_ge_world_render_sector3d(palette565);
        return;
    }

    if (psp_ge_world_textures_enabled)
        psp_ge_world_render_textures(palette565);
    else
        psp_ge_world_render_wireframe();

    if (psp_ge_world_planes_are_enabled)
    {
        if (psp_ge_world_planes_fill_is_enabled)
        {
            psp_ge_world_render_plane_fill(psp_ge_world_ceilings,
                                           psp_ge_world_ceiling_count, 0x40ff8040);
            psp_ge_world_render_plane_fill(psp_ge_world_floors,
                                           psp_ge_world_floor_count, 0x404080ff);
        }
        else
        {
            psp_ge_world_render_plane_lines(psp_ge_world_ceilings,
                                            psp_ge_world_ceiling_count, 0xa0ff8040);
            psp_ge_world_render_plane_lines(psp_ge_world_floors,
                                            psp_ge_world_floor_count, 0xa04080ff);
        }
    }
}
#ifndef JFBLOOD_PSP_GE_WORLD_H
#define JFBLOOD_PSP_GE_WORLD_H

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Experimental bridge between the classic BUILD visibility pass and the GE.
 *
 * The classic renderer remains authoritative until a material class has been
 * proven by the overlay path. The first material class is opaque wall spans.
 */
void psp_ge_world_set_enabled(int enabled);
void psp_ge_world_set_textures_enabled(int enabled);
void psp_ge_world_set_replace_walls(int enabled);
/* Diagnostic capture of portal-clipped ceiling/floor spans. This is the
   geometry source for the future opaque GE pass; it does not replace the
   software plane rasterizer yet. */
void psp_ge_world_set_planes_enabled(int enabled);
void psp_ge_world_set_planes_fill_enabled(int enabled);
/* Experimental opaque scene pass: current-sector geometry with real GE depth. */
void psp_ge_world_set_sector3d_enabled(int enabled);
/* Lets the GE perform perspective projection for the opaque-sector proof. */
void psp_ge_world_set_sector3d_native_enabled(int enabled);
/* Hybrid mode: opaque sector geometry is final; CPU becomes an overlay. */
void psp_ge_world_set_replace_opaque_enabled(int enabled);
int psp_ge_world_enabled(void);
int psp_ge_world_replace_walls(void);
int psp_ge_world_planes_enabled(void);
int psp_ge_world_planes_fill_enabled(void);
int psp_ge_world_sector3d_enabled(void);
int psp_ge_world_sector3d_native_enabled(void);
int psp_ge_world_replace_opaque_enabled(void);
void psp_ge_world_begin(int width, int height);
void psp_ge_world_capture_sector(int sectnum, int camera_x, int camera_y,
                                 int camera_z, int camera_cos, int camera_sin);
/* Called from BUILD's bunch traversal. This records only sectors which have
   already survived the classic portal visibility walk. */
void psp_ge_world_capture_visible_sector(int sectnum);
void psp_ge_world_capture_wall(int x1, int x2,
                               int top1, int top2,
                               int bottom1, int bottom2);
void psp_ge_world_capture_textured_wall(int x1, int x2,
                                        const short *uwal, const short *dwal,
                                        const int *swal, const int *lwal,
                                        const short *umost, const short *dmost,
                                        int horiz, int picnum, int pal, int shade,
                                        int xpanning, int yscale, int zd, int shift);
void psp_ge_world_capture_ceiling(int x1, int x2, const short *umost,
                                  const short *dmost, const short *uplc);
void psp_ge_world_capture_floor(int x1, int x2, const short *umost,
                                const short *dmost, const short *dplc);
void psp_ge_world_render(const unsigned short *palette565);

#ifdef __cplusplus
}
#endif

#endif
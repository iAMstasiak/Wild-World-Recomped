#!/usr/bin/env python3
"""Apply acwwrecomp's HD presenter change to the pinned ndsrecomp checkout.

The runner's HD picture (--internal-resolution 2-4) only worked in a GL top
window, but Wild World draws its 3D town on the bottom screen. This adds an
"HD readback" path used whenever there is no GL window: the compute
renderer draws the HD composite of whichever screen shows the 3D engine
offscreen, reads it back and hands it to the normal window as a big
texture. Stacked layout, touch, the settings menu and fullscreen keep
working, and the window scales smoothly instead of by whole steps.

Run tools/patch_ndsrecomp.py first. Safe to run again: edits that are
already there are skipped. Rebuild the runner afterwards:
cmake --build C:\\acww\\ndsrecomp\\runner\\build-acww
"""

from __future__ import annotations

import argparse
from pathlib import Path

GPU2D = "runner/src/gpu2d.cpp"
FRONTEND = "runner/src/frontend.cpp"
HOST = "runner/src/melonds_compute/ComputeHost.cpp"

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    # --- gpu2d: HD surfaces for the bottom screen too -------------------
    ("runner/src/gpu2d.h",
     "void nds_gpu2d_set_hd_emit(bool enabled);\n",
     "void nds_gpu2d_set_hd_emit(bool enabled);\n"
     "void nds_gpu2d_set_hd_any_screen(bool enabled);   // acwwrecomp\n",
     "nds_gpu2d_set_hd_any_screen"),
    (GPU2D,
     "bool g_hd_frame_valid = false;\n",
     "bool g_hd_frame_valid = false;\n"
     "bool g_hd_any_screen = false;   // acwwrecomp: emit for the bottom screen too\n",
     "bool g_hd_any_screen = false;"),
    (GPU2D,
     "        g_hd_emit_enabled && !g_adaptive_skybox_fill && screen == 0 &&\n",
     "        g_hd_emit_enabled && !g_adaptive_skybox_fill &&\n"
     "        (screen == 0 || g_hd_any_screen) &&   // acwwrecomp\n",
     "(screen == 0 || g_hd_any_screen) &&   // acwwrecomp"),
    (GPU2D,
     "void nds_gpu2d_set_hd_emit(bool enabled) {\n",
     "void nds_gpu2d_set_hd_any_screen(bool enabled) {   // acwwrecomp\n"
     "    g_hd_any_screen = enabled;\n"
     "}\n"
     "\n"
     "void nds_gpu2d_set_hd_emit(bool enabled) {\n",
     "void nds_gpu2d_set_hd_any_screen(bool enabled) {"),
    # --- compute host: draw the HD composite offscreen and read it back --
    ("runner/src/melonds_compute/ComputeHost.h",
     "void nds_compute_host_stop();\n",
     "void nds_compute_host_stop();\n"
     "// acwwrecomp: the HD composite of the screen whose HD surfaces the 2D\n"
     "// compositor emitted this frame, as top-down ARGB8888 pixels, or nullptr\n"
     "// when there is no HD frame. Works without a visible GL window.\n"
     "const unsigned int* nds_compute_host_render_hd(unsigned short width,\n"
     "                                              int* out_width,\n"
     "                                              int* out_height);\n",
     "nds_compute_host_render_hd"),
    (HOST,
     "#include <cstring>\n",
     "#include <cstring>\n"
     "#include <vector>   // acwwrecomp\n",
     "#include <vector>   // acwwrecomp"),
    (HOST,
     "void nds_compute_host_stop()\n{\n",
     r'''// acwwrecomp: offscreen HD composite, read back for SDL presentation.
namespace
{
GLuint g_hd_fbo = 0;
GLuint g_hd_color = 0;
int g_hd_fbo_width = 0;
int g_hd_fbo_height = 0;
std::vector<unsigned int> g_hd_rows;
std::vector<unsigned int> g_hd_out;
}

const unsigned int* nds_compute_host_render_hd(unsigned short width,
                                              int* out_width,
                                              int* out_height)
{
    if (!g_active || !out_width || !out_height) return nullptr;
    if (width == 0 || width > 448) return nullptr;
    if (!sdl_make_current(g_window, g_context)) return nullptr;
    if (!g_present_program && !start_presenter()) return nullptr;
    const unsigned int hires = nds_gpu3d_compute_output_texture_hires();
    NdsGpu2dHdFrame hd{};
    if (!hires || !nds_gpu2d_hd_frame(&hd) || hd.width != width ||
        !hd.top_pixels || !hd.below_pixels)
        return nullptr;
    const int scale = nds_gpu3d_internal_scale() > 1
        ? static_cast<int>(nds_gpu3d_internal_scale()) : 1;
    const int w = width * scale;
    const int h = 192 * scale;
    if (g_texture_width != width) {
        for (int i = 0; i < 2; ++i) {
            configure_integer_texture(g_fallback_texture[i], width);
            configure_integer_texture(g_object_texture[i], width);
            configure_layer_texture(g_hd_top_texture[i], width);
            configure_layer_texture(g_hd_below_texture[i], width);
        }
        g_texture_width = width;
    }
    if (!g_hd_fbo || g_hd_fbo_width != w || g_hd_fbo_height != h) {
        if (!g_hd_fbo) {
            glGenFramebuffers(1, &g_hd_fbo);
            glGenTextures(1, &g_hd_color);
        }
        glBindTexture(GL_TEXTURE_2D, g_hd_color);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA,
                     GL_UNSIGNED_BYTE, nullptr);
        glBindFramebuffer(GL_FRAMEBUFFER, g_hd_fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                               GL_TEXTURE_2D, g_hd_color, 0);
        const bool complete = glCheckFramebufferStatus(GL_FRAMEBUFFER) ==
                              GL_FRAMEBUFFER_COMPLETE;
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        if (!complete) {
            std::fprintf(stderr, "[acwwrecomp] HD framebuffer incomplete\n");
            return nullptr;
        }
        g_hd_fbo_width = w;
        g_hd_fbo_height = h;
        g_hd_rows.resize(static_cast<size_t>(w) * h);
        g_hd_out.resize(static_cast<size_t>(w) * h);
    }
    // The renderer can leave its pixel buffers bound (melonDS's capture
    // path does), which would turn the pointers below into buffer offsets.
    GLint previous_pack = 0;
    GLint previous_unpack = 0;
    glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING, &previous_pack);
    glGetIntegerv(GL_PIXEL_UNPACK_BUFFER_BINDING, &previous_unpack);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
    glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0);
    const unsigned buffer = g_present_buffer;
    g_present_buffer ^= 1u;
    glActiveTexture(GL_TEXTURE4);
    glBindTexture(GL_TEXTURE_2D, g_hd_top_texture[buffer]);
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, 192,
                    GL_RG_INTEGER, GL_UNSIGNED_INT, hd.top_pixels);
    glActiveTexture(GL_TEXTURE5);
    glBindTexture(GL_TEXTURE_2D, g_hd_below_texture[buffer]);
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, 192,
                    GL_RG_INTEGER, GL_UNSIGNED_INT, hd.below_pixels);
    glMemoryBarrier(GL_TEXTURE_FETCH_BARRIER_BIT);

    glBindFramebuffer(GL_FRAMEBUFFER, g_hd_fbo);
    glViewport(0, 0, w, h);
    glUseProgram(g_present_program);
    glActiveTexture(GL_TEXTURE1);
    glBindTexture(GL_TEXTURE_2D, g_object_texture[buffer]);
    glActiveTexture(GL_TEXTURE2);
    glBindTexture(GL_TEXTURE_2D, g_fallback_texture[buffer]);
    glActiveTexture(GL_TEXTURE3);
    glBindTexture(GL_TEXTURE_2D, hires);
    glActiveTexture(GL_TEXTURE4);
    glBindTexture(GL_TEXTURE_2D, g_hd_top_texture[buffer]);
    glActiveTexture(GL_TEXTURE5);
    glBindTexture(GL_TEXTURE_2D, g_hd_below_texture[buffer]);
    glUniform1ui(0, 0u);
    glUniform1ui(1, static_cast<GLuint>(width));
    glUniform1ui(11, 1u);
    glUniform1ui(10, static_cast<GLuint>(scale));
    glUniform1ui(12, hd.order_3d);
    glUniform1ui(2, hd.render_xpos);
    glUniform1ui(4, hd.bldcnt);
    glUniform1ui(5, hd.eva);
    glUniform1ui(6, hd.evb);
    glUniform1ui(7, hd.evy);
    glUniform1ui(8, hd.master_bright);
    glUniform1ui(9, hd.priority_3d);
    glBindVertexArray(g_present_vao);
    glDrawArrays(GL_TRIANGLES, 0, 3);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glReadPixels(0, 0, w, h, GL_BGRA, GL_UNSIGNED_BYTE, g_hd_rows.data());
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, static_cast<GLuint>(previous_pack));
    glBindBuffer(GL_PIXEL_UNPACK_BUFFER, static_cast<GLuint>(previous_unpack));
    // GL rows run bottom-up; the SDL texture wants them top-down.
    for (int y = 0; y < h; ++y)
        std::memcpy(&g_hd_out[static_cast<size_t>(y) * w],
                    &g_hd_rows[static_cast<size_t>(h - 1 - y) * w],
                    static_cast<size_t>(w) * sizeof(unsigned int));
    *out_width = w;
    *out_height = h;
    return g_hd_out.data();
}

void nds_compute_host_stop()
{
''',
     "const unsigned int* nds_compute_host_render_hd(unsigned short width,\n"
     "                                              int* out_width,\n"
     "                                              int* out_height)\n{"),
    # --- frontend: show the HD composite through the normal window ------
    (FRONTEND,
     "    int configured_sample_scale = 1;\n"
     "    int sample_scale = 1;\n"
     "};\n",
     "    int configured_sample_scale = 1;\n"
     "    int sample_scale = 1;\n"
     "    // acwwrecomp: HD readback (see update_hd_readback)\n"
     "    bool hd_readback = false;\n"
     "    bool hd_ready[2]{};\n"
     "    SDL_Texture* hd_textures[2]{};\n"
     "    int hd_sizes[2][2]{};\n"
     "};\n",
     "    bool hd_readback = false;\n"),
    (FRONTEND,
     "void destroy_presentation(FrontendPresentation& presentation) {\n",
     "void destroy_presentation(FrontendPresentation& presentation) {\n"
     "    for (SDL_Texture*& texture : presentation.hd_textures) {   // acwwrecomp\n"
     "        if (texture) SDL_DestroyTexture(texture);\n"
     "        texture = nullptr;\n"
     "    }\n",
     "presentation.hd_textures) {   // acwwrecomp"),
    (FRONTEND,
     "    SDL_Texture* source = presentation.textures[screen];\n",
     "    SDL_Texture* source = presentation.textures[screen];\n"
     "    if (presentation.hd_ready[screen] && presentation.hd_textures[screen]) {\n"
     "        // acwwrecomp: the HD composite replaces this screen's texture.\n"
     "        render_texture(renderer, presentation.hd_textures[screen],\n"
     "                       &destination);\n"
     "        return;\n"
     "    }\n",
     "presentation.hd_ready[screen] && presentation.hd_textures[screen]"),
    (FRONTEND,
     "PresentationTicks present_screens(FrontendPresentation& presentation,\n",
     r'''// acwwrecomp: HD without a GL window. The compute host draws the HD
// composite of the screen showing the 3D engine offscreen and reads it back,
// and it is shown through the normal SDL renderer in place of that screen's
// texture, so layouts, touch, overlays and fullscreen all keep working.
void update_hd_readback(FrontendPresentation& presentation, int top_width,
                        int bottom_width, bool top_menu_open) {
    presentation.hd_ready[0] = false;
    presentation.hd_ready[1] = false;
#if defined(NDS_HAVE_COMPUTE_RENDERER)
    if (!presentation.hd_readback) return;
    const int screen = (nds_powercontrol9() & 0x8000u) != 0 ? 0 : 1;
    if (screen == 0 && top_menu_open) return;   // keep the menu visible
    const int width = screen == 0 ? top_width : bottom_width;
    int hd_width = 0;
    int hd_height = 0;
    const unsigned int* pixels = nds_compute_host_render_hd(
        static_cast<unsigned short>(width), &hd_width, &hd_height);
    if (!pixels) return;
    SDL_Texture*& texture = presentation.hd_textures[screen];
    if (!texture || presentation.hd_sizes[screen][0] != hd_width ||
        presentation.hd_sizes[screen][1] != hd_height) {
        if (texture) SDL_DestroyTexture(texture);
        texture = SDL_CreateTexture(presentation.renderers[screen],
                                    SDL_PIXELFORMAT_ARGB8888,
                                    SDL_TEXTUREACCESS_STREAMING,
                                    hd_width, hd_height);
        if (!texture) {
            std::fprintf(stderr, "[acwwrecomp] HD texture failed: %s\n",
                         SDL_GetError());
            presentation.hd_readback = false;
            return;
        }
#if defined(NDS_HAVE_SDL3)
        SDL_SetTextureScaleMode(texture, SDL_SCALEMODE_LINEAR);
#else
        SDL_SetTextureScaleMode(texture, SDL_ScaleModeLinear);
#endif
        presentation.hd_sizes[screen][0] = hd_width;
        presentation.hd_sizes[screen][1] = hd_height;
    }
    SDL_UpdateTexture(texture, nullptr, pixels,
                      hd_width * static_cast<int>(sizeof(uint32_t)));
    presentation.hd_ready[screen] = true;
#else
    (void)top_width;
    (void)bottom_width;
    (void)top_menu_open;
#endif
}

PresentationTicks present_screens(FrontendPresentation& presentation,
''',
     "// acwwrecomp: HD without a GL window."),
    (FRONTEND,
     "    top_pixels = runtime_menu_overlay(\n"
     "        runtime_ui, top_pixels, top_width, kScreenHeight);\n"
     "    uint64_t start = SDL_GetPerformanceCounter();\n"
     "    SDL_UpdateTexture(presentation.textures[0], nullptr, top_pixels,\n"
     "                      top_width * sizeof(uint32_t));\n"
     "    SDL_UpdateTexture(presentation.textures[1], nullptr, bottom_pixels,\n"
     "                      bottom_width * sizeof(uint32_t));\n",
     "    const uint32_t* const top_before_menu = top_pixels;   // acwwrecomp: HD\n"
     "    top_pixels = runtime_menu_overlay(\n"
     "        runtime_ui, top_pixels, top_width, kScreenHeight);\n"
     "    uint64_t start = SDL_GetPerformanceCounter();\n"
     "    SDL_UpdateTexture(presentation.textures[0], nullptr, top_pixels,\n"
     "                      top_width * sizeof(uint32_t));\n"
     "    SDL_UpdateTexture(presentation.textures[1], nullptr, bottom_pixels,\n"
     "                      bottom_width * sizeof(uint32_t));\n"
     "    update_hd_readback(presentation, top_width, bottom_width,\n"
     "                       top_pixels != top_before_menu);   // acwwrecomp: HD\n",
     "top_pixels != top_before_menu);   // acwwrecomp: HD"),
    (FRONTEND,
     "        if (options.adaptive_screens & NDS_ADAPTIVE_BOTTOM)\n"
     "            bottom_pixels =\n"
     "                nds_gpu2d_adaptive_framebuffer(1, &bottom_width);\n",
     "        if (options.adaptive_screens & NDS_ADAPTIVE_BOTTOM)\n"
     "            bottom_pixels =\n"
     "                nds_gpu2d_adaptive_framebuffer(1, &bottom_width);\n"
     "        // acwwrecomp: HD readback needs the compositor's HD surfaces for\n"
     "        // whichever screen shows the 3D engine, at the native width too.\n"
     "        if (presentation.hd_readback &&\n"
     "            !nds_gpu2d_direct_present_frame_active()) {\n"
     "            const int hd_screen =\n"
     "                (nds_powercontrol9() & 0x8000u) != 0 ? 0 : 1;\n"
     "            const unsigned hd_bit = hd_screen == 0\n"
     "                ? static_cast<unsigned>(NDS_ADAPTIVE_TOP)\n"
     "                : static_cast<unsigned>(NDS_ADAPTIVE_BOTTOM);\n"
     "            if ((options.adaptive_screens & hd_bit) == 0u) {\n"
     "                uint16_t hd_width = 256;\n"
     "                nds_gpu2d_adaptive_framebuffer(hd_screen, &hd_width);\n"
     "            }\n"
     "        }\n",
     "        // acwwrecomp: HD readback needs the compositor's HD surfaces for\n"),
    (FRONTEND,
     "    nds_gpu2d_set_direct_present(\n"
     "        nds_compute_host_has_visible_context());\n",
     r'''    nds_gpu2d_set_direct_present(
        nds_compute_host_has_visible_context());
    // acwwrecomp: no GL window, so show the HD picture by reading it back.
    if (options.internal_resolution > 1 && !presentation.gl_top &&
        nds_compute_host_active() && nds_gpu3d_internal_scale() > 1) {
        presentation.hd_readback = true;
        nds_gpu2d_set_hd_any_screen(true);
        nds_gpu2d_set_hd_emit(true);
#if defined(NDS_HAVE_SDL3)
        // Scale smoothly to fill the window rather than by whole steps.
        for (int screen = 0; screen < (presentation.separate ? 2 : 1);
             ++screen) {
            int logical_w = 0;
            int logical_h = 0;
            SDL_RendererLogicalPresentation mode{};
            if (presentation.renderers[screen] &&
                SDL_GetRenderLogicalPresentation(
                    presentation.renderers[screen], &logical_w, &logical_h,
                    &mode))
                SDL_SetRenderLogicalPresentation(
                    presentation.renderers[screen], logical_w, logical_h,
                    SDL_LOGICAL_PRESENTATION_LETTERBOX);
        }
#endif
        std::fprintf(stderr,
                     "[acwwrecomp] HD readback on: %ux 3D in the normal "
                     "window\n",
                     static_cast<unsigned>(nds_gpu3d_internal_scale()));
    }
''',
     "presentation.hd_readback = true;"),
    (FRONTEND,
     "    nds_gpu2d_set_hd_emit(target_scale > 1u && presentation.gl_top);\n",
     "    nds_gpu2d_set_hd_emit(target_scale > 1u &&\n"
     "        (presentation.gl_top || presentation.hd_readback));   // acwwrecomp\n",
     "(presentation.gl_top || presentation.hd_readback));   // acwwrecomp"),
    # --- asynchronous readback, layered on the compute host edit above ---
    # The first version waited for the GPU every frame (about 3 ms). Now each
    # frame's composite goes into one pixel buffer while the previous frame's,
    # long finished, is read from the other.
    (HOST,
     "std::vector<unsigned int> g_hd_out;\n"
     "}\n",
     r'''std::vector<unsigned int> g_hd_out;
GLuint g_hd_pbo[2] = {};
size_t g_hd_pbo_bytes[2] = {};
GLsync g_hd_fence[2] = {};
int g_hd_size[2][2] = {};
int g_hd_slot = 0;

void drop_hd_readbacks()
{
    for (int i = 0; i < 2; ++i) {
        if (g_hd_fence[i]) glDeleteSync(g_hd_fence[i]);
        g_hd_fence[i] = nullptr;
    }
}
}
''',
     "void drop_hd_readbacks()"),
    (HOST,
     "    if (!hires || !nds_gpu2d_hd_frame(&hd) || hd.width != width ||\n"
     "        !hd.top_pixels || !hd.below_pixels)\n"
     "        return nullptr;\n",
     "    if (!hires || !nds_gpu2d_hd_frame(&hd) || hd.width != width ||\n"
     "        !hd.top_pixels || !hd.below_pixels) {\n"
     "        drop_hd_readbacks();   // never show a stale frame later\n"
     "        return nullptr;\n"
     "    }\n",
     "        drop_hd_readbacks();   // never show a stale frame later\n"),
    (HOST,
     r'''    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glReadPixels(0, 0, w, h, GL_BGRA, GL_UNSIGNED_BYTE, g_hd_rows.data());
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, static_cast<GLuint>(previous_pack));
    glBindBuffer(GL_PIXEL_UNPACK_BUFFER, static_cast<GLuint>(previous_unpack));
    // GL rows run bottom-up; the SDL texture wants them top-down.
    for (int y = 0; y < h; ++y)
        std::memcpy(&g_hd_out[static_cast<size_t>(y) * w],
                    &g_hd_rows[static_cast<size_t>(h - 1 - y) * w],
                    static_cast<size_t>(w) * sizeof(unsigned int));
    *out_width = w;
    *out_height = h;
    return g_hd_out.data();
}
''',
     r'''    // Start copying this frame into one pixel buffer; the GPU does it in
    // the background. The HD screen is shown one frame behind as a result.
    if (!g_hd_pbo[0]) glGenBuffers(2, g_hd_pbo);
    const int slot = g_hd_slot;
    const int other = slot ^ 1;
    g_hd_slot = other;
    const size_t bytes = static_cast<size_t>(w) * h * sizeof(unsigned int);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, g_hd_pbo[slot]);
    if (g_hd_pbo_bytes[slot] != bytes) {
        glBufferData(GL_PIXEL_PACK_BUFFER, static_cast<GLsizeiptr>(bytes),
                     nullptr, GL_STREAM_READ);
        g_hd_pbo_bytes[slot] = bytes;
    }
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glReadPixels(0, 0, w, h, GL_BGRA, GL_UNSIGNED_BYTE, nullptr);
    if (g_hd_fence[slot]) glDeleteSync(g_hd_fence[slot]);
    g_hd_fence[slot] = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
    g_hd_size[slot][0] = w;
    g_hd_size[slot][1] = h;
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    // Read the previous frame's buffer, which the GPU finished long ago.
    bool ready = false;
    if (g_hd_fence[other] && g_hd_size[other][0] == w &&
        g_hd_size[other][1] == h) {
        const GLenum wait = glClientWaitSync(
            g_hd_fence[other], GL_SYNC_FLUSH_COMMANDS_BIT, 20000000ull);
        if (wait == GL_ALREADY_SIGNALED || wait == GL_CONDITION_SATISFIED) {
            glBindBuffer(GL_PIXEL_PACK_BUFFER, g_hd_pbo[other]);
            const unsigned int* src = static_cast<const unsigned int*>(
                glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0,
                                 static_cast<GLsizeiptr>(bytes),
                                 GL_MAP_READ_BIT));
            if (src) {
                // GL rows run bottom-up; the SDL texture wants them top-down.
                for (int y = 0; y < h; ++y)
                    std::memcpy(&g_hd_out[static_cast<size_t>(y) * w],
                                src + static_cast<size_t>(h - 1 - y) * w,
                                static_cast<size_t>(w) * sizeof(unsigned int));
                glUnmapBuffer(GL_PIXEL_PACK_BUFFER);
                ready = true;
            }
        }
        glDeleteSync(g_hd_fence[other]);
        g_hd_fence[other] = nullptr;
    }
    glBindBuffer(GL_PIXEL_PACK_BUFFER, static_cast<GLuint>(previous_pack));
    glBindBuffer(GL_PIXEL_UNPACK_BUFFER, static_cast<GLuint>(previous_unpack));
    if (!ready) return nullptr;
    *out_width = w;
    *out_height = h;
    return g_hd_out.data();
}
''',
     "glReadPixels(0, 0, w, h, GL_BGRA, GL_UNSIGNED_BYTE, nullptr);"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(r"C:\acww\ndsrecomp"))
    args = parser.parse_args()

    texts: dict[str, tuple[str, bool]] = {}
    for rel, *_ in EDITS:
        if rel not in texts:
            raw = (args.root / rel).read_bytes().decode("utf-8")
            texts[rel] = (raw.replace("\r\n", "\n"), "\r\n" in raw)

    changed = set()
    for rel, old, new, marker in EDITS:
        text, crlf = texts[rel]
        if marker in text:
            print(f"  already there: {rel}: {marker.strip()[:60]}")
            continue
        if text.count(old) != 1:
            raise SystemExit(f"{rel}: expected exactly one '{old.strip()[:60]}' "
                             f"(found {text.count(old)}); nothing was changed")
        texts[rel] = (text.replace(old, new), crlf)
        changed.add(rel)
        print(f"  patched: {rel}: {marker.strip()[:60]}")

    for rel in sorted(changed):
        text, crlf = texts[rel]
        out = text.replace("\n", "\r\n") if crlf else text
        (args.root / rel).write_bytes(out.encode("utf-8"))
    print(f"{len(changed)} file(s) changed" + ("; now rebuild the runner" if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

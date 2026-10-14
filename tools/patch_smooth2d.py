#!/usr/bin/env python3
"""Apply acwwrecomp's 2D smoothing (sharp xBR) to the pinned ndsrecomp checkout.

Sharp xBR redraws the staircase edges of 2D pixel art (text, name tags,
bubbles, menus, the sky) as smooth lines at the HD scale. It only picks
which neighbouring pixel each output pixel copies, never blends, so on the
3D screen the DS layer data travels with the pixel and the HD 3D still sits
correctly in front of or behind every 2D layer. A screen with no HD picture
(the sky, menus without 3D) is smoothed as a whole.

On when ACWW_SMOOTH_2D=xbr is set (play.ps1 -HD does this unless -NoSmooth);
the G key flips it on and off while playing.

Run tools/patch_ndsrecomp.py and tools/patch_hd.py first. Safe to run
again: edits that are already there are skipped. Rebuild the runner
afterwards: cmake --build C:\\acww\\ndsrecomp\\runner\\build-acww
"""

from __future__ import annotations

import argparse
from pathlib import Path

FRONTEND = "runner/src/frontend.cpp"
HOST = "runner/src/melonds_compute/ComputeHost.cpp"

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    # --- present shader: the xBR pick, for HD 2D layers and plain screens --
    (HOST,
     "layout(location = 12) uniform uint order3d;\n",
     "layout(location = 12) uniform uint order3d;\n"
     "// acwwrecomp: sharp xBR on the 2D layers (13) or a whole plain screen (14).\n"
     "layout(location = 13) uniform uint smooth2d;\n"
     "layout(location = 14) uniform uint plainSmooth;\n",
     "layout(location = 13) uniform uint smooth2d;"),
    (HOST,
     "void main()\n{\n    ivec2 size = textureSize(texFallback, 0);\n",
     r'''// acwwrecomp: sharp xBR-lv2 (corner C, libretro rules). It only ever
// chooses which neighbouring native pixel an output sample copies, so the
// DS layer data (priority, blend targets) travels with the pixel.
vec3 xbrColor(usampler2D tex, bool packedLayer, ivec2 p)
{
    p = clamp(p, ivec2(0), textureSize(tex, 0) - ivec2(1));
    uvec4 t = texelFetch(tex, p, 0);
    if (packedLayer)
        return vec3(float(t.x & 63u), float((t.x >> 8) & 63u),
                    float((t.x >> 16) & 63u)) / 63.0;
    return vec3(t.rgb) / 255.0;
}

float xbrLum(usampler2D tex, bool packedLayer, ivec2 p)
{
    return dot(xbrColor(tex, packedLayer, p),
               vec3(0.2126, 0.7152, 0.0722)) * 48.0;
}

vec4 xbrDf(vec4 a, vec4 b) { return abs(a - b); }
vec4 xbrEq(vec4 a, vec4 b) { return vec4(lessThan(abs(a - b), vec4(15.0))); }
vec4 xbrNeq(vec4 a, vec4 b) { return vec4(1.0) - xbrEq(a, b); }
vec4 xbrWd(vec4 a, vec4 b, vec4 c, vec4 d, vec4 e, vec4 f, vec4 g, vec4 h)
{
    return xbrDf(a, b) + xbrDf(a, c) + xbrDf(d, e) + xbrDf(d, f) +
           4.0 * xbrDf(g, h);
}

// The native pixel that the output sample at fp (0..1 inside p) copies.
ivec2 xbrPick(usampler2D tex, bool packedLayer, ivec2 p, vec2 fp)
{
    vec3 cE = xbrColor(tex, packedLayer, p);
    float lE = dot(cE, vec3(0.2126, 0.7152, 0.0722)) * 48.0;
    vec4 b = vec4(xbrLum(tex, packedLayer, p + ivec2(0, -1)),
                  xbrLum(tex, packedLayer, p + ivec2(-1, 0)),
                  xbrLum(tex, packedLayer, p + ivec2(0, 1)),
                  xbrLum(tex, packedLayer, p + ivec2(1, 0)));
    vec4 c = vec4(xbrLum(tex, packedLayer, p + ivec2(1, -1)),
                  xbrLum(tex, packedLayer, p + ivec2(-1, -1)),
                  xbrLum(tex, packedLayer, p + ivec2(-1, 1)),
                  xbrLum(tex, packedLayer, p + ivec2(1, 1)));
    vec4 i4 = vec4(xbrLum(tex, packedLayer, p + ivec2(2, 1)),
                   xbrLum(tex, packedLayer, p + ivec2(1, -2)),
                   xbrLum(tex, packedLayer, p + ivec2(-2, -1)),
                   xbrLum(tex, packedLayer, p + ivec2(-1, 2)));
    vec4 i5 = vec4(xbrLum(tex, packedLayer, p + ivec2(1, 2)),
                   xbrLum(tex, packedLayer, p + ivec2(2, -1)),
                   xbrLum(tex, packedLayer, p + ivec2(-1, -2)),
                   xbrLum(tex, packedLayer, p + ivec2(-2, 1)));
    vec4 h5 = vec4(xbrLum(tex, packedLayer, p + ivec2(0, 2)),
                   xbrLum(tex, packedLayer, p + ivec2(2, 0)),
                   xbrLum(tex, packedLayer, p + ivec2(0, -2)),
                   xbrLum(tex, packedLayer, p + ivec2(-2, 0)));
    vec4 e = vec4(lE);
    vec4 d = b.yzwx, f = b.wxyz, h = b.zwxy;
    vec4 g = c.zwxy, i = c.wxyz;
    vec4 f4 = h5.yzwx;

    vec4 lv0 = vec4(notEqual(e, f)) * vec4(notEqual(e, h));
    vec4 lv1 = min(lv0 * (xbrNeq(f, b) * xbrNeq(f, c) +
                          xbrNeq(h, d) * xbrNeq(h, g) +
                          xbrEq(e, i) * (xbrNeq(f, f4) * xbrNeq(f, i4) +
                                         xbrNeq(h, h5) * xbrNeq(h, i5)) +
                          xbrEq(e, g) + xbrEq(e, c)), vec4(1.0));
    vec4 lv2l = vec4(notEqual(e, g)) * vec4(notEqual(d, g));
    vec4 lv2u = vec4(notEqual(e, c)) * vec4(notEqual(b, c));
    vec4 wd1 = xbrWd(e, c, g, i, h5, f4, h, f);
    vec4 wd2 = xbrWd(h, d, i5, f, i4, b, e, i);
    vec4 edri = vec4(lessThanEqual(wd1, wd2)) * lv0;
    vec4 edr = vec4(lessThan(wd1, wd2)) * lv1;
    vec4 edrl = vec4(lessThanEqual(2.0 * xbrDf(f, g), xbrDf(h, c))) * lv2l * edr;
    vec4 edru = vec4(greaterThanEqual(xbrDf(f, g), 2.0 * xbrDf(h, c))) * lv2u * edr;
    vec4 px = vec4(lessThanEqual(xbrDf(e, f), xbrDf(e, h)));

    const vec4 Ao = vec4(1.0, -1.0, -1.0, 1.0), Bo = vec4(1.0, 1.0, -1.0, -1.0);
    const vec4 Co = vec4(1.5, 0.5, -0.5, 0.5);
    const vec4 Ax = vec4(1.0, -1.0, -1.0, 1.0), Bx = vec4(0.5, 2.0, -0.5, -2.0);
    const vec4 Cx = vec4(1.0, 1.0, -0.5, 0.0);
    const vec4 Ay = vec4(1.0, -1.0, -1.0, 1.0), By = vec4(2.0, 0.5, -2.0, -0.5);
    const vec4 Cy = vec4(2.0, 0.0, -1.0, 0.5);
    vec4 fx = Ao * fp.y + Bo * fp.x;
    vec4 fxl = Ax * fp.y + Bx * fp.x;
    vec4 fxu = Ay * fp.y + By * fp.x;
    vec4 m = max(max(step(Cx, fxl) * edrl, step(Cy, fxu) * edru),
                 max(step(Co, fx) * edr, step(Co + vec4(0.25), fx) * edri));

    ivec2 o1 = ivec2(0);
    ivec2 o2 = ivec2(0);
    if (m.x > 0.5) o1 = px.x > 0.5 ? ivec2(1, 0) : ivec2(0, 1);
    if (m.z > 0.5) o1 = px.z > 0.5 ? ivec2(-1, 0) : ivec2(0, -1);
    if (m.y > 0.5) o2 = px.y > 0.5 ? ivec2(0, -1) : ivec2(1, 0);
    if (m.w > 0.5) o2 = px.w > 0.5 ? ivec2(0, 1) : ivec2(-1, 0);
    float d1 = dot(abs(xbrColor(tex, packedLayer, p + o1) - cE), vec3(1.0));
    float d2 = dot(abs(xbrColor(tex, packedLayer, p + o2) - cE), vec3(1.0));
    return p + (d1 <= d2 ? o2 : o1);
}

void main()
{
    ivec2 size = textureSize(texFallback, 0);
''',
     "ivec2 xbrPick(usampler2D tex, bool packedLayer, ivec2 p, vec2 fp)"),
    (HOST,
     "        Layer top = unpackLayer(texelFetch(texHdTop, dst, 0).xy);\n"
     "        Layer below = unpackLayer(texelFetch(texHdBelow, dst, 0).xy);\n",
     r'''        ivec2 src2d = dst;
        if (smooth2d != 0u) {
            // acwwrecomp: sharp xBR picks which native 2D pixel this
            // sample copies; the HD 3D is still inserted per sample.
            ivec2 nat = dstHi / s;
            vec2 fp2 = (vec2(dstHi - nat * s) + vec2(0.5)) / float(s);
            src2d = clamp(xbrPick(texHdTop, true, nat, fp2), ivec2(0),
                          size - ivec2(1));
        }
        Layer top = unpackLayer(texelFetch(texHdTop, src2d, 0).xy);
        Layer below = unpackLayer(texelFetch(texHdBelow, src2d, 0).xy);
''',
     "Layer top = unpackLayer(texelFetch(texHdTop, src2d, 0).xy);"),
    (HOST,
     "    if (directMode == 0u) {\n"
     "        uvec4 pixel = texelFetch(texFallback, dst, 0);\n",
     r'''    if (plainSmooth != 0u) {
        // acwwrecomp: a whole screen with no HD picture, through sharp xBR.
        int s = int(max(scale3d, 1u));
        ivec2 hiSize = size * s;
        ivec2 dstHi = ivec2(clamp(uv * vec2(hiSize), vec2(0.0),
                                  vec2(hiSize) - vec2(1.0)));
        ivec2 nat = dstHi / s;
        vec2 fp2 = (vec2(dstHi - nat * s) + vec2(0.5)) / float(s);
        ivec2 pick = clamp(xbrPick(texFallback, false, nat, fp2), ivec2(0),
                           size - ivec2(1));
        outColor = vec4(vec3(texelFetch(texFallback, pick, 0).rgb) / 255.0, 1.0);
        return;
    }
    if (directMode == 0u) {
        uvec4 pixel = texelFetch(texFallback, dst, 0);
''',
     "    if (plainSmooth != 0u) {\n"),
    # --- compute host: smoothing switch, HD uniforms, plain-screen pass ---
    (HOST,
     "int g_hd_slot = 0;\n",
     "int g_hd_slot = 0;\n"
     "bool g_smooth_2d = false;   // acwwrecomp: sharp xBR on 2D\n",
     "bool g_smooth_2d = false;"),
    (HOST,
     "    glUniform1ui(9, hd.priority_3d);\n"
     "    glBindVertexArray(g_present_vao);\n",
     "    glUniform1ui(9, hd.priority_3d);\n"
     "    glUniform1ui(13, g_smooth_2d ? 1u : 0u);   // acwwrecomp: 2D smoothing\n"
     "    glUniform1ui(14, 0u);\n"
     "    glBindVertexArray(g_present_vao);\n",
     "glUniform1ui(13, g_smooth_2d ? 1u : 0u);"),
    (HOST,
     "void nds_compute_host_stop()\n{\n",
     r'''// acwwrecomp: a screen with no HD picture, smoothed with sharp xBR
// offscreen and read back the same way as the HD composite.
namespace
{
struct SmoothTarget {
    GLuint source = 0;
    int source_width = 0;
    GLuint fbo = 0;
    GLuint color = 0;
    int width = 0;
    int height = 0;
    GLuint pbo[2] = {};
    size_t pbo_bytes[2] = {};
    GLsync fence[2] = {};
    int size[2][2] = {};
    int slot = 0;
    std::vector<unsigned int> out;
};
SmoothTarget g_smooth_target[2];
}

void nds_compute_host_set_smooth_2d(bool enabled)
{
    g_smooth_2d = enabled;
}

const unsigned int* nds_compute_host_render_smooth(int screen,
                                                  const unsigned int* pixels,
                                                  unsigned short width,
                                                  int scale,
                                                  int* out_width,
                                                  int* out_height)
{
    if (!g_active || !pixels || !out_width || !out_height) return nullptr;
    if (screen < 0 || screen > 1 || width == 0 || width > 448 || scale < 2)
        return nullptr;
    if (!sdl_make_current(g_window, g_context)) return nullptr;
    if (!g_present_program && !start_presenter()) return nullptr;
    SmoothTarget& t = g_smooth_target[screen];
    const int w = width * scale;
    const int h = 192 * scale;
    GLint previous_pack = 0;
    GLint previous_unpack = 0;
    glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING, &previous_pack);
    glGetIntegerv(GL_PIXEL_UNPACK_BUFFER_BINDING, &previous_unpack);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
    glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0);
    auto restore = [&]() {
        glBindBuffer(GL_PIXEL_PACK_BUFFER, static_cast<GLuint>(previous_pack));
        glBindBuffer(GL_PIXEL_UNPACK_BUFFER,
                     static_cast<GLuint>(previous_unpack));
    };
    if (!t.source) glGenTextures(1, &t.source);
    if (t.source_width != width) {
        configure_integer_texture(t.source, width);
        t.source_width = width;
    }
    glActiveTexture(GL_TEXTURE2);
    glBindTexture(GL_TEXTURE_2D, t.source);
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, 192,
                    GL_BGRA_INTEGER, GL_UNSIGNED_BYTE, pixels);
    if (!t.fbo || t.width != w || t.height != h) {
        if (!t.fbo) {
            glGenFramebuffers(1, &t.fbo);
            glGenTextures(1, &t.color);
        }
        glBindTexture(GL_TEXTURE_2D, t.color);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA,
                     GL_UNSIGNED_BYTE, nullptr);
        glBindFramebuffer(GL_FRAMEBUFFER, t.fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                               GL_TEXTURE_2D, t.color, 0);
        const bool complete = glCheckFramebufferStatus(GL_FRAMEBUFFER) ==
                              GL_FRAMEBUFFER_COMPLETE;
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        if (!complete) {
            restore();
            return nullptr;
        }
        for (int k = 0; k < 2; ++k) {
            if (t.fence[k]) glDeleteSync(t.fence[k]);
            t.fence[k] = nullptr;
        }
        t.width = w;
        t.height = h;
        t.out.resize(static_cast<size_t>(w) * h);
    }
    glBindFramebuffer(GL_FRAMEBUFFER, t.fbo);
    glViewport(0, 0, w, h);
    glUseProgram(g_present_program);
    glActiveTexture(GL_TEXTURE2);
    glBindTexture(GL_TEXTURE_2D, t.source);
    glUniform1ui(0, 0u);
    glUniform1ui(1, static_cast<GLuint>(width));
    glUniform1ui(10, static_cast<GLuint>(scale));
    glUniform1ui(11, 0u);
    glUniform1ui(13, 0u);
    glUniform1ui(14, 1u);
    glBindVertexArray(g_present_vao);
    glDrawArrays(GL_TRIANGLES, 0, 3);
    glUniform1ui(14, 0u);

    if (!t.pbo[0]) glGenBuffers(2, t.pbo);
    const int slot = t.slot;
    const int other = slot ^ 1;
    t.slot = other;
    const size_t bytes = static_cast<size_t>(w) * h * sizeof(unsigned int);
    glBindBuffer(GL_PIXEL_PACK_BUFFER, t.pbo[slot]);
    if (t.pbo_bytes[slot] != bytes) {
        glBufferData(GL_PIXEL_PACK_BUFFER, static_cast<GLsizeiptr>(bytes),
                     nullptr, GL_STREAM_READ);
        t.pbo_bytes[slot] = bytes;
    }
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    glReadPixels(0, 0, w, h, GL_BGRA, GL_UNSIGNED_BYTE, nullptr);
    if (t.fence[slot]) glDeleteSync(t.fence[slot]);
    t.fence[slot] = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
    t.size[slot][0] = w;
    t.size[slot][1] = h;
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    bool ready = false;
    if (t.fence[other] && t.size[other][0] == w && t.size[other][1] == h) {
        const GLenum wait = glClientWaitSync(
            t.fence[other], GL_SYNC_FLUSH_COMMANDS_BIT, 20000000ull);
        if (wait == GL_ALREADY_SIGNALED || wait == GL_CONDITION_SATISFIED) {
            glBindBuffer(GL_PIXEL_PACK_BUFFER, t.pbo[other]);
            const unsigned int* src = static_cast<const unsigned int*>(
                glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0,
                                 static_cast<GLsizeiptr>(bytes),
                                 GL_MAP_READ_BIT));
            if (src) {
                for (int y = 0; y < h; ++y)
                    std::memcpy(&t.out[static_cast<size_t>(y) * w],
                                src + static_cast<size_t>(h - 1 - y) * w,
                                static_cast<size_t>(w) * sizeof(unsigned int));
                glUnmapBuffer(GL_PIXEL_PACK_BUFFER);
                ready = true;
            }
        }
        glDeleteSync(t.fence[other]);
        t.fence[other] = nullptr;
    }
    restore();
    if (!ready) return nullptr;
    *out_width = w;
    *out_height = h;
    return t.out.data();
}

void nds_compute_host_stop()
{
''',
     "const unsigned int* nds_compute_host_render_smooth(int screen,"),
    ("runner/src/melonds_compute/ComputeHost.h",
     "                                              int* out_height);\n",
     "                                              int* out_height);\n"
     "// acwwrecomp: sharp xBR 2D smoothing. The switch applies to the HD\n"
     "// composite; render_smooth smooths a whole screen that has no HD picture\n"
     "// (top-down ARGB8888 at width*scale x 192*scale, one frame behind).\n"
     "void nds_compute_host_set_smooth_2d(bool enabled);\n"
     "const unsigned int* nds_compute_host_render_smooth(int screen,\n"
     "                                                  const unsigned int* pixels,\n"
     "                                                  unsigned short width,\n"
     "                                                  int scale,\n"
     "                                                  int* out_width,\n"
     "                                                  int* out_height);\n",
     "nds_compute_host_render_smooth"),
    # --- frontend: smooth both screens, the switch, the G key ------------
    (FRONTEND,
     "    int hd_sizes[2][2]{};\n",
     "    int hd_sizes[2][2]{};\n"
     "    bool smooth_2d = false;   // acwwrecomp: sharp xBR on 2D (G flips it)\n",
     "    bool smooth_2d = false;"),
    (FRONTEND,
     r'''void update_hd_readback(FrontendPresentation& presentation, int top_width,
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
''',
     r'''void update_hd_readback(FrontendPresentation& presentation,
                        const uint32_t* top_pixels, int top_width,
                        const uint32_t* bottom_pixels, int bottom_width,
                        bool top_menu_open) {
    presentation.hd_ready[0] = false;
    presentation.hd_ready[1] = false;
#if defined(NDS_HAVE_COMPUTE_RENDERER)
    if (!presentation.hd_readback) return;
    nds_compute_host_set_smooth_2d(presentation.smooth_2d);
    const int hd_screen = (nds_powercontrol9() & 0x8000u) != 0 ? 0 : 1;
    const int scale = static_cast<int>(nds_gpu3d_internal_scale());
    // acwwrecomp: the 3D screen gets the HD composite; a screen without one
    // (the sky, a menu with no 3D) is smoothed whole when 2D smoothing is on.
    for (int screen = 0; screen < 2; ++screen) {
    if (screen == 0 && top_menu_open) continue;   // keep the menu visible
    const int width = screen == 0 ? top_width : bottom_width;
    const uint32_t* native = screen == 0 ? top_pixels : bottom_pixels;
    int hd_width = 0;
    int hd_height = 0;
    const unsigned int* pixels = nullptr;
    if (screen == hd_screen)
        pixels = nds_compute_host_render_hd(
            static_cast<unsigned short>(width), &hd_width, &hd_height);
    if (!pixels && presentation.smooth_2d && native && scale >= 2)
        pixels = nds_compute_host_render_smooth(
            screen, native, static_cast<unsigned short>(width), scale,
            &hd_width, &hd_height);
    if (!pixels) continue;
    SDL_Texture*& texture = presentation.hd_textures[screen];
''',
     "nds_compute_host_set_smooth_2d(presentation.smooth_2d);"),
    (FRONTEND,
     r'''            presentation.hd_readback = false;
            return;
        }
''',
     r'''            presentation.hd_readback = false;
            return;
        }
        SDL_SetTextureBlendMode(texture, SDL_BLENDMODE_NONE);   // acwwrecomp
''',
     "SDL_SetTextureBlendMode(texture, SDL_BLENDMODE_NONE);   // acwwrecomp"),
    (FRONTEND,
     r'''    SDL_UpdateTexture(texture, nullptr, pixels,
                      hd_width * static_cast<int>(sizeof(uint32_t)));
    presentation.hd_ready[screen] = true;
#else
    (void)top_width;
    (void)bottom_width;
    (void)top_menu_open;
#endif
}
''',
     r'''    SDL_UpdateTexture(texture, nullptr, pixels,
                      hd_width * static_cast<int>(sizeof(uint32_t)));
    presentation.hd_ready[screen] = true;
    }   // acwwrecomp: end of the per-screen loop
#else
    (void)top_pixels;
    (void)top_width;
    (void)bottom_pixels;
    (void)bottom_width;
    (void)top_menu_open;
#endif
}
''',
     "    }   // acwwrecomp: end of the per-screen loop\n"),
    (FRONTEND,
     "    update_hd_readback(presentation, top_width, bottom_width,\n"
     "                       top_pixels != top_before_menu);   // acwwrecomp: HD\n",
     "    update_hd_readback(presentation, top_pixels, top_width,\n"
     "                       bottom_pixels, bottom_width,\n"
     "                       top_pixels != top_before_menu);   // acwwrecomp: HD\n",
     "update_hd_readback(presentation, top_pixels, top_width,"),
    (FRONTEND,
     "        presentation.hd_readback = true;\n"
     "        nds_gpu2d_set_hd_any_screen(true);\n",
     "        presentation.hd_readback = true;\n"
     "        nds_gpu2d_set_hd_any_screen(true);\n"
     "        const char* smooth = std::getenv(\"ACWW_SMOOTH_2D\");   // acwwrecomp\n"
     "        presentation.smooth_2d = smooth && std::strcmp(smooth, \"xbr\") == 0;\n"
     "        std::fprintf(stderr, \"[acwwrecomp] 2D smoothing: %s (G to switch)\\n\",\n"
     "                     presentation.smooth_2d ? \"sharp xBR\" : \"off\");\n",
     "std::getenv(\"ACWW_SMOOTH_2D\");   // acwwrecomp"),
    (FRONTEND,
     "            if (event.type == SDL_KEYDOWN && !event.key.repeat) {\n"
     "                const SDL_Scancode scancode = sdl_event_scancode(event);\n"
     "                NdsSavestateSlotCommand state_command{};\n",
     r'''            if (event.type == SDL_KEYDOWN && !event.key.repeat &&
                sdl_event_scancode(event) == SDL_SCANCODE_G &&
                presentation.hd_readback) {
                // acwwrecomp: G flips 2D smoothing while playing.
                presentation.smooth_2d = !presentation.smooth_2d;
                savestate_notice = presentation.smooth_2d
                    ? "2D smoothing: sharp xBR" : "2D smoothing: off";
                savestate_notice_until =
                    SDL_GetPerformanceCounter() + frequency * 2u;
                std::fprintf(stderr, "[acwwrecomp] %s\n",
                             savestate_notice.c_str());
                continue;
            }
            if (event.type == SDL_KEYDOWN && !event.key.repeat) {
                const SDL_Scancode scancode = sdl_event_scancode(event);
                NdsSavestateSlotCommand state_command{};
''',
     "// acwwrecomp: G flips 2D smoothing while playing."),
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

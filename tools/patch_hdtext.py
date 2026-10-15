#!/usr/bin/env python3
"""Add HD letters to the pinned ndsrecomp checkout.

Wild World paints its letters into the tiles of a 2D layer. The runner now
reads them back off the layer, matching the game's own font (fontA, read
from the ROM) exactly, and draws them again as smooth HD strokes in the HD
picture of both screens. Everything else keeps the 2D smoothing.

On when ACWW_HD_TEXT=on is set (play.ps1 -HD does this unless -NoHDText);
the T key flips it while playing. The reading and drawing live in
tools/acww_hdtext.h, which this copies into the runner.

Run after patch_ndsrecomp.py, patch_hd.py, patch_smooth2d.py and
patch_branding.py. Safe to run again: edits that are already there are
skipped, and the header is refreshed. Rebuild the runner afterwards:
cmake --build C:\\acww\\ndsrecomp\\runner\\build-acww
"""

from __future__ import annotations

import argparse
from pathlib import Path

FRONTEND = "runner/src/frontend.cpp"
HOST = "runner/src/melonds_compute/ComputeHost.cpp"
HEADER = Path(__file__).with_name("acww_hdtext.h")

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    # --- gpu2d: the BG registers the letters are read with ---------------
    ("runner/src/gpu2d.h",
     "void nds_gpu2d_set_hd_any_screen(bool enabled);   // acwwrecomp\n",
     "void nds_gpu2d_set_hd_any_screen(bool enabled);   // acwwrecomp\n"
     "// acwwrecomp: the BG registers the HD letters read (patch_hdtext.py).\n"
     "void nds_gpu2d_text_regs(int engine, uint32_t* dispcnt, uint16_t* bgcnt,\n"
     "                         uint16_t* bgx, uint16_t* bgy);\n",
     "void nds_gpu2d_text_regs("),
    ("runner/src/gpu2d.cpp",
     "void nds_gpu2d_set_hd_any_screen(bool enabled) {   // acwwrecomp\n",
     "void nds_gpu2d_text_regs(int engine, uint32_t* dispcnt, uint16_t* bgcnt,\n"
     "                         uint16_t* bgx, uint16_t* bgy) {   // acwwrecomp\n"
     "    const Unit& u = g_unit[engine & 1];\n"
     "    *dispcnt = u.dispcnt;\n"
     "    for (int i = 0; i < 4; ++i) {\n"
     "        bgcnt[i] = u.bgcnt[i];\n"
     "        bgx[i] = u.bgx[i];\n"
     "        bgy[i] = u.bgy[i];\n"
     "    }\n"
     "}\n"
     "\n"
     "void nds_gpu2d_set_hd_any_screen(bool enabled) {   // acwwrecomp\n",
     "void nds_gpu2d_text_regs(int engine, uint32_t* dispcnt, uint16_t* bgcnt,\n"
     "                         uint16_t* bgx, uint16_t* bgy) {   // acwwrecomp"),

    # --- compute host: the letter pictures and the shader that uses them --
    ("runner/src/melonds_compute/ComputeHost.h",
     "void nds_compute_host_set_smooth_2d(bool enabled);\n",
     "void nds_compute_host_set_smooth_2d(bool enabled);\n"
     "// acwwrecomp: HD letters. mask is width x 192 bytes (non-zero: the HD\n"
     "// letters own that native pixel), hd is (width*scale) x (192*scale) ARGB;\n"
     "// nullptr switches the screen off. set_text_screen picks the screen the\n"
     "// next render_hd draws; set_plain_mode: 1 = sharp xBR, 2 = no smoothing.\n"
     "void nds_compute_host_set_hd_text(int screen, const unsigned char* mask,\n"
     "                                  const unsigned int* hd, int width,\n"
     "                                  int scale);\n"
     "void nds_compute_host_set_text_screen(int screen);\n"
     "void nds_compute_host_set_plain_mode(unsigned int mode);\n",
     "void nds_compute_host_set_hd_text(int screen,"),
    (HOST,
     "layout(location = 14) uniform uint plainSmooth;\n",
     "layout(location = 14) uniform uint plainSmooth;\n"
     "// acwwrecomp: HD letters (15): the pixels they own, and the letters.\n"
     "layout(location = 15) uniform uint hdText;\n"
     "layout(binding = 6) uniform usampler2D texTextMask;\n"
     "layout(binding = 7) uniform sampler2D texTextHd;\n",
     "layout(location = 15) uniform uint hdText;"),
    (HOST,
     "    if (hdMode != 0u) {\n"
     "        int s = int(max(scale3d, 1u));\n"
     "        ivec2 hiSize = size * s;\n"
     "        ivec2 dstHi = ivec2(clamp(uv * vec2(hiSize), vec2(0.0),\n"
     "                                  vec2(hiSize) - vec2(1.0)));\n",
     "    if (hdMode != 0u) {\n"
     "        int s = int(max(scale3d, 1u));\n"
     "        ivec2 hiSize = size * s;\n"
     "        ivec2 dstHi = ivec2(clamp(uv * vec2(hiSize), vec2(0.0),\n"
     "                                  vec2(hiSize) - vec2(1.0)));\n"
     "        if (hdText != 0u && texelFetch(texTextMask, dstHi / s, 0).r != 0u) {\n"
     "            // acwwrecomp: an HD letter owns this pixel.\n"
     "            outColor = vec4(texelFetch(texTextHd, dstHi, 0).rgb, 1.0);\n"
     "            return;\n"
     "        }\n",
     "// acwwrecomp: an HD letter owns this pixel."),
    (HOST,
     "        ivec2 pick = clamp(xbrPick(texFallback, false, nat, fp2), ivec2(0),\n"
     "                           size - ivec2(1));\n",
     "        if (hdText != 0u && texelFetch(texTextMask, nat, 0).r != 0u) {\n"
     "            // acwwrecomp: an HD letter owns this pixel (plain screen).\n"
     "            outColor = vec4(texelFetch(texTextHd, dstHi, 0).rgb, 1.0);\n"
     "            return;\n"
     "        }\n"
     "        ivec2 pick = plainSmooth == 1u\n"
     "            ? clamp(xbrPick(texFallback, false, nat, fp2), ivec2(0),\n"
     "                    size - ivec2(1))\n"
     "            : nat;\n",
     "// acwwrecomp: an HD letter owns this pixel (plain screen)."),
    (HOST,
     "bool g_smooth_2d = false;   // acwwrecomp: sharp xBR on 2D\n",
     r'''bool g_smooth_2d = false;   // acwwrecomp: sharp xBR on 2D
// acwwrecomp: HD letters per screen (patch_hdtext.py).
struct TextTextures {
    GLuint mask = 0;
    GLuint hd = 0;
    int width = 0;
    int scale = 0;
    bool on = false;
};
TextTextures g_text[2];
int g_text_screen = -1;
GLuint g_plain_mode = 1u;

void bind_text(int screen, int width, int scale)
{
    const TextTextures* t =
        (screen >= 0 && screen < 2 && g_text[screen].on &&
         g_text[screen].width == width && g_text[screen].scale == scale)
            ? &g_text[screen] : nullptr;
    glActiveTexture(GL_TEXTURE6);
    glBindTexture(GL_TEXTURE_2D, t ? t->mask : 0u);
    glActiveTexture(GL_TEXTURE7);
    glBindTexture(GL_TEXTURE_2D, t ? t->hd : 0u);
    glUniform1ui(15, t ? 1u : 0u);
}
''',
     "// acwwrecomp: HD letters per screen (patch_hdtext.py)."),
    (HOST,
     "void nds_compute_host_set_smooth_2d(bool enabled)\n{\n",
     r'''// acwwrecomp: hands the HD letters of one screen to the GPU.
void nds_compute_host_set_hd_text(int screen, const unsigned char* mask,
                                  const unsigned int* hd, int width, int scale)
{
    if (screen < 0 || screen > 1) return;
    TextTextures& t = g_text[screen];
    t.on = false;
    if (!mask || !hd || width <= 0 || width > 448 || scale < 1 || !g_active)
        return;
    if (!sdl_make_current(g_window, g_context)) return;
    GLint previous_unpack = 0;
    GLint previous_align = 4;
    GLint previous_unit = GL_TEXTURE0;
    glGetIntegerv(GL_PIXEL_UNPACK_BUFFER_BINDING, &previous_unpack);
    glGetIntegerv(GL_UNPACK_ALIGNMENT, &previous_align);
    glGetIntegerv(GL_ACTIVE_TEXTURE, &previous_unit);
    glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    if (!t.mask) {
        glGenTextures(1, &t.mask);
        glGenTextures(1, &t.hd);
    }
    const bool resize = t.width != width || t.scale != scale;
    glActiveTexture(GL_TEXTURE6);
    glBindTexture(GL_TEXTURE_2D, t.mask);
    if (resize) {
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_R8UI, width, 192, 0,
                     GL_RED_INTEGER, GL_UNSIGNED_BYTE, mask);
    } else {
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width, 192,
                        GL_RED_INTEGER, GL_UNSIGNED_BYTE, mask);
    }
    glActiveTexture(GL_TEXTURE7);
    glBindTexture(GL_TEXTURE_2D, t.hd);
    if (resize) {
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, width * scale, 192 * scale,
                     0, GL_BGRA, GL_UNSIGNED_BYTE, hd);
    } else {
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, width * scale, 192 * scale,
                        GL_BGRA, GL_UNSIGNED_BYTE, hd);
    }
    glPixelStorei(GL_UNPACK_ALIGNMENT, previous_align);
    glActiveTexture(static_cast<GLenum>(previous_unit));
    glBindBuffer(GL_PIXEL_UNPACK_BUFFER, static_cast<GLuint>(previous_unpack));
    t.width = width;
    t.scale = scale;
    t.on = true;
}

void nds_compute_host_set_text_screen(int screen)
{
    g_text_screen = screen;
}

void nds_compute_host_set_plain_mode(unsigned int mode)
{
    g_plain_mode = mode == 2u ? 2u : 1u;
}

void nds_compute_host_set_smooth_2d(bool enabled)
{
''',
     "// acwwrecomp: hands the HD letters of one screen to the GPU."),
    (HOST,
     "    glUniform1ui(13, g_smooth_2d ? 1u : 0u);   // acwwrecomp: 2D smoothing\n"
     "    glUniform1ui(14, 0u);\n",
     "    glUniform1ui(13, g_smooth_2d ? 1u : 0u);   // acwwrecomp: 2D smoothing\n"
     "    glUniform1ui(14, 0u);\n"
     "    bind_text(g_text_screen, width, scale);   // acwwrecomp: HD letters\n",
     "bind_text(g_text_screen, width, scale);"),
    (HOST,
     "    glUniform1ui(13, 0u);\n"
     "    glUniform1ui(14, 1u);\n",
     "    glUniform1ui(13, 0u);\n"
     "    glUniform1ui(14, g_plain_mode);   // acwwrecomp: xBR, or none\n"
     "    bind_text(screen, width, scale);   // acwwrecomp: HD letters\n",
     "bind_text(screen, width, scale);"),

    # --- frontend: read the letters each frame, the switch, the T key -----
    (FRONTEND,
     "#include \"melonds_compute/ComputeHost.h\"\n#endif\n",
     "#include \"melonds_compute/ComputeHost.h\"\n"
     "#include \"acww_hdtext.h\"   // acwwrecomp: HD letters\n"
     "#endif\n",
     "#include \"acww_hdtext.h\""),
    (FRONTEND,
     "    bool smooth_2d = false;   // acwwrecomp: sharp xBR on 2D (G flips it)\n",
     "    bool smooth_2d = false;   // acwwrecomp: sharp xBR on 2D (G flips it)\n"
     "    bool hd_text = false;     // acwwrecomp: HD letters (T flips it)\n",
     "    bool hd_text = false;"),
    (FRONTEND,
     "    const int scale = static_cast<int>(nds_gpu3d_internal_scale());\n"
     "    // acwwrecomp: the 3D screen gets the HD composite; a screen without one\n",
     "    const int scale = static_cast<int>(nds_gpu3d_internal_scale());\n"
     "    // acwwrecomp: HD letters, read off whichever 2D engine each screen shows.\n"
     "    bool text_on[2] = {false, false};\n"
     "    for (int screen = 0; screen < 2; ++screen) {\n"
     "        const bool a_on_top = (nds_powercontrol9() & 0x8000u) != 0;\n"
     "        const int engine = a_on_top == (screen == 0) ? 0 : 1;\n"
     "        if (presentation.hd_text && !(screen == 0 && top_menu_open))\n"
     "            text_on[screen] = acww_hdtext::update(\n"
     "                screen, engine, screen == 0 ? top_pixels : bottom_pixels,\n"
     "                screen == 0 ? top_width : bottom_width, scale);\n"
     "        else\n"
     "            acww_hdtext::disable(screen);\n"
     "    }\n"
     "    // acwwrecomp: the 3D screen gets the HD composite; a screen without one\n",
     "// acwwrecomp: HD letters, read off whichever 2D engine each screen shows."),
    (FRONTEND,
     "    if (screen == hd_screen)\n"
     "        pixels = nds_compute_host_render_hd(\n",
     "    nds_compute_host_set_text_screen(screen);   // acwwrecomp: HD letters\n"
     "    if (screen == hd_screen)\n"
     "        pixels = nds_compute_host_render_hd(\n",
     "nds_compute_host_set_text_screen(screen);"),
    (FRONTEND,
     "    if (!pixels && presentation.smooth_2d && native && scale >= 2)\n"
     "        pixels = nds_compute_host_render_smooth(\n",
     "    nds_compute_host_set_plain_mode(presentation.smooth_2d ? 1u : 2u);\n"
     "    if (!pixels && (presentation.smooth_2d || text_on[screen]) && native &&\n"
     "        scale >= 2)   // acwwrecomp: HD letters\n"
     "        pixels = nds_compute_host_render_smooth(\n",
     "nds_compute_host_set_plain_mode(presentation.smooth_2d ? 1u : 2u);"),
    (FRONTEND,
     "                     presentation.smooth_2d ? \"sharp xBR\" : \"off\");\n",
     "                     presentation.smooth_2d ? \"sharp xBR\" : \"off\");\n"
     "        const char* hd_text = std::getenv(\"ACWW_HD_TEXT\");   // acwwrecomp\n"
     "        presentation.hd_text = hd_text && std::strcmp(hd_text, \"on\") == 0;\n"
     "        std::fprintf(stderr, \"[acwwrecomp] HD letters: %s (T to switch)\\n\",\n"
     "                     presentation.hd_text ? \"on\" : \"off\");\n",
     "std::getenv(\"ACWW_HD_TEXT\");   // acwwrecomp"),
    (FRONTEND,
     "            if (event.type == SDL_KEYDOWN && !event.key.repeat &&\n"
     "                sdl_event_scancode(event) == SDL_SCANCODE_G &&\n",
     r'''            if (event.type == SDL_KEYDOWN && !event.key.repeat &&
                sdl_event_scancode(event) == SDL_SCANCODE_T &&
                presentation.hd_readback) {
                // acwwrecomp: T flips the HD letters while playing.
                presentation.hd_text = !presentation.hd_text;
                savestate_notice = presentation.hd_text
                    ? "HD letters: on" : "HD letters: off";
                savestate_notice_until =
                    SDL_GetPerformanceCounter() + frequency * 2u;
                std::fprintf(stderr, "[acwwrecomp] %s\n",
                             savestate_notice.c_str());
                continue;
            }
            if (event.type == SDL_KEYDOWN && !event.key.repeat &&
                sdl_event_scancode(event) == SDL_SCANCODE_G &&
''',
     "// acwwrecomp: T flips the HD letters while playing."),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(r"C:\acww\ndsrecomp"))
    args = parser.parse_args()
    if not HEADER.is_file():
        raise SystemExit(f"{HEADER} is missing: paste tools\\acww_hdtext.h first")

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

    target = args.root / "runner/src/acww_hdtext.h"
    header = HEADER.read_bytes().replace(b"\r\n", b"\n")
    if not target.is_file() or target.read_bytes().replace(b"\r\n", b"\n") != header:
        target.write_bytes(header)
        changed.add(str(target))
        print(f"  wrote: runner/src/acww_hdtext.h")
    else:
        print(f"  already there: runner/src/acww_hdtext.h")
    print(f"{len(changed)} file(s) changed" + ("; now rebuild the runner" if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

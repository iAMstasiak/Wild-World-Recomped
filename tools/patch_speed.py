#!/usr/bin/env python3
"""Make the HD picture cheaper to show (the speed patch).

Two savings, both in how the HD pictures reach the window:

* A smoothed screen whose picture hasn't changed since last frame (the sky,
  a menu, a room where nothing moves) keeps the texture it already has, so
  it isn't smoothed, read back and uploaded again.
* Every HD picture read back from the GPU is copied once, straight into the
  window's texture, instead of into a buffer first and then again by SDL.

With -Fps the title bar also shows how often a smoothed screen was reused.

Run after patch_ndsrecomp.py, patch_hd.py, patch_smooth2d.py,
patch_branding.py and patch_hdtext.py. Safe to run again: edits that are
already there are skipped. Rebuild the runner afterwards:
cmake --build C:\\acww\\ndsrecomp\\runner\\build-acww
"""

from __future__ import annotations

import argparse
from pathlib import Path

FRONTEND = "runner/src/frontend.cpp"
HOST = "runner/src/melonds_compute/ComputeHost.cpp"
HOST_H = "runner/src/melonds_compute/ComputeHost.h"

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    # --- ComputeHost.h: the two new calls --------------------------------
    (HOST_H,
     "                                                  int* out_height);\n"
     "bool nds_compute_host_active();\n",
     "                                                  int* out_height);\n"
     "// acwwrecomp: speed patch. render_hd and render_smooth leave the picture\n"
     "// they hand back in a mapped GL buffer (the returned pointer is only a\n"
     "// fallback buffer): copy_readback copies it top-down into dst (pitch in\n"
     "// bytes, e.g. a locked SDL texture) and lets it go; false if none.\n"
     "// forget_readbacks drops readbacks still in flight, so no old picture\n"
     "// comes back later: 0/1 = that screen's smoothing, 2 = the HD composite.\n"
     "bool nds_compute_host_copy_readback(void* dst, int pitch);\n"
     "void nds_compute_host_forget_readbacks(int which);\n"
     "bool nds_compute_host_active();\n",
     "bool nds_compute_host_copy_readback("),

    # --- ComputeHost.cpp: keep the finished readback mapped ---------------
    (HOST,
     "}\n\nconst unsigned int* nds_compute_host_render_hd(unsigned short width,\n",
     "}\n\n"
     "// acwwrecomp: speed patch. A finished readback stays mapped until the\n"
     "// frontend copies it straight into its texture: one copy, not two.\n"
     "namespace\n"
     "{\n"
     "struct MappedReadback {\n"
     "    GLuint pbo = 0;\n"
     "    const unsigned int* src = nullptr;   // GL rows, bottom-up\n"
     "    int width = 0;\n"
     "    int height = 0;\n"
     "};\n"
     "MappedReadback g_mapped;\n"
     "\n"
     "void release_readback()\n"
     "{\n"
     "    if (!g_mapped.src) return;\n"
     "    GLint previous = 0;\n"
     "    glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING, &previous);\n"
     "    glBindBuffer(GL_PIXEL_PACK_BUFFER, g_mapped.pbo);\n"
     "    glUnmapBuffer(GL_PIXEL_PACK_BUFFER);\n"
     "    glBindBuffer(GL_PIXEL_PACK_BUFFER, static_cast<GLuint>(previous));\n"
     "    g_mapped = MappedReadback{};\n"
     "}\n"
     "\n"
     "void keep_readback(GLuint pbo, const unsigned int* src, int w, int h)\n"
     "{\n"
     "    g_mapped.pbo = pbo;\n"
     "    g_mapped.src = src;\n"
     "    g_mapped.width = w;\n"
     "    g_mapped.height = h;\n"
     "}\n"
     "}\n"
     "\n"
     "const unsigned int* nds_compute_host_render_hd(unsigned short width,\n",
     "struct MappedReadback {"),
    (HOST,
     "    if (!g_present_program && !start_presenter()) return nullptr;\n"
     "    const unsigned int hires",
     "    if (!g_present_program && !start_presenter()) return nullptr;\n"
     "    release_readback();   // acwwrecomp: speed patch (HD)\n"
     "    const unsigned int hires",
     "release_readback();   // acwwrecomp: speed patch (HD)"),
    (HOST,
     "            if (src) {\n"
     "                // GL rows run bottom-up; the SDL texture wants them top-down.\n"
     "                for (int y = 0; y < h; ++y)\n"
     "                    std::memcpy(&g_hd_out[static_cast<size_t>(y) * w],\n"
     "                                src + static_cast<size_t>(h - 1 - y) * w,\n"
     "                                static_cast<size_t>(w) * sizeof(unsigned int));\n"
     "                glUnmapBuffer(GL_PIXEL_PACK_BUFFER);\n"
     "                ready = true;\n"
     "            }\n",
     "            if (src) {\n"
     "                // acwwrecomp: speed patch. Left mapped for\n"
     "                // nds_compute_host_copy_readback, which flips the rows.\n"
     "                keep_readback(g_hd_pbo[other], src, w, h);\n"
     "                ready = true;\n"
     "            }\n",
     "keep_readback(g_hd_pbo[other], src, w, h);"),
    (HOST,
     "    if (!g_present_program && !start_presenter()) return nullptr;\n"
     "    SmoothTarget& t = g_smooth_target[screen];\n",
     "    if (!g_present_program && !start_presenter()) return nullptr;\n"
     "    release_readback();   // acwwrecomp: speed patch (smoothing)\n"
     "    SmoothTarget& t = g_smooth_target[screen];\n",
     "release_readback();   // acwwrecomp: speed patch (smoothing)"),
    (HOST,
     "            if (src) {\n"
     "                for (int y = 0; y < h; ++y)\n"
     "                    std::memcpy(&t.out[static_cast<size_t>(y) * w],\n"
     "                                src + static_cast<size_t>(h - 1 - y) * w,\n"
     "                                static_cast<size_t>(w) * sizeof(unsigned int));\n"
     "                glUnmapBuffer(GL_PIXEL_PACK_BUFFER);\n"
     "                ready = true;\n"
     "            }\n",
     "            if (src) {\n"
     "                keep_readback(t.pbo[other], src, w, h);   // acwwrecomp: speed patch\n"
     "                ready = true;\n"
     "            }\n",
     "keep_readback(t.pbo[other], src, w, h);"),
    (HOST,
     "void nds_compute_host_stop()\n{\n",
     "// acwwrecomp: speed patch. See ComputeHost.h.\n"
     "bool nds_compute_host_copy_readback(void* dst, int pitch)\n"
     "{\n"
     "    if (!g_mapped.src) return false;\n"
     "    if (!g_active) {   // the buffers are gone already\n"
     "        g_mapped = MappedReadback{};\n"
     "        return false;\n"
     "    }\n"
     "    const int w = g_mapped.width;\n"
     "    const int h = g_mapped.height;\n"
     "    const size_t row = static_cast<size_t>(w) * sizeof(unsigned int);\n"
     "    const bool fits = dst && pitch > 0 && static_cast<size_t>(pitch) >= row;\n"
     "    if (fits) {\n"
     "        unsigned char* out = static_cast<unsigned char*>(dst);\n"
     "        for (int y = 0; y < h; ++y)\n"
     "            std::memcpy(out + static_cast<size_t>(y) * static_cast<size_t>(pitch),\n"
     "                        g_mapped.src + static_cast<size_t>(h - 1 - y) * w, row);\n"
     "    }\n"
     "    if (sdl_make_current(g_window, g_context)) release_readback();\n"
     "    return fits;\n"
     "}\n"
     "\n"
     "void nds_compute_host_forget_readbacks(int which)\n"
     "{\n"
     "    if (!g_active || which < 0 || which > 2) return;\n"
     "    GLsync* fences = which == 2 ? g_hd_fence : g_smooth_target[which].fence;\n"
     "    if (!fences[0] && !fences[1]) return;\n"
     "    if (!sdl_make_current(g_window, g_context)) return;\n"
     "    for (int i = 0; i < 2; ++i) {\n"
     "        if (fences[i]) glDeleteSync(fences[i]);\n"
     "        fences[i] = nullptr;\n"
     "    }\n"
     "}\n"
     "\n"
     "void nds_compute_host_stop()\n{\n",
     "// acwwrecomp: speed patch. See ComputeHost.h.\n"),

    # --- frontend: what the reuse test remembers per screen ---------------
    (FRONTEND,
     "    bool hd_text = false;     // acwwrecomp: HD letters (T flips it)\n",
     "    bool hd_text = false;     // acwwrecomp: HD letters (T flips it)\n"
     "    // acwwrecomp: speed patch (see update_hd_readback). A smoothed screen's\n"
     "    // last native picture and settings, and whether its HD texture shows\n"
     "    // exactly that; hd_held: last frame's picture was shown once more.\n"
     "    std::vector<uint32_t> smooth_last[2];\n"
     "    uint32_t smooth_mode[2]{};\n"
     "    uint64_t smooth_text[2]{};\n"
     "    bool smooth_shown[2]{};\n"
     "    bool hd_held[2]{};\n"
     "    int hd_screen_last = -1;\n"
     "    unsigned smooth_frames = 0;   // for the -Fps title\n"
     "    unsigned smooth_reused = 0;\n",
     "    std::vector<uint32_t> smooth_last[2];\n"),
    (FRONTEND,
     "    presentation.hd_ready[0] = false;\n"
     "    presentation.hd_ready[1] = false;\n"
     "#if defined(NDS_HAVE_COMPUTE_RENDERER)\n"
     "    if (!presentation.hd_readback) return;\n",
     "    // acwwrecomp: speed patch. Which screens showed an HD picture last frame.\n"
     "    const bool was_ready[2] = {presentation.hd_ready[0],\n"
     "                               presentation.hd_ready[1]};\n"
     "    (void)was_ready;\n"
     "    presentation.hd_ready[0] = false;\n"
     "    presentation.hd_ready[1] = false;\n"
     "#if defined(NDS_HAVE_COMPUTE_RENDERER)\n"
     "    if (!presentation.hd_readback) return;\n",
     "    const bool was_ready[2] = {presentation.hd_ready[0],\n"),

    # --- frontend: reuse an unchanged smoothed screen, hold for a frame ---
    (FRONTEND,
     "    for (int screen = 0; screen < 2; ++screen) {\n"
     "    if (screen == 0 && top_menu_open) continue;   // keep the menu visible\n"
     "    const int width = screen == 0 ? top_width : bottom_width;\n"
     "    const uint32_t* native = screen == 0 ? top_pixels : bottom_pixels;\n"
     "    int hd_width = 0;\n"
     "    int hd_height = 0;\n"
     "    const unsigned int* pixels = nullptr;\n"
     "    nds_compute_host_set_text_screen(screen);   // acwwrecomp: HD letters\n"
     "    if (screen == hd_screen)\n"
     "        pixels = nds_compute_host_render_hd(\n"
     "            static_cast<unsigned short>(width), &hd_width, &hd_height);\n"
     "    nds_compute_host_set_plain_mode(presentation.smooth_2d ? 1u : 2u);\n"
     "    if (!pixels && (presentation.smooth_2d || text_on[screen]) && native &&\n"
     "        scale >= 2)   // acwwrecomp: HD letters\n"
     "        pixels = nds_compute_host_render_smooth(\n"
     "            screen, native, static_cast<unsigned short>(width), scale,\n"
     "            &hd_width, &hd_height);\n"
     "    if (!pixels) continue;\n",
     "    // acwwrecomp: speed patch. When the 3D moves to the other screen, the HD\n"
     "    // composite starts afresh rather than show last frame's on this one.\n"
     "    if (hd_screen != presentation.hd_screen_last) {\n"
     "        nds_compute_host_forget_readbacks(2);\n"
     "        presentation.hd_screen_last = hd_screen;\n"
     "    }\n"
     "    for (int screen = 0; screen < 2; ++screen) {\n"
     "    const bool held = presentation.hd_held[screen];   // acwwrecomp: speed patch\n"
     "    presentation.hd_held[screen] = false;\n"
     "    if (screen == 0 && top_menu_open) {   // keep the menu visible\n"
     "        nds_compute_host_forget_readbacks(0);\n"
     "        if (hd_screen == 0) nds_compute_host_forget_readbacks(2);\n"
     "        continue;\n"
     "    }\n"
     "    const int width = screen == 0 ? top_width : bottom_width;\n"
     "    const uint32_t* native = screen == 0 ? top_pixels : bottom_pixels;\n"
     "    int hd_width = 0;\n"
     "    int hd_height = 0;\n"
     "    const unsigned int* pixels = nullptr;\n"
     "    bool tried = false;\n"
     "    nds_compute_host_set_text_screen(screen);   // acwwrecomp: HD letters\n"
     "    if (screen == hd_screen) {\n"
     "        tried = true;\n"
     "        pixels = nds_compute_host_render_hd(\n"
     "            static_cast<unsigned short>(width), &hd_width, &hd_height);\n"
     "    }\n"
     "    nds_compute_host_set_plain_mode(presentation.smooth_2d ? 1u : 2u);\n"
     "    bool smoothed = false;\n"
     "    bool unchanged = false;\n"
     "    if (!pixels && (presentation.smooth_2d || text_on[screen]) && native &&\n"
     "        scale >= 2) {   // acwwrecomp: HD letters\n"
     "        // acwwrecomp: speed patch. Everything the smoothed picture depends\n"
     "        // on: the native picture, size, scale, smoothing and the letters.\n"
     "        const size_t count = static_cast<size_t>(width) * kScreenHeight;\n"
     "        const uint32_t mode = static_cast<uint32_t>(width) |\n"
     "                              static_cast<uint32_t>(scale) << 16 |\n"
     "                              (presentation.smooth_2d ? 1u : 2u) << 24;\n"
     "        const uint64_t text =\n"
     "            text_on[screen] ? acww_hdtext::g_out[screen].hash : 0u;\n"
     "        std::vector<uint32_t>& last = presentation.smooth_last[screen];\n"
     "        unchanged = presentation.smooth_mode[screen] == mode &&\n"
     "                    presentation.smooth_text[screen] == text &&\n"
     "                    last.size() == count &&\n"
     "                    std::memcmp(last.data(), native,\n"
     "                                count * sizeof(uint32_t)) == 0;\n"
     "        ++presentation.smooth_frames;\n"
     "        if (unchanged && presentation.smooth_shown[screen] &&\n"
     "            presentation.hd_textures[screen]) {\n"
     "            ++presentation.smooth_reused;   // the texture already shows it\n"
     "            nds_compute_host_forget_readbacks(screen);\n"
     "            presentation.hd_ready[screen] = true;\n"
     "            continue;\n"
     "        }\n"
     "        if (!unchanged) {\n"
     "            last.assign(native, native + count);\n"
     "            presentation.smooth_mode[screen] = mode;\n"
     "            presentation.smooth_text[screen] = text;\n"
     "        }\n"
     "        smoothed = true;\n"
     "        pixels = nds_compute_host_render_smooth(\n"
     "            screen, native, static_cast<unsigned short>(width), scale,\n"
     "            &hd_width, &hd_height);\n"
     "    }\n"
     "    if (!smoothed) nds_compute_host_forget_readbacks(screen);\n"
     "    presentation.smooth_shown[screen] = false;\n"
     "    if (!pixels) {\n"
     "        // acwwrecomp: speed patch. Nothing back yet (readbacks run a frame\n"
     "        // behind): show last frame's picture once more, not the plain one.\n"
     "        if ((tried || smoothed) && was_ready[screen] && !held &&\n"
     "            presentation.hd_textures[screen]) {\n"
     "            presentation.hd_ready[screen] = true;\n"
     "            presentation.hd_held[screen] = true;\n"
     "        }\n"
     "        continue;\n"
     "    }\n",
     "            presentation.hd_held[screen] = true;\n"),

    # --- frontend: copy the readback straight into the texture ------------
    (FRONTEND,
     "    SDL_UpdateTexture(texture, nullptr, pixels,\n"
     "                      hd_width * static_cast<int>(sizeof(uint32_t)));\n"
     "    presentation.hd_ready[screen] = true;\n"
     "    }   // acwwrecomp: end of the per-screen loop\n",
     "    // acwwrecomp: speed patch. The readback goes straight into the texture.\n"
     "    void* locked_pixels = nullptr;\n"
     "    int locked_pitch = 0;\n"
     "#if defined(NDS_HAVE_SDL3)\n"
     "    const bool locked =\n"
     "        SDL_LockTexture(texture, nullptr, &locked_pixels, &locked_pitch);\n"
     "#else\n"
     "    const bool locked = SDL_LockTexture(texture, nullptr, &locked_pixels,\n"
     "                                        &locked_pitch) == 0;\n"
     "#endif\n"
     "    bool copied = false;\n"
     "    if (locked) {\n"
     "        copied = nds_compute_host_copy_readback(locked_pixels, locked_pitch);\n"
     "        SDL_UnlockTexture(texture);\n"
     "    }\n"
     "    if (!copied) {\n"
     "        nds_compute_host_copy_readback(const_cast<unsigned int*>(pixels),\n"
     "            hd_width * static_cast<int>(sizeof(uint32_t)));\n"
     "        SDL_UpdateTexture(texture, nullptr, pixels,\n"
     "                          hd_width * static_cast<int>(sizeof(uint32_t)));\n"
     "    }\n"
     "    presentation.hd_ready[screen] = true;\n"
     "    presentation.smooth_shown[screen] = smoothed && unchanged;\n"
     "    }   // acwwrecomp: end of the per-screen loop\n",
     "copied = nds_compute_host_copy_readback(locked_pixels, locked_pitch);"),

    # --- frontend: -Fps also shows how often a screen was reused ----------
    (FRONTEND,
     "            const std::string stats =\n"
     "                show_fps ? \" - \" + fps_text + governor_text : \"\";\n",
     "            // acwwrecomp: speed patch. Share of smoothed frames reused.\n"
     "            std::string reuse_text;\n"
     "            if (presentation.smooth_frames)\n"
     "                reuse_text = \" - 2D reused \" +\n"
     "                    std::to_string(presentation.smooth_reused * 100u /\n"
     "                                   presentation.smooth_frames) + \"%\";\n"
     "            presentation.smooth_frames = 0;\n"
     "            presentation.smooth_reused = 0;\n"
     "            const std::string stats = show_fps\n"
     "                ? \" - \" + fps_text + governor_text + reuse_text : \"\";\n",
     "            std::string reuse_text;\n"),
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
    if "nds_compute_host_set_text_screen(screen);" not in texts[FRONTEND][0]:
        raise SystemExit("run patch_hdtext.py first; nothing was changed")

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

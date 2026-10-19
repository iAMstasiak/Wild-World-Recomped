#!/usr/bin/env python3
"""Add material effects (water first) to the pinned ndsrecomp checkout.

The HD renderer learns which of the game's textures are water from
materials.toml (tools/acww_materials.h, copied into the runner) and draws
those polygons with moving ripples, a sky reflection that grows with
distance, and glints, on top of the game's own colours. A texture is
known by a hash of its texels, so a tag holds wherever the game loads it.

Waterfalls get streaks and foam of their own. The texture picker fills in
materials.toml: run play.ps1 -Pick, then [ and ] step through the textures
on screen (the chosen one flashes), M marks it as water and F as a
waterfall (again to unmark), O turns the effects off and on, and R reads
materials.toml again, so its [look] numbers can be tried while playing.

Only the HD picture (internal resolution 2 or more) has the effect. Run
after the other patch_*.py scripts. Safe to run again: edits that are
already there are skipped, and the header and the shader code are brought
up to date. Rebuild the runner afterwards:
cmake --build C:\\acww\\ndsrecomp\\runner\\build-acww
"""

from __future__ import annotations

import argparse
from pathlib import Path

TEXCACHE = "runner/vendor/melonds/GPU3D_Texcache.h"
COMPUTE_H = "runner/vendor/melonds/GPU3D_Compute.h"
COMPUTE = "runner/vendor/melonds/GPU3D_Compute.cpp"
SHADERS = "runner/vendor/melonds/GPU3D_Compute_shaders.h"
FRONTEND = "runner/src/frontend.cpp"
HEADER = Path(__file__).with_name("acww_materials.h")

WATER_GLSL = r'''
// acwwrecomp: material effects (tools/patch_materials.py). Colours are the
// DS's 0-63 range. p is the spot's place on its texture in texels, which
// moves with the water when the game scrolls the texture.
#ifdef UseTexture
float AcwwHash(vec2 i)
{
    i = mod(i, 256.0);
    vec2 p = fract(i * vec2(0.1031, 0.1030));
    p += dot(p, p.yx + 33.33);
    return fract((p.x + p.y) * p.x);
}

// Smooth value noise at p, from 0 to 1.
float AcwwNoise(vec2 p)
{
    vec2 i = floor(p);
    vec2 f = p - i;
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = AcwwHash(i);
    float b = AcwwHash(i + vec2(1.0, 0.0));
    float c = AcwwHash(i + vec2(0.0, 1.0));
    float d = AcwwHash(i + vec2(1.0, 1.0));
    return a + (b - a) * u.x + (c - a) * u.y + (a - b - c + d) * u.x * u.y;
}

// The slope of that noise at p.
vec2 AcwwNoiseSlope(vec2 p)
{
    vec2 i = floor(p);
    vec2 f = p - i;
    vec2 u = f * f * (3.0 - 2.0 * f);
    vec2 du = 6.0 * f * (1.0 - f);
    float a = AcwwHash(i);
    float b = AcwwHash(i + vec2(1.0, 0.0));
    float c = AcwwHash(i + vec2(0.0, 1.0));
    float d = AcwwHash(i + vec2(1.0, 1.0));
    float k = a - b - c + d;
    return du * vec2(b - a + k * u.y, c - a + k * u.x);
}

// Ripples: three sizes of noise, each turned and drifting its own way. The
// smallest fades out toward the distance, where it would only be grain.
// AcwwLook[0] is ripples, shading, size, speed; AcwwLook[1] is mirror,
// glints, falls-streaks, falls-speed (materials.toml's [look]).
vec2 AcwwRippleSlope(vec2 p, float near)
{
    const mat2 r1 = mat2(0.4536, 0.8912, -0.8912, 0.4536);
    const mat2 r2 = mat2(-0.6663, 0.7457, -0.7457, -0.6663);
    float size = max(AcwwLook[0].z, 0.05);
    float t = AcwwTime * AcwwLook[0].w;
    p /= size;
    vec2 slope = AcwwNoiseSlope(p * 0.16 + vec2(1.0, 0.35) * (t * 0.24)) * 0.16;
    slope += (AcwwNoiseSlope(r1 * p * 0.33 + vec2(-0.55, 1.0) * (t * 0.36)) * r1) * 0.20;
    slope += (AcwwNoiseSlope(r2 * p * 0.62 + vec2(0.3, -1.0) * (t * 0.51)) * r2) * (0.20 * near);
    return slope * AcwwLook[0].x * size;
}

vec3 AcwwWater(vec3 base, vec2 p, ivec2 pos)
{
    vec2 slope = AcwwRippleSlope(p, float(pos.y) / float(ScreenHeight));
    float lum = dot(base, vec3(0.3, 0.5, 0.2)) / 63.0;
    // slopes facing the light are brighter; the others only a little darker,
    // or the troughs turn to dark blotches
    float lit = dot(slope, vec2(-0.45, 0.65)) * AcwwLook[0].y;
    vec3 color = base * (1.0 + (lit > 0.0 ? lit : lit * 0.35));
    // water farther away, higher on the screen, mirrors more of the sky; the
    // sky is a brighter, bluer copy of the water's own colour, so night stays dark
    float far = 1.0 - float(pos.y) / float(ScreenHeight);
    vec3 sky = base * vec3(1.35, 1.45, 1.5) + 4.0;
    float mirror = clamp(AcwwLook[1].x * (0.35 + 0.65 * far) + slope.y * 0.6, 0.0, 0.75);
    color = mix(color, sky, mirror);
    // glints where a ripple faces the sun (or the moon, more faintly)
    vec2 toSun = slope - vec2(0.09, -0.14);
    float glint = exp(-dot(toSun, toSun) * 450.0);
    return color + vec3(glint * (0.15 + 1.5 * lum) * 31.5 * AcwwLook[1].y);
}

// Waterfalls: streaks and foam running along the texture's v, the way the
// game lays its falling water.
vec3 AcwwFalls(vec3 base, vec2 p)
{
    float t = AcwwTime * AcwwLook[1].w;
    float strength = AcwwLook[1].z;
    float n = AcwwNoise(vec2(p.x * 0.45, p.y * 0.06 - t * 2.0)) * 0.6
            + AcwwNoise(vec2(p.x * 1.10, p.y * 0.15 - t * 3.4)) * 0.4;
    float lum = dot(base, vec3(0.3, 0.5, 0.2)) / 63.0;
    vec3 color = base * (1.0 + (n - 0.5) * 0.5 * strength);
    float foam = clamp(smoothstep(0.62, 0.9, n) * strength, 0.0, 1.0);
    return mix(color, base * 1.3 + (6.0 + 12.0 * lum), foam * 0.8);
}

vec3 AcwwHighlight(vec3 base)
{
    float pulse = 0.5 + 0.5 * sin(AcwwTime * 8.0);
    return mix(base, vec3(63.0, 0.0, 63.0), 0.3 + 0.6 * pulse);
}
#endif
'''

APPLY_GLSL = (
    "#ifdef UseTexture\n"
    "            // acwwrecomp: the polygon's material effect\n"
    "            if (polygon.Material == 255U\n"
    "                || ((polygon.Material == 1U || polygon.Material == 2U) && (AcwwFlags & 1U) != 0U))\n"
    "            {\n"
    "                vec3 acwwBase = vec3(r, g, b);\n"
    "                vec2 acwwP = vec2(u, v) * (1.0 / 16.0);\n"
    "                vec3 acwwColor = polygon.Material == 255U ? AcwwHighlight(acwwBase)\n"
    "                    : polygon.Material == 2U ? AcwwFalls(acwwBase, acwwP)\n"
    "                    : AcwwWater(acwwBase, acwwP, position);\n"
    "                acwwColor = clamp(acwwColor + 0.5, 0.0, 63.0);\n"
    "                r = uint(acwwColor.r);\n"
    "                g = uint(acwwColor.g);\n"
    "                b = uint(acwwColor.b);\n"
    "            }\n"
    "#endif\n")

# (file, text to find, replacement, marker that shows the edit is already in)
EDITS = [
    # --- texture cache: a material per texture, known by its texels -------
    (TEXCACHE,
     '#include "../../src/melonds_compute/TextureUpscale.h"\n',
     '#include "../../src/melonds_compute/TextureUpscale.h"\n'
     '#include "../../src/acww_materials.h"   // acwwrecomp: material tags\n',
     '#include "../../src/acww_materials.h"'),
    (TEXCACHE,
     "        u64 TextureHash[2];\n"
     "        u64 TexPalHash;\n",
     "        u64 TextureHash[2];\n"
     "        u64 TexPalHash;\n"
     "        u64 AcwwHash;   // acwwrecomp: the texels' hash, for material tags\n"
     "        u32 AcwwMaterial;\n",
     "        u64 AcwwHash;"),
    (TEXCACHE,
     "    void GetTexture(GPU& gpu, u32 texParam, u32 palBase, TexHandleT& textureHandle, u32& layer, u32*& helper)\n",
     "    void GetTexture(GPU& gpu, u32 texParam, u32 palBase, TexHandleT& textureHandle, u32& layer, u32*& helper,\n"
     "        u32& material, u64& materialHash)   // acwwrecomp: and its material\n",
     "u32& material, u64& materialHash)"),
    (TEXCACHE,
     "            layer = it->second.Texture.Layer;\n"
     "            helper = &it->second.LastVariant;\n"
     "            return;\n",
     "            layer = it->second.Texture.Layer;\n"
     "            helper = &it->second.LastVariant;\n"
     "            material = it->second.AcwwMaterial;   // acwwrecomp\n"
     "            materialHash = it->second.AcwwHash;\n"
     "            return;\n",
     "            material = it->second.AcwwMaterial;"),
    (TEXCACHE,
     "                entry.TexPalStart, entry.TexPalSize);\n"
     "\n"
     "        auto& texArrays = TexArrays[widthLog2][heightLog2];\n",
     "                entry.TexPalStart, entry.TexPalSize);\n"
     "\n"
     "        // acwwrecomp: material tags know a texture by its texels alone, not\n"
     "        // its palette or where it is in VRAM\n"
     "        entry.AcwwHash = entry.TextureHash[0] ^ (entry.TextureHash[1] * 0x9E3779B97F4A7C15ull)\n"
     "            ^ ((u64)((fmt << 8) | (widthLog2 << 4) | heightLog2) << 48);\n"
     "        entry.AcwwMaterial = acww_materials::material_for(entry.AcwwHash);\n"
     "\n"
     "        auto& texArrays = TexArrays[widthLog2][heightLog2];\n",
     "        entry.AcwwHash = entry.TextureHash[0]"),
    (TEXCACHE,
     "        textureHandle = storagePlace.TextureID;\n"
     "        layer = storagePlace.Layer;\n",
     "        textureHandle = storagePlace.TextureID;\n"
     "        layer = storagePlace.Layer;\n"
     "        material = entry.AcwwMaterial;   // acwwrecomp\n"
     "        materialHash = entry.AcwwHash;\n",
     "        material = entry.AcwwMaterial;"),
    (TEXCACHE,
     "    void Reset()\n",
     "    // acwwrecomp: the material tags changed\n"
     "    void AcwwRefreshMaterials()\n"
     "    {\n"
     "        for (auto& item : Cache)\n"
     "            item.second.AcwwMaterial = acww_materials::material_for(item.second.AcwwHash);\n"
     "    }\n"
     "\n"
     "    void Reset()\n",
     "    void AcwwRefreshMaterials()"),
    # --- compute renderer: the material per polygon, and the clock --------
    (COMPUTE_H,
     "        float TextureLayer;\n"
     "    };\n",
     "        float TextureLayer;\n"
     "        u32 Material;   // acwwrecomp: 0, or a tag from acww_materials.h\n"
     "    };\n",
     "        u32 Material;   // acwwrecomp"),
    (COMPUTE_H,
     "        u32 FogOffset, FogShift, FogColor;\n",
     "        u32 FogOffset, FogShift, FogColor;\n"
     "\n"
     "        float AcwwTime;   // acwwrecomp: seconds, for the water effect\n"
     "        u32 AcwwFlags;   // acwwrecomp: 1 = water effect on\n",
     "        float AcwwTime;"),
    (COMPUTE_H,
     "        u32 AcwwFlags;   // acwwrecomp: 1 = water effect on\n",
     "        u32 AcwwFlags;   // acwwrecomp: 1 = water effect on\n"
     "        float AcwwLook[8];   // acwwrecomp: materials.toml's [look]\n",
     "        float AcwwLook[8];"),
    (COMPUTE_H,
     "    int ShaderStepIdx = 0;\n",
     "    int ShaderStepIdx = 0;\n"
     "    u32 AcwwMaterialsVersion = 0;   // acwwrecomp\n"
     "    bool AcwwAnimated = false;   // acwwrecomp: the last frame had water to move\n",
     "    u32 AcwwMaterialsVersion = 0;"),
    (COMPUTE,
     '#include "GPU3D_Compute_shaders.h"\n',
     '#include "GPU3D_Compute_shaders.h"\n'
     '\n'
     '#include <chrono>\n'
     '#include <cmath>\n'
     '#include "../../src/acww_materials.h"   // acwwrecomp: material tags\n',
     '#include "../../src/acww_materials.h"'),
    (COMPUTE,
     "    if (!Texcache.Update(gpu) && gpu.GPU3D.RenderFrameIdentical)\n"
     "    {\n"
     "        return;\n"
     "    }\n",
     "    // acwwrecomp: water keeps moving, and the picker's choice keeps\n"
     "    // flashing, when the game sends the same picture again.\n"
     "    const bool acwwPicking = acww_materials::picker_enabled();\n"
     "    if (!Texcache.Update(gpu) && gpu.GPU3D.RenderFrameIdentical && !AcwwAnimated && !acwwPicking)\n"
     "    {\n"
     "        return;\n"
     "    }\n"
     "    if (AcwwMaterialsVersion != acww_materials::version())\n"
     "    {\n"
     "        Texcache.AcwwRefreshMaterials();\n"
     "        AcwwMaterialsVersion = acww_materials::version();\n"
     "    }\n"
     "    const u64 acwwSelected = acww_materials::begin_frame();\n"
     "    const bool acwwWater = acww_materials::effects_on();\n"
     "    bool acwwAnimated = acwwPicking;\n",
     "    const bool acwwPicking = acww_materials::picker_enabled();"),
    (COMPUTE,
     "    u32 numVariants = 0, prevVariant, prevTexLayer;\n",
     "    u32 numVariants = 0, prevVariant, prevTexLayer;\n"
     "    u32 acwwMaterial = 0;   // acwwrecomp: the current texture's material\n"
     "    u64 acwwHash = 0;\n",
     "    u32 acwwMaterial = 0;"),
    (COMPUTE,
     "            // we always need to look up the texture to get the layer of the array texture\n",
     "            acwwMaterial = 0;   // acwwrecomp: untextured polygons have none\n"
     "            acwwHash = 0;\n"
     "            // we always need to look up the texture to get the layer of the array texture\n",
     "            acwwMaterial = 0;   // acwwrecomp"),
    (COMPUTE,
     "variant.Texture, prevTexLayer, textureLastVariant);\n",
     "variant.Texture, prevTexLayer, textureLastVariant,\n"
     "                    acwwMaterial, acwwHash);   // acwwrecomp\n",
     "acwwMaterial, acwwHash);   // acwwrecomp"),
    (COMPUTE,
     "        RenderPolygons[i].TextureLayer = (float)prevTexLayer;\n",
     "        RenderPolygons[i].TextureLayer = (float)prevTexLayer;\n"
     "        // acwwrecomp: the polygon's material; the picker's choice flashes\n"
     "        RenderPolygons[i].Material = (acwwSelected && acwwHash == acwwSelected)\n"
     "            ? (u32)acww_materials::kHighlight : acwwMaterial;\n"
     "        if ((RenderPolygons[i].Material == acww_materials::kWater ||\n"
     "             RenderPolygons[i].Material == acww_materials::kFalls) && acwwWater)\n"
     "            acwwAnimated = true;\n",
     "        RenderPolygons[i].Material = (acwwSelected"),
    (COMPUTE,   # (an older patch: waterfalls move too)
     "        if (RenderPolygons[i].Material == acww_materials::kWater && acwwWater)\n",
     "        if ((RenderPolygons[i].Material == acww_materials::kWater ||\n"
     "             RenderPolygons[i].Material == acww_materials::kFalls) && acwwWater)\n",
     "RenderPolygons[i].Material == acww_materials::kFalls) && acwwWater)"),
    (COMPUTE,
     "        RenderPolygons[i].YTop = ytop;\n"
     "        RenderPolygons[i].YBot = ybot;\n",
     "        RenderPolygons[i].YTop = ytop;\n"
     "        RenderPolygons[i].YBot = ybot;\n"
     "        if (acwwPicking && acwwHash)   // acwwrecomp: how much of the screen it covers\n"
     "        {\n"
     "            s32 xmin = ScreenWidth, xmax = 0;\n"
     "            for (u32 k = 0; k < nverts; k++)\n"
     "            {\n"
     "                xmin = std::min(scaledPositions[k][0], xmin);\n"
     "                xmax = std::max(scaledPositions[k][0], xmax);\n"
     "            }\n"
     "            acww_materials::note(acwwHash, TextureWidth(polygon->TexParam), TextureHeight(polygon->TexParam),\n"
     "                (polygon->TexParam >> 26) & 0x7,\n"
     "                (long long)std::max(xmax - xmin, 0) * std::max(ybot - ytop, 0));\n"
     "        }\n",
     "        if (acwwPicking && acwwHash)"),
    (COMPUTE,
     '    //printf("found via %d %d %d of %d\\n", foundviatexcache, foundviaprev, numslow, RenderNumPolygons);\n',
     "    acww_materials::end_frame();   // acwwrecomp: the picker's keys\n"
     "    AcwwAnimated = acwwAnimated;\n"
     "\n"
     '    //printf("found via %d %d %d of %d\\n", foundviatexcache, foundviaprev, numslow, RenderNumPolygons);\n',
     "    acww_materials::end_frame();"),
    (COMPUTE,
     "    meta.FogOffset = gpu.GPU3D.RenderFogOffset;\n",
     "    meta.FogOffset = gpu.GPU3D.RenderFogOffset;\n"
     "    {   // acwwrecomp: the water effect's clock\n"
     "        static const auto acwwStart = std::chrono::steady_clock::now();\n"
     "        const double seconds = std::chrono::duration<double>(\n"
     "            std::chrono::steady_clock::now() - acwwStart).count();\n"
     "        meta.AcwwTime = (float)std::fmod(seconds, 3600.0);\n"
     "        meta.AcwwFlags = acwwWater ? 1u : 0u;\n"
     "    }\n",
     "        meta.AcwwTime = (float)std::fmod"),
    (COMPUTE,
     "        meta.AcwwFlags = acwwWater ? 1u : 0u;\n",
     "        meta.AcwwFlags = acwwWater ? 1u : 0u;\n"
     "        for (int k = 0; k < acww_materials::kLookCount; k++)\n"
     "            meta.AcwwLook[k] = acww_materials::look(k);\n",
     "            meta.AcwwLook[k] = acww_materials::look(k);"),
    # --- shaders: the effects ----------------------------------------------
    (SHADERS,
     "    float TextureLayer;\n"
     "};\n",
     "    float TextureLayer;\n"
     "\n"
     "    uint Material; // acwwrecomp: 1 water, 255 the picker's choice\n"
     "};\n",
     "    uint Material; // acwwrecomp"),
    (SHADERS,
     "    uint FogOffset, FogShift, FogColor;\n"
     "};\n",
     "    uint FogOffset, FogShift, FogColor;\n"
     "\n"
     "    float AcwwTime; // acwwrecomp\n"
     "    uint AcwwFlags;\n"
     "};\n",
     "    float AcwwTime; // acwwrecomp"),
    (SHADERS,
     "    uint AcwwFlags;\n"
     "};\n",
     "    uint AcwwFlags;\n"
     "    vec4 AcwwLook[2]; // acwwrecomp: materials.toml's [look]\n"
     "};\n",
     "    vec4 AcwwLook[2];"),
    (SHADERS,
     "layout (location = 1) uniform vec2 InvTextureSize;\n",
     "layout (location = 1) uniform vec2 InvTextureSize;\n" + WATER_GLSL,
     "vec3 AcwwWater(vec3 base"),
    (SHADERS,
     "            if (polyalpha == 0)\n"
     "                a = 31;\n",
     APPLY_GLSL +
     "\n"
     "            if (polyalpha == 0)\n"
     "                a = 31;\n",
     "            // acwwrecomp: the polygon's material effect"),
    # --- frontend: the picker's keys and what it says -----------------------
    (FRONTEND,
     '#include "acww_keys.h"   // acwwrecomp: keybinds.ini\n',
     '#include "acww_keys.h"   // acwwrecomp: keybinds.ini\n'
     '#include "acww_materials.h"   // acwwrecomp: water and the texture picker\n',
     '#include "acww_materials.h"'),
    (FRONTEND,
     "            if (event.type == SDL_KEYDOWN && !event.key.repeat &&\n"
     "                sdl_event_scancode(event) == SDL_SCANCODE_T &&\n",
     "            if (event.type == SDL_KEYDOWN && !event.key.repeat &&\n"
     "                acww_materials::picker_enabled()) {\n"
     "                // acwwrecomp: the texture picker. [ and ] choose a texture\n"
     "                // on screen, M marks it as water and F as a waterfall, O\n"
     "                // turns the effects off and on, R reads materials.toml again.\n"
     "                const SDL_Scancode pick_key = sdl_event_scancode(event);\n"
     "                if (pick_key == SDL_SCANCODE_LEFTBRACKET) {\n"
     "                    acww_materials::press_step(-1);\n"
     "                    continue;\n"
     "                }\n"
     "                if (pick_key == SDL_SCANCODE_RIGHTBRACKET) {\n"
     "                    acww_materials::press_step(1);\n"
     "                    continue;\n"
     "                }\n"
     "                if (pick_key == SDL_SCANCODE_M || pick_key == SDL_SCANCODE_F) {\n"
     "                    acww_materials::press_mark(pick_key == SDL_SCANCODE_F\n"
     "                        ? acww_materials::kFalls : acww_materials::kWater);\n"
     "                    continue;\n"
     "                }\n"
     "                if (pick_key == SDL_SCANCODE_R) {\n"
     "                    acww_materials::press_reload();\n"
     "                    continue;\n"
     "                }\n"
     "                if (pick_key == SDL_SCANCODE_O) {\n"
     "                    acww_materials::press_toggle();\n"
     "                    continue;\n"
     "                }\n"
     "            }\n"
     "            if (event.type == SDL_KEYDOWN && !event.key.repeat &&\n"
     "                sdl_event_scancode(event) == SDL_SCANCODE_T &&\n",
     "                acww_materials::picker_enabled()) {"),
    (FRONTEND,   # (an older patch: F marks waterfalls, R reloads)
     "                // acwwrecomp: the texture picker. [ and ] choose a texture\n"
     "                // on screen, M marks it as water, O turns water off and on.\n",
     "                // acwwrecomp: the texture picker. [ and ] choose a texture\n"
     "                // on screen, M marks it as water and F as a waterfall, O\n"
     "                // turns the effects off and on, R reads materials.toml again.\n",
     "M marks it as water and F as a waterfall"),
    (FRONTEND,
     "                if (pick_key == SDL_SCANCODE_M) {\n"
     "                    acww_materials::press_mark();\n"
     "                    continue;\n"
     "                }\n",
     "                if (pick_key == SDL_SCANCODE_M || pick_key == SDL_SCANCODE_F) {\n"
     "                    acww_materials::press_mark(pick_key == SDL_SCANCODE_F\n"
     "                        ? acww_materials::kFalls : acww_materials::kWater);\n"
     "                    continue;\n"
     "                }\n"
     "                if (pick_key == SDL_SCANCODE_R) {\n"
     "                    acww_materials::press_reload();\n"
     "                    continue;\n"
     "                }\n",
     "acww_materials::press_reload();"),
    (FRONTEND,
     "        const uint64_t counter = SDL_GetPerformanceCounter();\n"
     "        if (!savestate_notice.empty() && counter >= savestate_notice_until)\n",
     "        {   // acwwrecomp: what the texture picker has to say\n"
     "            const std::string pick_notice = acww_materials::take_notice();\n"
     "            if (!pick_notice.empty()) {\n"
     "                savestate_notice = pick_notice;\n"
     "                savestate_notice_until =\n"
     "                    SDL_GetPerformanceCounter() + frequency * 4u;\n"
     '                std::fprintf(stderr, "[acwwrecomp] %s\\n", pick_notice.c_str());\n'
     "            }\n"
     "        }\n"
     "        const uint64_t counter = SDL_GetPerformanceCounter();\n"
     "        if (!savestate_notice.empty() && counter >= savestate_notice_until)\n",
     "acww_materials::take_notice();"),
]

# Blocks rewritten whole when they differ, so a newer look replaces an older
# one: (file, the text the block starts with, the text that ends it).
BLOCKS = [
    (SHADERS, "// acwwrecomp: material effects (tools/patch_materials.py)", "#endif\n",
     WATER_GLSL.lstrip("\n")),
    (SHADERS, APPLY_GLSL.split("\n", 2)[0] + "\n" + APPLY_GLSL.split("\n", 2)[1] + "\n", "#endif\n",
     APPLY_GLSL),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(r"C:\acww\ndsrecomp"))
    args = parser.parse_args()
    if not HEADER.is_file():
        raise SystemExit(f"{HEADER} is missing: paste tools\\acww_materials.h first")

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

    for rel, begin, end, block in BLOCKS:
        text, crlf = texts[rel]
        at = text.find(begin)
        stop = text.find(end, at) + len(end) if at >= 0 else -1
        if at < 0 or stop < len(end):
            raise SystemExit(f"{rel}: can't find the block starting '{begin.strip().splitlines()[0][:60]}'")
        if text[at:stop] == block:
            continue
        texts[rel] = (text[:at] + block + text[stop:], crlf)
        changed.add(rel)
        print(f"  updated: {rel}: {begin.strip().splitlines()[0][:60]}")

    for rel in sorted(changed):
        text, crlf = texts[rel]
        out = text.replace("\n", "\r\n") if crlf else text
        (args.root / rel).write_bytes(out.encode("utf-8"))

    target = args.root / "runner/src/acww_materials.h"
    header = HEADER.read_bytes().replace(b"\r\n", b"\n")
    if not target.is_file() or target.read_bytes().replace(b"\r\n", b"\n") != header:
        target.write_bytes(header)
        changed.add(str(target))
        print("  wrote: runner/src/acww_materials.h")
    else:
        print("  already there: runner/src/acww_materials.h")
    print(f"{len(changed)} file(s) changed" + ("; now rebuild the runner" if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

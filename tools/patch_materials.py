#!/usr/bin/env python3
"""Add material effects (water first) to the pinned ndsrecomp checkout.

The HD renderer learns which of the game's textures are water from
materials.toml (tools/acww_materials.h, copied into the runner) and draws
those polygons in place of the game's pattern: calm swells, a sky sheen
that grows with distance and glints in short dashes, in the texture's
average colour (so day and night still change it), tinted toward a colour
of your choosing. A texture is known by a hash of its texels, so a tag
holds wherever the game loads it.

Waterfalls get streaks and foam of their own. The texture picker fills in
materials.toml: run play.ps1 -Pick, then [ and ] step through the textures
on screen (the chosen one flashes), M marks it as water, F as a waterfall,
H as hidden and B as under the water (again to unmark), O turns the effects
off and on, R reads
materials.toml again, so its [look] numbers can be tried while playing.
While picking, textures drawn exactly where tagged water was the frame
before are tagged too, which finds the water's other animation frames.

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

// The texture's average colour and alpha, from 16 of its texels: the water
// without the game's pattern (which is partly in its alpha), still following
// its day and night palettes.
vec4 AcwwAverage(float layer)
{
    vec3 sum = vec3(0.0);
    float count = 0.0, alpha = 0.0;
    for (int y = 0; y < 4; y++)
        for (int x = 0; x < 4; x++)
        {
            uvec4 texel = texture(CurrentTexture, vec3((vec2(x, y) + 0.5) * 0.25, layer));
            alpha += float(texel.a);
            if (texel.a > 0U)
            {
                sum += vec3(texel.rgb);
                count += 1.0;
            }
        }
    return vec4(count > 0.0 ? sum / count : vec3(0.0), alpha / 16.0);
}

// Water, drawn in place of the game's pattern: calm broad swells, a sky sheen
// that grows with distance, and glints that catch the light in short dashes.
// AcwwLook[0] = swell, wave-size, wave-speed, mirror; [1] = glints,
// glint-amount, keep-texture, tint; [2] = tint colour (0-255), falls-streaks;
// [3] = falls-speed, opacity, see-through (materials.toml's [look]). dx is how
// far along the texture one pixel to the right is, so the glints lie along rows.
vec3 AcwwWater(vec3 texColor, vec3 avgColor, vec2 p, vec2 dx, ivec2 pos)
{
    const vec3 lumw = vec3(0.3, 0.5, 0.2);
    vec3 game = mix(avgColor, texColor, clamp(AcwwLook[1].z, 0.0, 1.0));
    vec3 tint = AcwwLook[2].xyz * (63.0 / 255.0);
    float l = dot(game, lumw);
    vec3 base = mix(game, tint * (l / max(dot(tint, lumw), 0.5)), clamp(AcwwLook[1].w, 0.0, 1.0));

    float t = AcwwTime * AcwwLook[0].z;
    p /= max(AcwwLook[0].y, 0.05);
    vec2 swell = AcwwNoiseSlope(p * 0.03 + vec2(1.0, 0.3) * (t * 0.15))
               + AcwwNoiseSlope(p * 0.06 + vec2(-0.4, 1.0) * (t * 0.24)) * 0.5;
    swell *= AcwwLook[0].x;
    vec3 color = base * (1.0 + dot(swell, vec2(-0.4, 0.7)) * 0.10);

    float far = 1.0 - float(pos.y) / float(ScreenHeight);
    vec3 sky = base * vec3(1.2, 1.25, 1.25) + 2.5;
    color = mix(color, sky, clamp(AcwwLook[0].w * (0.25 + far) + swell.y * 0.05, 0.0, 0.7));

    vec2 e = dot(dx, dx) > 0.0 ? normalize(dx) : vec2(1.0, 0.0);
    vec2 ps = vec2(dot(p, e), dot(p, vec2(-e.y, e.x)));
    // on a stretched texture a dash would run right across the screen: keep
    // them under about 40 pixels long and 9 pixels thick
    float texel = dot(dx, dx) > 0.0 ? length(dx) / max(AcwwLook[0].y, 0.05) : 1.0;
    vec2 q = vec2(ps.x * max(0.05, 0.025 / texel), ps.y * max(0.22, 0.11 / texel))
           + vec2(t * 0.1, -t * 0.35);
    vec2 g = AcwwNoiseSlope(q) + AcwwNoiseSlope(q * vec2(1.9, 2.3) + 3.7) * 0.5;
    vec2 d = g - vec2(0.0, 1.1);
    float spot = exp(-dot(d, d) * 18.0);
    float gate = clamp((AcwwNoise(p * 0.03 + vec2(t * 0.03, 0.0)) - 0.65 + 0.3 * AcwwLook[1].y) * 3.0, 0.0, 1.0);
    float light = dot(base, lumw) / 30.0;   // about 1 by day, much less at night
    return color + vec3(spot * gate * AcwwLook[1].x * (4.0 + 36.0 * light * light));
}

// Waterfalls: streaks and foam running along the texture's v, the way the
// game lays its falling water.
vec3 AcwwFalls(vec3 base, vec2 p)
{
    float t = AcwwTime * AcwwLook[3].x;
    float strength = AcwwLook[2].w;
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
    "                vec3 acwwColor;\n"
    "                if (polygon.Material == 255U)\n"
    "                    acwwColor = AcwwHighlight(acwwBase);\n"
    "                else if (polygon.Material == 2U)\n"
    "                    acwwColor = AcwwFalls(acwwBase, acwwP);\n"
    "                else\n"
    "                {\n"
    "                    vec4 acwwAvg4 = AcwwAverage(polygon.TextureLayer);\n"
    "                    vec3 acwwAvg = acwwAvg4.rgb;\n"
    "#ifndef Decal\n"
    "                    acwwAvg = (acwwAvg + 1.0) * (vec3(vr, vg, vb) + 1.0) / 64.0 - 1.0;\n"
    "                    // the game's pattern is partly in the texture's alpha: even it\n"
    "                    // out too, then make the water more or less see-through\n"
    "                    float acwwA = mix(acwwAvg4.a, float(texcolor.a), clamp(AcwwLook[1].z, 0.0, 1.0));\n"
    "                    acwwA = min(acwwA * AcwwLook[3].y, 31.0);\n"
    "                    a = uint(((int(acwwA + 0.5) + 1) * (int(polyalpha) + 1) - 1) >> 5);\n"
    "#endif\n"
    "                    // which way the screen's rows run across the texture\n"
    "                    vec2 acwwDx = vec2(0.0);\n"
    "                    if (xspan.X1 - xspan.X0 >= 2)\n"
    "                    {\n"
    "                        int acwwX = position.x + 1 < xspan.X1 ? position.x + 1 : position.x - 1;\n"
    "                        int acwwU, acwwV;\n"
    "                        if ((xspan.Flags & XSpanSetup_Linear) == 0U)\n"
    "                        {\n"
    "                            int acwwF = CalcYFactorX(xspan, acwwX);\n"
    "                            acwwU = InterpolateAttrPersp(xspan.TexcoordU0, xspan.TexcoordU1, acwwF);\n"
    "                            acwwV = InterpolateAttrPersp(xspan.TexcoordV0, xspan.TexcoordV1, acwwF);\n"
    "                        }\n"
    "                        else\n"
    "                        {\n"
    "                            acwwU = InterpolateAttrLinear(xspan.TexcoordU0, xspan.TexcoordU1,\n"
    "                                acwwX - xspan.X0, xspan.XRecip, xspan.X1 - xspan.X0);\n"
    "                            acwwV = InterpolateAttrLinear(xspan.TexcoordV0, xspan.TexcoordV1,\n"
    "                                acwwX - xspan.X0, xspan.XRecip, xspan.X1 - xspan.X0);\n"
    "                        }\n"
    "                        acwwDx = vec2(acwwU - u, acwwV - v) * (acwwX > position.x ? 1.0 : -1.0) / 16.0;\n"
    "                    }\n"
    "                    acwwColor = AcwwWater(acwwBase, acwwAvg, acwwP, acwwDx, position);\n"
    "                }\n"
    "                acwwColor = clamp(acwwColor + 0.5, 0.0, 63.0);\n"
    "                r = uint(acwwColor.r);\n"
    "                g = uint(acwwColor.g);\n"
    "                b = uint(acwwColor.b);\n"
    "            }\n"
    "#else\n"
    "            // acwwrecomp: the picker's choice flashes on untextured polygons too\n"
    "            if (polygon.Material == 255U)\n"
    "            {\n"
    "                float acwwPulse = 0.5 + 0.5 * sin(AcwwTime * 8.0);\n"
    "                vec3 acwwColor = mix(vec3(r, g, b), vec3(63.0, 0.0, 63.0), 0.3 + 0.6 * acwwPulse);\n"
    "                r = uint(acwwColor.r + 0.5);\n"
    "                g = uint(acwwColor.g + 0.5);\n"
    "                b = uint(acwwColor.b + 0.5);\n"
    "            }\n"
    "#endif\n"
    "            if (polygon.Material == 3U && (AcwwFlags & 1U) != 0U)\n"
    "                a = 0U;   // acwwrecomp: hidden\n"
    "// acwwrecomp: end of the material effect\n")

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
     "        float AcwwLook[16];   // acwwrecomp: materials.toml's [look]\n",
     "        float AcwwLook["),
    (COMPUTE_H,   # (an older patch had 8)
     "        float AcwwLook[8];",
     "        float AcwwLook[16];",
     "        float AcwwLook[16];"),
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
    (COMPUTE,
     "             RenderPolygons[i].Material == acww_materials::kFalls) && acwwWater)\n"
     "            acwwAnimated = true;\n",
     "             RenderPolygons[i].Material == acww_materials::kFalls) && acwwWater)\n"
     "            acwwAnimated = true;\n"
     "        // acwwrecomp: a polygon with no texture is known by its kind, alpha and ID\n"
     "        const u64 acwwPlain = (!acwwHash && !polygon->IsShadowMask)\n"
     "            ? acww_materials::plain_key(polygon->Attr) : 0;\n"
     "        if (acwwPlain)\n"
     "            RenderPolygons[i].Material = (acwwSelected && acwwPlain == acwwSelected)\n"
     "                ? (u32)acww_materials::kHighlight : acww_materials::material_for(acwwPlain);\n",
     "const u64 acwwPlain = (!acwwHash"),
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
     "                (long long)std::max(xmax - xmin, 0) * std::max(ybot - ytop, 0));\n",
     "                (long long)std::max(xmax - xmin, 0) * std::max(ybot - ytop, 0));\n"
     "            // acwwrecomp: drawn where water was last frame, with an untagged\n"
     "            // texture of the same size and format: the water's next frame\n"
     "            const u32 learned = acww_materials::learn(xmin, xmax, ytop, ybot, (int)nverts,\n"
     "                (polygon->TexParam >> 20) & 0x1FF, acwwHash, acwwMaterial,\n"
     "                TextureWidth(polygon->TexParam), TextureHeight(polygon->TexParam),\n"
     "                (polygon->TexParam >> 26) & 0x7);\n"
     "            if (learned != acwwMaterial)\n"
     "            {\n"
     "                acwwMaterial = learned;\n"
     "                if (RenderPolygons[i].Material != acww_materials::kHighlight)\n"
     "                    RenderPolygons[i].Material = learned;\n"
     "                if (acwwWater)\n"
     "                    acwwAnimated = true;\n"
     "            }\n",
     "acww_materials::learn(xmin, xmax"),
    (COMPUTE,
     "        if (acwwPicking && acwwHash)   // acwwrecomp: how much of the screen it covers\n",
     "        if (acwwPicking && acwwPlain)   // acwwrecomp: untextured polygons too\n"
     "        {\n"
     "            s32 xmin = ScreenWidth, xmax = 0;\n"
     "            for (u32 k = 0; k < nverts; k++)\n"
     "            {\n"
     "                xmin = std::min(scaledPositions[k][0], xmin);\n"
     "                xmax = std::max(scaledPositions[k][0], xmax);\n"
     "            }\n"
     "            acww_materials::note_plain(acwwPlain, (polygon->Attr >> 16) & 0x1F, (polygon->Attr >> 24) & 0x3F,\n"
     "                polygon->Vertices[0]->FinalColor[0] >> 3, polygon->Vertices[0]->FinalColor[1] >> 3,\n"
     "                polygon->Vertices[0]->FinalColor[2] >> 3,\n"
     "                (long long)std::max(xmax - xmin, 0) * std::max(ybot - ytop, 0));\n"
     "        }\n"
     "        if (acwwPicking && acwwHash)   // acwwrecomp: how much of the screen it covers\n",
     "acww_materials::note_plain(acwwPlain"),
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
     "    vec4 AcwwLook[4]; // acwwrecomp: materials.toml's [look]\n"
     "};\n",
     "    vec4 AcwwLook["),
    (SHADERS,   # (an older patch had 2)
     "    vec4 AcwwLook[2];",
     "    vec4 AcwwLook[4];",
     "    vec4 AcwwLook[4];"),
    (SHADERS,
     "layout (location = 1) uniform vec2 InvTextureSize;\n",
     "layout (location = 1) uniform vec2 InvTextureSize;\n" + WATER_GLSL,
     "// acwwrecomp: material effects (tools/patch_materials.py)"),
    (SHADERS,
     "            if (polyalpha == 0)\n"
     "                a = 31;\n",
     APPLY_GLSL +
     "\n"
     "            if (polyalpha == 0)\n"
     "                a = 31;\n",
     "            // acwwrecomp: the polygon's material effect"),
    (SHADERS,
     "                    uint srcAttr = (polygonAttr & 0x3F008000U);\n",
     "                    uint srcAttr = (polygonAttr & 0x3F008000U);\n"
     "                    // acwwrecomp: the game fogs the near water blue, which makes a line\n"
     "                    // across it, so our water (and the picker's choice) goes without\n"
     "                    if (Polygons[polygonIdx].Material == 255U ||\n"
     "                        (Polygons[polygonIdx].Material == 1U && (AcwwFlags & 1U) != 0U))\n"
     "                        srcAttr &= ~(1U << 15);\n",
     "// acwwrecomp: the game fogs the near water"),
    (SHADERS,
     "void PlotTranslucent(inout uint color, inout uint depth, inout uint attr, bool isShadow,",
     "// acwwrecomp: set while our water is drawn, so it covers the 2D layers\n"
     "bool AcwwSolid = false;\n"
     "\n"
     "void PlotTranslucent(inout uint color, inout uint depth, inout uint attr, bool isShadow,",
     "bool AcwwSolid = false;"),
    (SHADERS,
     "        color = (srcRB & 0x3F003FU) | (srcG & 0x003F00U) | max(dstA, srcA);\n",
     "        color = (srcRB & 0x3F003FU) | (srcG & 0x003F00U) | (AcwwSolid ? 0x1F000000U : max(dstA, srcA));\n",
     "(AcwwSolid ? 0x1F000000U"),
    (SHADERS,
     "                        bool writeDepth = (polygonAttr & (1U<<11)) != 0;\n",
     "                        bool writeDepth = (polygonAttr & (1U<<11)) != 0;\n"
     "                        // acwwrecomp: our water shows the 3D behind it but not the 2D\n"
     "                        // layers (the sky showed through the near water as a blue band)\n"
     "                        AcwwSolid = Polygons[polygonIdx].Material == 1U && (AcwwFlags & 1U) != 0U;\n",
     "AcwwSolid = Polygons[polygonIdx]"),
    (SHADERS,
     "                        srcAttr &= ~(1U << 15);\n",
     "                        srcAttr &= ~(1U << 15);\n"
     "                    // acwwrecomp: our water marks its pixels (bit 4), so the next layer of\n"
     "                    // water blends with it the DS way, but it can go over the game's others\n"
     "                    if (Polygons[polygonIdx].Material == 1U && (AcwwFlags & 1U) != 0U)\n"
     "                        srcAttr |= 0x10U;\n",
     "srcAttr |= 0x10U;"),
    (SHADERS,
     "    if ((!isShadow || (attr & (1U<<22)) != 0U)\n"
     "        ? (attr & 0x007F0000U) != (blendAttr & 0x007F0000U)\n"
     "        : (attr & 0x3F000000U) != (srcAttr & 0x3F000000U))\n",
     "    // acwwrecomp: the DS skips a see-through layer over one with the same ID; near the\n"
     "    // camera that hid our water under the game's fogged blue layer, so ours goes over\n"
     "    if ((AcwwSolid && (attr & 0x10U) == 0U) ||\n"
     "        ((!isShadow || (attr & (1U<<22)) != 0U)\n"
     "        ? (attr & 0x007F0000U) != (blendAttr & 0x007F0000U)\n"
     "        : (attr & 0x3F000000U) != (srcAttr & 0x3F000000U)))\n",
     "(AcwwSolid && (attr & 0x10U) == 0U)"),
    (SHADERS,
     "    uint blendAttr = (srcAttr & 0xE0F0U) | ((srcAttr >> 8) & 0xFF0000U) | (1U<<22) | (attr & 0xFF001F0FU);\n",
     "    uint blendAttr = (srcAttr & 0xE0F0U) | ((srcAttr >> 8) & 0xFF0000U) | (1U<<22) | (attr & 0xFF001F0FU);\n"
     "    uint acwwOldAttr = attr;   // acwwrecomp: was our water here already?\n",
     "uint acwwOldAttr = attr;"),
    (SHADERS,
     "        uint dstA = color & 0x1F000000U;\n",
     "        uint dstA = color & 0x1F000000U;\n"
     "        // acwwrecomp: under our water, what the game drew mostly gives way to a deeper\n"
     "        // shade of the water itself; see-through in [look] says how much still shows\n"
     "        bool acwwDeep = AcwwSolid && (acwwOldAttr & 0x10U) == 0U;\n"
     "        if (acwwDeep)\n"
     "        {\n"
     "            vec3 acwwSrc = vec3(float(tileColor & 0x3FU), float((tileColor >> 8) & 0x3FU),\n"
     "                float((tileColor >> 16) & 0x3FU));\n"
     "            vec3 acwwDst = vec3(float(color & 0x3FU), float((color >> 8) & 0x3FU),\n"
     "                float((color >> 16) & 0x3FU));\n"
     "            float acwwSee = (dstA != 0U && (acwwOldAttr & 0x20U) == 0U) ? clamp(AcwwLook[3].z, 0.0, 1.0) : 0.0;\n"
     "            uvec3 acwwU = uvec3(clamp(mix(acwwSrc * 0.62, acwwDst, acwwSee) + 0.5, 0.0, 63.0));\n"
     "            dstRB = acwwU.r | (acwwU.b << 16);\n"
     "            dstG = acwwU.g << 8;\n"
     "        }\n",
     "bool acwwDeep = AcwwSolid"),
    (SHADERS,
     "        if (dstA != 0)\n",
     "        if (dstA != 0 || acwwDeep)\n",
     "if (dstA != 0 || acwwDeep)"),
    (SHADERS,
     "        uint alpha = (srcA >> 24) + 1;\n",
     "        uint alpha = (srcA >> 24) + 1;\n"
     "        // acwwrecomp: our water's strength comes from opacity in [look], not the\n"
     "        // game's alpha for that polygon (higher near the camera), and every layer\n"
     "        // of water aims for the same shade, however many the game draws there\n"
     "        float acwwW = clamp(0.5 * AcwwLook[3].y, 0.0, 1.0);\n"
     "        float acwwK = mix(0.62, 1.0, acwwW);\n"
     "        if (acwwDeep)\n"
     "            alpha = uint(acwwW * 32.0 + 0.5);\n"
     "        else if (AcwwSolid)\n"
     "        {\n"
     "            uint acwwR = uint(float(srcRB & 0x3FU) * acwwK + 0.5);\n"
     "            uint acwwB = uint(float((srcRB >> 16) & 0x3FU) * acwwK + 0.5);\n"
     "            srcRB = acwwR | (acwwB << 16);\n"
     "            srcG = uint(float((srcG >> 8) & 0x3FU) * acwwK + 0.5) << 8;\n"
     "        }\n",
     "float acwwK = mix(0.62, 1.0, acwwW);"),
    (SHADERS,   # (an older patch: everything under the water showed see-through of it)
     "            float acwwSee = dstA != 0U ? clamp(AcwwLook[3].z, 0.0, 1.0) : 0.0;\n",
     "            float acwwSee = (dstA != 0U && (acwwOldAttr & 0x20U) == 0U) ? clamp(AcwwLook[3].z, 0.0, 1.0) : 0.0;\n",
     "(acwwOldAttr & 0x20U) == 0U"),
    (SHADERS,
     "                        srcAttr |= 0x10U;\n",
     "                        srcAttr |= 0x10U;\n"
     "                    // acwwrecomp: and a layer marked under-water (B) marks its pixels (bit 5),\n"
     "                    // so our water covers it completely\n"
     "                    if (Polygons[polygonIdx].Material == 4U && (AcwwFlags & 1U) != 0U)\n"
     "                        srcAttr |= 0x20U;\n",
     "srcAttr |= 0x20U;"),
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
     "                if (pick_key == SDL_SCANCODE_M || pick_key == SDL_SCANCODE_F ||\n"
     "                    pick_key == SDL_SCANCODE_H || pick_key == SDL_SCANCODE_B) {\n"
     "                    acww_materials::press_mark(pick_key == SDL_SCANCODE_F ? acww_materials::kFalls\n"
     "                        : pick_key == SDL_SCANCODE_H ? acww_materials::kHide\n"
     "                        : pick_key == SDL_SCANCODE_B ? acww_materials::kUnder : acww_materials::kWater);\n"
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
    (FRONTEND,   # (an older patch: H hides)
     "                if (pick_key == SDL_SCANCODE_M || pick_key == SDL_SCANCODE_F) {\n"
     "                    acww_materials::press_mark(pick_key == SDL_SCANCODE_F\n"
     "                        ? acww_materials::kFalls : acww_materials::kWater);\n",
     "                if (pick_key == SDL_SCANCODE_M || pick_key == SDL_SCANCODE_F ||\n"
     "                    pick_key == SDL_SCANCODE_H) {\n"
     "                    acww_materials::press_mark(pick_key == SDL_SCANCODE_F ? acww_materials::kFalls\n"
     "                        : pick_key == SDL_SCANCODE_H ? acww_materials::kHide : acww_materials::kWater);\n",
     "pick_key == SDL_SCANCODE_H"),
    (FRONTEND,   # (an older patch: B marks a layer as under the water)
     "                    pick_key == SDL_SCANCODE_H) {\n"
     "                    acww_materials::press_mark(pick_key == SDL_SCANCODE_F ? acww_materials::kFalls\n"
     "                        : pick_key == SDL_SCANCODE_H ? acww_materials::kHide : acww_materials::kWater);\n",
     "                    pick_key == SDL_SCANCODE_H || pick_key == SDL_SCANCODE_B) {\n"
     "                    acww_materials::press_mark(pick_key == SDL_SCANCODE_F ? acww_materials::kFalls\n"
     "                        : pick_key == SDL_SCANCODE_H ? acww_materials::kHide\n"
     "                        : pick_key == SDL_SCANCODE_B ? acww_materials::kUnder : acww_materials::kWater);\n",
     "pick_key == SDL_SCANCODE_B) {"),
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
# one: (file, the text the block starts with, the text that ends it, or a
# list of those to try in turn, newest first).
BLOCKS = [
    (SHADERS, "// acwwrecomp: material effects (tools/patch_materials.py)", "#endif\n",
     WATER_GLSL.lstrip("\n")),
    (SHADERS, APPLY_GLSL.split("\n", 2)[0] + "\n" + APPLY_GLSL.split("\n", 2)[1] + "\n",
     ("\n// acwwrecomp: end of the material effect\n", "#endif // acwwrecomp: end of the material effect\n",
      "            }\n#endif\n"), APPLY_GLSL),
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

    for rel, begin, ends, block in BLOCKS:
        text, crlf = texts[rel]
        at = text.find(begin)
        stop = -1
        for end in (ends if isinstance(ends, tuple) else (ends,)):
            if at >= 0 and text.find(end, at) >= 0:
                stop = text.find(end, at) + len(end)
                break
        if at < 0 or stop < 0:
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

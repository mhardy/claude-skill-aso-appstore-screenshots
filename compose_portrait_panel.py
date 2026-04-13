#!/usr/bin/env python3
"""
Portrait Floating Panel Screenshot Composer (1290×2796)

Layout:
  - Top band: brand colour + headline text (vertically centred)
  - Floating panel: app screenshot as a rounded card with drop shadow,
    centred in the remaining canvas space
  - Background: brand colour throughout

Used for non-keyboard screenshots (modals, sheets) that don't work
in the panoramic format.
"""

import argparse
from PIL import Image, ImageDraw, ImageFont

CANVAS_W = 1290
CANVAS_H = 2796

# Text band
TEXT_SECTION_H = 750

# Panel geometry
PANEL_W = 1180
PANEL_MARGIN = (CANVAS_W - PANEL_W) // 2   # 55px each side
CORNER_R = 28
SHADOW_DEPTH = 22
SHADOW_ALPHA_MAX = 90

# Typography
VERB_SIZE_MAX = 300
VERB_SIZE_MIN = 80
DESC_SIZE = 110
VERB_DESC_GAP = 28
DESC_LINE_GAP = 18
MAX_TEXT_W = int(CANVAS_W * 0.88)  # 1135px

FONT_PATH = "/Library/Fonts/SF-Pro-Display-Black.otf"


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def word_wrap(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_font(text, max_w, size_max, size_min):
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for size in range(size_max, size_min - 1, -4):
        font = ImageFont.truetype(FONT_PATH, size)
        bbox = dummy.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_w:
            return font
    return ImageFont.truetype(FONT_PATH, size_min)


def compose(bg_hex, verb, desc, screenshot_path, output_path):
    bg = hex_to_rgb(bg_hex)
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (*bg, 255))
    draw = ImageDraw.Draw(canvas)

    # ── Headline text ──────────────────────────────────────────────────
    verb_font = fit_font(verb.upper(), MAX_TEXT_W, VERB_SIZE_MAX, VERB_SIZE_MIN)
    desc_font = ImageFont.truetype(FONT_PATH, DESC_SIZE)

    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    verb_bbox = dummy.textbbox((0, 0), verb.upper(), font=verb_font)
    verb_h = verb_bbox[3] - verb_bbox[1]

    desc_lines = word_wrap(dummy, desc.upper(), desc_font, MAX_TEXT_W)
    desc_h = 0
    for line in desc_lines:
        b = dummy.textbbox((0, 0), line, font=desc_font)
        desc_h += (b[3] - b[1]) + DESC_LINE_GAP
    total_h = verb_h + VERB_DESC_GAP + desc_h

    y = (TEXT_SECTION_H - total_h) // 2
    draw.text((CANVAS_W // 2, y - verb_bbox[1]), verb.upper(),
              fill="white", font=verb_font, anchor="mt")
    y += verb_h + VERB_DESC_GAP
    for line in desc_lines:
        b = draw.textbbox((0, 0), line, font=desc_font)
        h = b[3] - b[1]
        draw.text((CANVAS_W // 2, y - b[1]), line,
                  fill="white", font=desc_font, anchor="mt")
        y += h + DESC_LINE_GAP

    # ── Floating panel ─────────────────────────────────────────────────
    shot = Image.open(screenshot_path).convert("RGBA")

    # Scale screenshot to panel width, maintaining aspect ratio
    scale = PANEL_W / shot.width
    panel_h = int(shot.height * scale)
    shot_scaled = shot.resize((PANEL_W, panel_h), Image.LANCZOS)

    # Position panel just below the text band with a small gap,
    # then nudge it down slightly so it sits in the upper-third of the
    # remaining space rather than hugging the text or being centred.
    remaining_h = CANVAS_H - TEXT_SECTION_H
    panel_x = PANEL_MARGIN
    panel_y = TEXT_SECTION_H + max(80, (remaining_h - panel_h) // 4)

    # Drop shadow (layered semi-transparent rounded rects)
    shadow_layer = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    for i in range(SHADOW_DEPTH, 0, -1):
        alpha = int(SHADOW_ALPHA_MAX * (1 - (i - 1) / SHADOW_DEPTH))
        shadow_draw.rounded_rectangle(
            [panel_x - i, panel_y - i + 16,
             panel_x + PANEL_W + i, panel_y + panel_h + i + 16],
            radius=CORNER_R + i,
            fill=(0, 0, 0, alpha)
        )
    canvas = Image.alpha_composite(canvas, shadow_layer)

    # Panel image with rounded corners
    mask = Image.new("L", (PANEL_W, panel_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, PANEL_W - 1, panel_h - 1], radius=CORNER_R, fill=255
    )
    shot_scaled.putalpha(mask)
    canvas.paste(shot_scaled, (panel_x, panel_y), shot_scaled)

    canvas.convert("RGB").save(output_path, "PNG")
    print(f"✓ {output_path} ({CANVAS_W}×{CANVAS_H})")


def main():
    p = argparse.ArgumentParser(description="Compose portrait floating panel App Store screenshot")
    p.add_argument("--bg", required=True, help="Background hex colour e.g. #4F46E5")
    p.add_argument("--verb", required=True, help="Action verb e.g. EXPLORE")
    p.add_argument("--desc", required=True, help="Benefit descriptor")
    p.add_argument("--screenshot", required=True, help="Screenshot path")
    p.add_argument("--output", required=True, help="Output PNG path")
    args = p.parse_args()
    compose(args.bg, args.verb, args.desc, args.screenshot, args.output)


if __name__ == "__main__":
    main()

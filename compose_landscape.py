#!/usr/bin/env python3
"""
Landscape App Store Screenshot Composer (2796×1290)
Sidebar layout: brand-colour panel on left with headline text,
full-height app screenshot filling the right section.

This ensures the screenshot always scales to full canvas height,
so key proportions are exactly as they appear in the app.
"""

import argparse
from PIL import Image, ImageDraw, ImageFont

CANVAS_W = 2796
CANVAS_H = 1290

# Layout — sidebar on left, screenshot on right
SIDEBAR_W = 750
TEXT_PADDING_X = 65          # padding inside sidebar
MAX_TEXT_W = SIDEBAR_W - 2 * TEXT_PADDING_X   # 620px

# Typography
VERB_SIZE_MAX = 180
VERB_SIZE_MIN = 60
DESC_SIZE = 70
VERB_DESC_GAP = 20
DESC_LINE_GAP = 16

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

    # ── Text in sidebar ────────────────────────────────────────────────
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

    # Vertically centre text in the sidebar
    text_center_x = SIDEBAR_W // 2
    y = (CANVAS_H - total_h) // 2

    draw.text((text_center_x, y - verb_bbox[1]), verb.upper(),
              fill="white", font=verb_font, anchor="mt")
    y += verb_h + VERB_DESC_GAP

    for line in desc_lines:
        b = draw.textbbox((0, 0), line, font=desc_font)
        h = b[3] - b[1]
        draw.text((text_center_x, y - b[1]), line,
                  fill="white", font=desc_font, anchor="mt")
        y += h + DESC_LINE_GAP

    # ── Screenshot — scale to full canvas height, crop centre ─────────
    shot = Image.open(screenshot_path).convert("RGBA")
    right_w = CANVAS_W - SIDEBAR_W   # 2046px

    # Scale to full canvas height so key proportions are exact
    scale = CANVAS_H / shot.height
    sc_h = CANVAS_H
    sc_w = int(shot.width * scale)
    shot = shot.resize((sc_w, sc_h), Image.LANCZOS)

    # Centre-crop to the right section width
    if sc_w > right_w:
        offset_x = (sc_w - right_w) // 2
        shot = shot.crop((offset_x, 0, offset_x + right_w, sc_h))
    else:
        # Narrower than section — pad with background colour
        padded = Image.new("RGBA", (right_w, sc_h), (*bg, 255))
        padded.paste(shot, ((right_w - sc_w) // 2, 0))
        shot = padded

    canvas.paste(shot, (SIDEBAR_W, 0))

    # Subtle shadow on the right edge of the sidebar for depth
    for i in range(18):
        alpha = int(80 * (1 - i / 18))
        shadow = Image.new("RGBA", (1, CANVAS_H), (0, 0, 0, alpha))
        canvas.paste(shadow, (SIDEBAR_W + i, 0), shadow)

    canvas.convert("RGB").save(output_path, "PNG")
    print(f"✓ {output_path} ({CANVAS_W}×{CANVAS_H})")


def main():
    p = argparse.ArgumentParser(description="Compose landscape App Store screenshot")
    p.add_argument("--bg", required=True, help="Background hex colour (#4F46E5)")
    p.add_argument("--verb", required=True, help="Action verb")
    p.add_argument("--desc", required=True, help="Benefit descriptor")
    p.add_argument("--screenshot", required=True, help="Simulator screenshot path")
    p.add_argument("--output", required=True, help="Output PNG path")
    args = p.parse_args()
    compose(args.bg, args.verb, args.desc, args.screenshot, args.output)


if __name__ == "__main__":
    main()

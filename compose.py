#!/usr/bin/env python3
"""
App Store Screenshot Composer
Composites headline text, device frame template, and app screenshot
into a pixel-perfect 1290×2796 App Store Connect image.

The device frame is positioned dynamically based on text height,
matching the proportions seen in professional App Store screenshots.
"""

import argparse
import os
from PIL import Image, ImageDraw, ImageFont, ImageChops

from fonts import find_font

# ── Canvas ──────────────────────────────────────────────────────────
CANVAS_W = 1290
CANVAS_H = 2796

# ── Device frame: real iPhone 15 Pro PNG (not hand-drawn) ───────────
DEVICE_W = 1030                      # device width on canvas
FRAME_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "assets", "iPhone15ProFrameBlack.png")
# Screen cutout box (x0, y0, x1, y1), measured from the frame PNG's own
# alpha channel at its native 1293x2656 size — the transparent hole that
# isn't reachable by flood-filling in from an outside corner.
FRAME_CUTOUT = (58, 50, 1237, 2606)

# ── Layout ──────────────────────────────────────────────────────────
DEVICE_Y = 720                       # device top position (fixed)
MIN_TEXT_DEVICE_GAP = 40             # minimum gap between text bottom and device top

# ── Typography ──────────────────────────────────────────────────────
VERB_SIZE_MAX = 256
VERB_SIZE_MIN = 150
DESC_SIZE = 124
VERB_DESC_GAP = 20
DESC_LINE_GAP = 24
MAX_TEXT_W = int(CANVAS_W * 0.92)
MAX_VERB_W = int(CANVAS_W * 0.92)

FONT_PATH = find_font("SF-Pro-Display-Black.otf")


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


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
    """Return the largest font size where text fits within max_w."""
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for size in range(size_max, size_min - 1, -4):
        font = ImageFont.truetype(FONT_PATH, size)
        bbox = dummy.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_w:
            return font
    return ImageFont.truetype(FONT_PATH, size_min)


def draw_centered(draw, y, text, font, max_w=None):
    lines = word_wrap(draw, text, font, max_w) if max_w else [text]
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        # Use anchor="mt" (middle-top) for pixel-perfect horizontal centering
        # Adjust y by bbox[1] offset so text top aligns with intended position
        draw.text((CANVAS_W // 2, y - bbox[1]), line, fill="white", font=font, anchor="mt")
        y += h + DESC_LINE_GAP
    return y


def device_layer(shot, dev_x, dev_y, dev_w):
    """Composite the screenshot behind the real frame PNG, clipped to its
    silhouette so screen corners never poke past the frame's rounded edges.

    The frame's own alpha supplies the bezel, rails, buttons and Dynamic
    Island — nothing here is hand-drawn.
    """
    frame = Image.open(FRAME_PATH).convert("RGBA")
    scale = dev_w / frame.width
    fw, fh = dev_w, round(frame.height * scale)
    frame = frame.resize((fw, fh), Image.LANCZOS)

    cx0, cy0, cx1, cy1 = (round(v * scale) for v in FRAME_CUTOUT)
    # cover the cutout; the bezel hides any sliver of aspect mismatch
    shot_scale = max((cx1 - cx0) / shot.width, (cy1 - cy0) / shot.height)
    screen_w = round(shot.width * shot_scale)
    screen_h = round(shot.height * shot_scale)
    shot_r = shot.resize((screen_w, screen_h), Image.LANCZOS)

    sx = dev_x + (cx0 + cx1) // 2 - screen_w // 2
    sy = dev_y + cy0 - 8          # tuck under the bezel's soft inner edge
    size = (CANVAS_W, max(CANVAS_H, dev_y + fh + 10, sy + screen_h + 10))

    # filled phone silhouette: everything not reachable from the outside corner
    sil = frame.split()[3].point(lambda v: 255 if v > 8 else 0)
    pad = Image.new("L", (fw + 2, fh + 2), 0)
    pad.paste(sil, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128, thresh=0)
    sil = pad.crop((1, 1, fw + 1, fh + 1)).point(lambda v: 0 if v == 128 else 255)
    sil_full = Image.new("L", size, 0)
    sil_full.paste(sil, (dev_x, dev_y))

    scr = Image.new("RGBA", size, (0, 0, 0, 0))
    scr.paste(shot_r, (sx, sy))
    scr.putalpha(ImageChops.multiply(scr.split()[3], sil_full))

    fl = Image.new("RGBA", size, (0, 0, 0, 0))
    fl.paste(frame, (dev_x, dev_y))
    dev = Image.alpha_composite(scr, fl)          # frame on top of screen

    return dev.crop((0, 0, CANVAS_W, CANVAS_H))


def compose(bg_hex, verb, desc, screenshot_path, output_path):
    bg = hex_to_rgb(bg_hex)

    # ── 1. Canvas ───────────────────────────────────────────────────
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (*bg, 255))
    draw = ImageDraw.Draw(canvas)

    # ── 2. Headline text at fixed position ───────────────────────────
    verb_font = fit_font(verb.upper(), MAX_VERB_W, VERB_SIZE_MAX, VERB_SIZE_MIN)
    desc_font = ImageFont.truetype(FONT_PATH, DESC_SIZE)

    y = 200
    y = draw_centered(draw, y, verb.upper(), verb_font)
    y += VERB_DESC_GAP
    draw_centered(draw, y, desc.upper(), desc_font, max_w=MAX_TEXT_W)

    # ── 3. Screenshot + real device frame ────────────────────────────
    device_x = (CANVAS_W - DEVICE_W) // 2
    shot = Image.open(screenshot_path).convert("RGB")
    dev = device_layer(shot, device_x, DEVICE_Y, DEVICE_W)
    canvas = Image.alpha_composite(canvas, dev)

    # ── 4. Save ────────────────────────────────────────────────────
    canvas.convert("RGB").save(output_path, "PNG")
    print(f"OK {output_path} ({CANVAS_W}x{CANVAS_H})")


def main():
    p = argparse.ArgumentParser(description="Compose App Store screenshot")
    p.add_argument("--bg", required=True, help="Background hex colour (#E31837)")
    p.add_argument("--verb", required=True, help="Action verb (TRACK)")
    p.add_argument("--desc", required=True, help="Benefit descriptor (TRADING CARD PRICES)")
    p.add_argument("--screenshot", required=True, help="Simulator screenshot path")
    p.add_argument("--output", required=True, help="Output file path")
    args = p.parse_args()

    compose(args.bg, args.verb, args.desc, args.screenshot, args.output)


if __name__ == "__main__":
    main()

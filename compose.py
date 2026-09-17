#!/usr/bin/env python3
"""
App Store Screenshot Composer
Composites headline text, a real device frame, and an app screenshot into a
pixel-perfect 1290×2796 App Store Connect image — plus optional breakout
cards, badges, callouts and a gradient background for when the scaffold
itself needs to be the finished, deterministic image (no AI enhancement
pass afterward).

Everything here is plain PIL compositing: no text or app pixels are ever
sent to an AI model, so captions stay crisp and OCR-indexable and the app
screenshot stays pixel-faithful.
"""

import argparse
import json
import math
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

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

FONT_BLACK = find_font("SF-Pro-Display-Black.otf")
FONT_HEAVY = find_font("SF-Pro-Display-Heavy.otf")
FONT_PATH = FONT_BLACK               # back-compat alias


# ---------------------------------------------------------------- colour
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def darken(rgb, factor):
    return tuple(round(c * factor) for c in rgb)


def text_colour_for(rgb):
    """Dark text on light pills, white text on dark pills."""
    r, g, b = rgb
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#101010" if luminance > 150 else "#FFFFFF"


# ---------------------------------------------------------------- text
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


def fit_font(text, max_w, size_max, size_min, font_path=None):
    """Return the largest font size where text fits within max_w."""
    font_path = font_path or FONT_BLACK
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for size in range(size_max, size_min - 1, -4):
        font = ImageFont.truetype(font_path, size)
        bbox = dummy.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_w:
            return font
    return ImageFont.truetype(font_path, size_min)


def draw_centered(draw, y, text, font, max_w=None):
    lines = word_wrap(draw, text, font, max_w) if max_w else [text]
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        # anchor="mt" for pixel-perfect horizontal centering; adjust y by
        # bbox[1] offset so the text's visual top lands at the intended y
        draw.text((CANVAS_W // 2, y - bbox[1]), line, fill="white", font=font, anchor="mt")
        y += h + DESC_LINE_GAP
    return y


# ---------------------------------------------------------------- layer helpers
def vgrad(size, top, bot):
    w, h = size
    g = Image.new("RGB", (1, h))
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = y / max(1, h - 1)
        d.point((0, y), fill=tuple(round(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    return g.resize((w, h), Image.BICUBIC).convert("RGBA")


def radial_glow(size, cx, cy, rx, ry, color, strength=1.0, falloff=2.2):
    w, h = size
    sw = 200
    sh = int(sw * h / w)
    m = Image.new("L", (sw, sh))
    px = m.load()
    for y in range(sh):
        for x in range(sw):
            dx = (x / sw * w - cx) / rx
            dy = (y / sh * h - cy) / ry
            v = max(0.0, 1.0 - math.hypot(dx, dy)) ** falloff
            px[x, y] = int(255 * v * strength)
    m = m.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(40))
    lay = Image.new("RGBA", (w, h), (*color, 0))
    lay.putalpha(m)
    return lay


def screen_blend(base, layer):
    b = base.convert("RGB")
    a = layer.split()[3]
    return Image.composite(ImageChops.screen(b, layer.convert("RGB")), b, a).convert("RGBA")


def rrect_mask(size, box, r, ss=4):
    w, h = size
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [box[0] * ss, box[1] * ss, box[2] * ss, box[3] * ss], radius=r * ss, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def drop_shadow(mask, blur, offset=(0, 0), opacity=255, color=(0, 0, 0)):
    s = mask.filter(ImageFilter.GaussianBlur(blur))
    if opacity < 255:
        s = s.point(lambda v: v * opacity // 255)
    lay = Image.new("RGBA", mask.size, (*color, 0))
    lay.putalpha(s)
    return ImageChops.offset(lay, offset[0], offset[1]) if offset != (0, 0) else lay


# ---------------------------------------------------------------- background
def flat_canvas(bg_hex):
    return Image.new("RGBA", (CANVAS_W, CANVAS_H), (*hex_to_rgb(bg_hex), 255))


def gradient_canvas(bg_hex):
    """Dark radial-glow gradient built from the brand colour — richer than a
    flat fill, used when --gradient is passed instead of a solid background."""
    base = hex_to_rgb(bg_hex)
    c = vgrad((CANVAS_W, CANVAS_H), darken(base, 0.32), darken(base, 0.07))
    c = screen_blend(c, radial_glow((CANVAS_W, CANVAS_H), CANVAS_W * .5, CANVAS_H * .52,
                                    CANVAS_W * .95, CANVAS_H * .40, base, .55))
    c = screen_blend(c, radial_glow((CANVAS_W, CANVAS_H), CANVAS_W * .5, CANVAS_H * .40,
                                    CANVAS_W * .62, CANVAS_H * .22, base, .35, 2.6))
    return c


# ---------------------------------------------------------------- device
def device_layer(shot, dev_x, dev_y, dev_w):
    """Composite the screenshot behind the real frame PNG, clipped to its
    silhouette so screen corners never poke past the frame's rounded edges.

    The frame's own alpha supplies the bezel, rails, buttons and Dynamic
    Island — nothing here is hand-drawn. Returns (device_rgba, body_mask,
    screen_rect) — body_mask is the filled silhouette (for casting a drop
    shadow), screen_rect is (sx, sy, screen_w, screen_h, shot_scale) for
    positioning breakout cards relative to the on-screen content.
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

    # shadow mask = frame silhouette filled (screen hole included)
    body = Image.new("L", size, 0)
    body.paste(frame.split()[3], (dev_x, dev_y))
    hole = Image.new("L", size, 0)
    ImageDraw.Draw(hole).rectangle([sx, sy, sx + screen_w, sy + screen_h], fill=255)
    body = ImageChops.lighter(body, hole)

    return (dev.crop((0, 0, CANVAS_W, CANVAS_H)), body.crop((0, 0, CANVAS_W, CANVAS_H)),
            (sx, sy, screen_w, screen_h, shot_scale))


# ---------------------------------------------------------------- breakout / callouts
def breakout_card(canvas, shot, src_box, screen_rect, zoom=1.30, corner=36,
                  ring=True, dy=0):
    """Lift a real UI card out of the screenshot, scale it up, float it over
    both bezels with a shadow. Returns (canvas, placed_box)."""
    sx, sy, screen_w, screen_h, scale = screen_rect
    x0, y0, x1, y1 = src_box
    card = shot.crop(src_box).convert("RGBA")

    out_w = int((x1 - x0) * scale * zoom)
    out_h = int((y1 - y0) * scale * zoom)
    card = card.resize((out_w, out_h), Image.LANCZOS)

    cx = CANVAS_W // 2
    on_screen_cy = sy + (y0 + y1) / 2 * scale
    px, py = cx - out_w // 2, int(on_screen_cy - out_h / 2) + dy

    m = rrect_mask((CANVAS_W, CANVAS_H), (px, py, px + out_w, py + out_h), int(corner * scale * zoom))
    canvas = Image.alpha_composite(canvas, drop_shadow(m, 55, (0, 34), 215))
    canvas = Image.alpha_composite(canvas, drop_shadow(m, 130, (0, 62), 130))

    lay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    lay.paste(card, (px, py))
    lay.putalpha(ImageChops.multiply(lay.split()[3], m))
    canvas = Image.alpha_composite(canvas, lay)

    if ring:
        r = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        ImageDraw.Draw(r).rounded_rectangle(
            [px, py, px + out_w, py + out_h],
            radius=int(corner * scale * zoom), outline=(255, 255, 255, 70), width=3)
        r.putalpha(ImageChops.multiply(r.split()[3], m))
        canvas = Image.alpha_composite(canvas, r)

    return canvas, (px, py, px + out_w, py + out_h)


def badge(canvas, text, xy, accent_hex, size=42, anchor="tl"):
    """Accent pill pinned onto a corner of the breakout card (or anywhere)."""
    accent = hex_to_rgb(accent_hex)
    text_col = text_colour_for(accent)
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(FONT_HEAVY, size)
    tw = d.textlength(text, font=f)
    bw, bh = int(tw + 60), int(size * 1.02 + 34)
    x, y = xy
    if anchor.endswith("r"):
        x -= bw
    if anchor.startswith("b"):
        y -= bh
    m = rrect_mask((CANVAS_W, CANVAS_H), (x, y, x + bw, y + bh), bh // 2)
    canvas = Image.alpha_composite(canvas, drop_shadow(m, 30, (0, 14), 185))
    pill = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([x, y, x + bw, y + bh], radius=bh // 2,
                                           fill=(*accent, 255))
    canvas = Image.alpha_composite(canvas, pill)
    ImageDraw.Draw(canvas).text((x + bw / 2, y + bh / 2), text, font=f,
                                fill=text_col, anchor="mm")
    return canvas


def callout(canvas, text, anchor_xy, label_xy, accent_hex, side="left", size=44):
    """Accent pill + elbow leader line pointing at a spot on the artwork."""
    accent = hex_to_rgb(accent_hex)
    text_col = text_colour_for(accent)
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(FONT_HEAVY, size)
    tw = d.textlength(text, font=f)
    pad_x, pad_y = 30, 19
    bw, bh = int(tw + pad_x * 2), int(size * 1.02 + pad_y * 2)
    lx, ly = label_xy
    if side == "right":
        lx -= bw

    ax, ay = anchor_xy
    py_c = ly + bh // 2
    mid_x = (lx + bw + ax) // 2 if side == "left" else (lx + ax) // 2
    start_x = lx + bw if side == "left" else lx

    ln = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(ln)
    ld.line([(start_x, py_c), (mid_x, py_c), (mid_x, ay), (ax, ay)],
            fill=(*accent, 255), width=5, joint="curve")
    ld.ellipse([ax - 13, ay - 13, ax + 13, ay + 13], outline=(*accent, 255), width=5)
    canvas = Image.alpha_composite(canvas, ln)

    pm = rrect_mask((CANVAS_W, CANVAS_H), (lx, ly, lx + bw, ly + bh), bh // 2)
    canvas = Image.alpha_composite(canvas, drop_shadow(pm, 26, (0, 12), 160))
    pill = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([lx, ly, lx + bw, ly + bh],
                                           radius=bh // 2, fill=(*accent, 255))
    canvas = Image.alpha_composite(canvas, pill)
    ImageDraw.Draw(canvas).text((lx + bw / 2, ly + bh / 2), text, font=f,
                                fill=text_col, anchor="mm")
    return canvas


# ---------------------------------------------------------------- page
def compose(bg_hex, verb, desc, screenshot_path, output_path, gradient=False,
            accent_hex=None, breakout=None, badges=(), callouts=()):
    accent_hex = accent_hex or bg_hex

    # ── 1. Canvas ───────────────────────────────────────────────────
    canvas = (gradient_canvas(bg_hex) if gradient else flat_canvas(bg_hex))
    draw = ImageDraw.Draw(canvas)

    # ── 2. Headline text at fixed position ───────────────────────────
    verb_font = fit_font(verb.upper(), MAX_VERB_W, VERB_SIZE_MAX, VERB_SIZE_MIN)
    desc_font = ImageFont.truetype(FONT_BLACK, DESC_SIZE)

    y = 200
    y = draw_centered(draw, y, verb.upper(), verb_font)
    y += VERB_DESC_GAP
    draw_centered(draw, y, desc.upper(), desc_font, max_w=MAX_TEXT_W)

    # ── 3. Screenshot + real device frame ────────────────────────────
    device_x = (CANVAS_W - DEVICE_W) // 2
    shot = Image.open(screenshot_path).convert("RGB")
    dev, body_mask, screen_rect = device_layer(shot, device_x, DEVICE_Y, DEVICE_W)

    if gradient:
        canvas = Image.alpha_composite(canvas, drop_shadow(body_mask, 170, (0, 70), 125))
        canvas = Image.alpha_composite(canvas, drop_shadow(body_mask, 70, (0, 30), 195))
    canvas = Image.alpha_composite(canvas, dev)

    # ── 4. Breakout card ──────────────────────────────────────────────
    if breakout:
        canvas, _ = breakout_card(canvas, shot, tuple(breakout["box"]), screen_rect,
                                  zoom=breakout.get("zoom", 1.30),
                                  dy=breakout.get("dy", 0))

    # ── 5. Badges + callouts ──────────────────────────────────────────
    for b in badges:
        canvas = badge(canvas, b["text"], tuple(b["xy"]),
                       b.get("accent", accent_hex), anchor=b.get("anchor", "tl"))
    for c in callouts:
        canvas = callout(canvas, c["text"], tuple(c["anchor"]), tuple(c["label"]),
                         c.get("accent", accent_hex), side=c.get("side", "left"))

    # ── 6. Save ────────────────────────────────────────────────────
    canvas.convert("RGB").save(output_path, "PNG")
    print(f"OK {output_path} ({CANVAS_W}x{CANVAS_H})")


def main():
    p = argparse.ArgumentParser(description="Compose App Store screenshot")
    p.add_argument("--bg", required=True, help="Background hex colour (#E31837)")
    p.add_argument("--verb", required=True, help="Action verb (TRACK)")
    p.add_argument("--desc", required=True, help="Benefit descriptor (TRADING CARD PRICES)")
    p.add_argument("--screenshot", required=True, help="Simulator screenshot path")
    p.add_argument("--output", required=True, help="Output file path")
    p.add_argument("--gradient", action="store_true",
                   help="Use a dark radial-glow gradient (built from --bg) instead of a flat fill")
    p.add_argument("--accent", help="Hex colour for badge/callout pills (defaults to --bg)")
    p.add_argument("--breakout",
                   help='JSON: {"box":[x0,y0,x1,y1],"zoom":1.3,"dy":0} — a UI card '
                        'cropped from the screenshot (in its own pixel coords) that pops '
                        'out over the device frame')
    p.add_argument("--badges",
                   help='JSON array: [{"text":"...","xy":[x,y],"anchor":"tl"}] — '
                        'accent pills pinned to a point on the canvas')
    p.add_argument("--callouts",
                   help='JSON array: [{"text":"...","anchor":[x,y],"label":[x,y],'
                        '"side":"left"}] — pill with a leader line pointing at a spot')
    args = p.parse_args()

    breakout = json.loads(args.breakout) if args.breakout else None
    badges = json.loads(args.badges) if args.badges else ()
    callouts = json.loads(args.callouts) if args.callouts else ()

    compose(args.bg, args.verb, args.desc, args.screenshot, args.output,
            gradient=args.gradient, accent_hex=args.accent,
            breakout=breakout, badges=badges, callouts=callouts)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Usage: generate-card.py "headline text" out.png ["RUBRIC LABEL"] ["#accentHex"]"""
import math
import sys

from PIL import Image, ImageDraw, ImageFont

headline = sys.argv[1]
out_file = sys.argv[2]
rubric_label = sys.argv[3] if len(sys.argv) > 3 else "AI БЕЗ ВОДЫ"
accent_hex = sys.argv[4] if len(sys.argv) > 4 else "#8B5CF6"


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


ACCENT = hex_to_rgb(accent_hex)
VIOLET = (109, 40, 217)
TEAL = (14, 165, 164)
BASE = (11, 17, 32)

W = H = 1024


def add_glow(base_img, cx, cy, radius, color, max_alpha=200, steps=48):
    glow = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    for i in range(steps, 0, -1):
        r = radius * i / steps
        alpha = int(max_alpha * (1 - i / steps) ** 2)
        gdraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, alpha))
    base_img.alpha_composite(glow)


def load_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


img = Image.new("RGBA", (W, H), (*BASE, 255))
add_glow(img, 160, 180, 460, VIOLET)
add_glow(img, 900, 260, 400, ACCENT)
add_glow(img, 250, 950, 420, TEAL)

overlay = Image.new("RGBA", img.size, (*BASE, 60))
img.alpha_composite(overlay)

draw = ImageDraw.Draw(img)
tag_font = load_font(32)
headline_font = load_font(64)

pad_x, pad_y = 36, 18
bbox = draw.textbbox((0, 0), rubric_label, font=tag_font)
tag_w = (bbox[2] - bbox[0]) + pad_x * 2
tag_h = (bbox[3] - bbox[1]) + pad_y * 2
tag_x, tag_y = 80, 90
draw.rounded_rectangle([tag_x, tag_y, tag_x + tag_w, tag_y + tag_h], radius=tag_h // 2, fill=ACCENT)
draw.text((tag_x + pad_x, tag_y + pad_y - bbox[1]), rubric_label, font=tag_font, fill=(0, 0, 0))

max_width = W - 160
words = headline.split()
lines, line = [], ""
for w in words:
    test = (line + " " + w).strip()
    bbox = draw.textbbox((0, 0), test, font=headline_font)
    if bbox[2] - bbox[0] > max_width and line:
        lines.append(line)
        line = w
    else:
        line = test
lines.append(line)

y = 320
for line in lines:
    draw.text((80, y), line, font=headline_font, fill=(255, 255, 255))
    y += 90

cx, cy, r = W - 110, H - 110, 45
for angle in range(0, 360, 72):
    rad = math.radians(angle)
    x = cx + r * math.cos(rad)
    y2 = cy + r * math.sin(rad)
    draw.line([(cx, cy), (x, y2)], fill=(255, 255, 255, 160), width=4)
    draw.ellipse([x - 7, y2 - 7, x + 7, y2 + 7], fill=(255, 255, 255))
draw.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], fill=(255, 255, 255))

img.convert("RGB").save(out_file)
print(f"Saved: {out_file}")

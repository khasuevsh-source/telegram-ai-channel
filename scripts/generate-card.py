#!/usr/bin/env python3
"""Usage: generate-card.py "headline text" out.png"""
import math
import sys

from PIL import Image, ImageDraw, ImageFont

headline, out_file = sys.argv[1], sys.argv[2]

W = H = 1024
img = Image.new("RGB", (W, H))
draw = ImageDraw.Draw(img)

c1 = (11, 18, 32)
c2 = (30, 27, 75)
for y in range(H):
    t = y / H
    r = int(c1[0] + (c2[0] - c1[0]) * t)
    g = int(c1[1] + (c2[1] - c1[1]) * t)
    b = int(c1[2] + (c2[2] - c1[2]) * t)
    draw.line([(0, y), (W, y)], fill=(r, g, b))

# brand mark: small node glyph, top-left corner
cx, cy, R = 110, 110, 55
for angle in range(0, 360, 72):
    rad = math.radians(angle)
    x = cx + R * math.cos(rad)
    y = cy + R * math.sin(rad)
    draw.line([(cx, cy), (x, y)], fill=(220, 220, 255), width=4)
    draw.ellipse([x - 9, y - 9, x + 9, y + 9], fill="white")
draw.ellipse([cx - 17, cy - 17, cx + 17, cy + 17], fill="white")

font = None
for path in (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
):
    try:
        font = ImageFont.truetype(path, 64)
        break
    except Exception:
        continue
if font is None:
    font = ImageFont.load_default()

words = headline.split()
lines, line = [], ""
for w in words:
    test = (line + " " + w).strip()
    bbox = draw.textbbox((0, 0), test, font=font)
    if bbox[2] - bbox[0] > W - 160:
        lines.append(line)
        line = w
    else:
        line = test
lines.append(line)

total_h = len(lines) * 80
y = (H - total_h) // 2 + 60
for line in lines:
    bbox = draw.textbbox((0, 0), line, font=font)
    x = (W - (bbox[2] - bbox[0])) // 2
    draw.text((x, y), line, font=font, fill="white")
    y += 80

img.save(out_file)
print(f"Saved: {out_file}")

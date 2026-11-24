#!/usr/bin/env python3
"""news-image-20261124: draw Tuesday 24 November 2026's world news as one
1024x1024 newspaper front page, using only the Python 3.13 standard library.

Five stories, each first reported on 24 November 2026 (verified against
Reuters / IRNA / AP datelines before this file was written):
  1. Strait of Hormuz - IRGC says three oil tankers hit naval mines and
     caught fire under US escort; the claim is unverified (IRNA, early Tue).
  2. Gaza - Israel kills Hamas internal security chief Naeem Abu Nahel, 50,
     in a Gaza City strike; seven killed across the Strip (Reuters, Nov 24).
  3. Ukraine - Russian overnight strike on Zaporizhzhia kills 2, wounds 40,
     four of them children (Reuters, Nov 24).
  4. Business - Sanofi agrees to buy Insmed for $41bn in cash, $175 a
     share, its biggest deal in 20 years (announced Tue Nov 24).
  5. Nepal - magnitude 5.6 quake near Olangchung Gola, Taplejung, at 7:17am;
     felt in Kathmandu, no casualties reported (Nov 24).

The picture is drawn from scratch with a small software rasterizer and a
hand-built stroke font, then encoded as a PNG with zlib. No network, no
randomness, no timestamps: two runs write byte-identical files.
Output goes to $MAKEFUN_OUTPUT_DIR/entry.png, or /output/entry.png.
"""

import os
import struct
import sys
import zlib

W = 1024
H = 1024

# --- palette: newsprint on cream paper -------------------------------------
PAPER = (248, 243, 230)
INK = (20, 20, 20)
RED = (178, 32, 44)
BLUE = (29, 78, 137)
SEA = (24, 68, 110)
SKY = (188, 214, 232)
GOLD = (212, 160, 40)
ORANGE = (230, 120, 30)
GREY = (120, 120, 116)
LIGHT = (225, 218, 200)
DARKBLUE = (16, 42, 68)
GREEN = (46, 110, 70)


class Canvas:
    """A plain RGB pixel buffer with a few flat drawing primitives."""

    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.clip = None  # (x0, y0, x1, y1) or None: art stays inside its panel
        buf = bytearray(w * h * 3)
        for i in range(w * h):
            buf[3 * i] = bg[0]
            buf[3 * i + 1] = bg[1]
            buf[3 * i + 2] = bg[2]
        self.px = buf

    def clip_to(self, x, y, w, h):
        self.clip = (int(x), int(y), int(x + w), int(y + h))

    def clip_clear(self):
        self.clip = None

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            if self.clip is not None:
                cx0, cy0, cx1, cy1 = self.clip
                if not (cx0 <= x < cx1 and cy0 <= y < cy1):
                    return
            i = (y * self.w + x) * 3
            self.px[i] = c[0]
            self.px[i + 1] = c[1]
            self.px[i + 2] = c[2]

    def rect(self, x, y, w, h, c):
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.w, int(x + w))
        y1 = min(self.h, int(y + h))
        for yy in range(y0, y1):
            base = (yy * self.w + x0) * 3
            for xx in range(x0, x1):
                i = base + (xx - x0) * 3
                self.px[i] = c[0]
                self.px[i + 1] = c[1]
                self.px[i + 2] = c[2]

    def disc(self, cx, cy, r, c):
        r = int(r)
        for yy in range(int(cy) - r, int(cy) + r + 1):
            for xx in range(int(cx) - r, int(cx) + r + 1):
                if (xx - cx) * (xx - cx) + (yy - cy) * (yy - cy) <= r * r:
                    self.set(xx, yy, c)

    def line(self, x0, y0, x1, y1, c, thick=1):
        """Bresenham line with a round brush of the given thickness."""
        x0, y0, x1, y1 = float(x0), float(y0), float(x1), float(y1)
        dx = x1 - x0
        dy = y1 - y0
        steps = int(max(abs(dx), abs(dy))) + 1
        r = max(0, (thick - 1) // 2)
        for s in range(steps + 1):
            t = s / steps if steps else 0.0
            x = int(round(x0 + dx * t))
            y = int(round(y0 + dy * t))
            if r <= 0:
                self.set(x, y, c)
            else:
                self.disc(x, y, r, c)

    def poly(self, pts, c):
        """Fill a polygon with the even-odd scanline rule."""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        y0, y1 = int(min(ys)), int(max(ys))
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x0, ya = pts[i]
                x1, yb = pts[(i + 1) % n]
                if ya == yb:
                    continue
                if (ya <= y < yb) or (yb <= y < ya):
                    t = (y - ya) / (yb - ya)
                    xs.append(x0 + t * (x1 - x0))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                xa, xb = int(xs[k]), int(xs[k + 1])
                for x in range(xa, xb + 1):
                    self.set(x, y, c)

    def outline_rect(self, x, y, w, h, c, thick=2):
        self.rect(x, y, w, thick, c)
        self.rect(x, y + h - thick, w, thick, c)
        self.rect(x, y, thick, h, c)
        self.rect(x + w - thick, y, thick, h, c)


# --- stroke font: capitals, digits and punctuation on an 8 x 12 grid -------
# Each glyph is a list of strokes; each stroke a list of (x, y) points.
FONT = {
    "A": [[(0, 10), (3.5, 0), (7, 10)], [(2, 6.5), (5, 6.5)]],
    "B": [[(0, 0), (0, 10)], [(0, 0), (4.5, 0), (6.5, 2), (4.5, 4), (0, 4)],
          [(0, 4), (4.5, 4), (6.5, 6), (5, 8), (4, 10), (0, 10)]],
    "C": [[(6, 1), (4, 0), (1.5, 0), (0, 2), (0, 8), (1.5, 10), (4, 10), (6, 9)]],
    "D": [[(0, 0), (0, 10)], [(0, 0), (4, 0), (6.5, 2.5), (6.5, 7.5), (4, 10), (0, 10)]],
    "E": [[(0, 0), (0, 10), (6.5, 10)], [(0, 0), (6, 0)], [(0, 5), (5, 5)]],
    "F": [[(0, 0), (0, 10)], [(0, 0), (6, 0)], [(0, 5), (5, 5)]],
    "G": [[(6, 1), (4, 0), (1.5, 0), (0, 2), (0, 8), (1.5, 10), (4, 10), (6, 9), (6, 5), (3.5, 5)]],
    "H": [[(0, 0), (0, 10)], [(7, 0), (7, 10)], [(0, 5), (7, 5)]],
    "I": [[(0, 0), (7, 0)], [(3.5, 0), (3.5, 10)], [(0, 10), (7, 10)]],
    "J": [[(1, 0), (6, 0)], [(4.5, 0), (4.5, 8), (3, 10), (1, 9)]],
    "K": [[(0, 0), (0, 10)], [(6, 0), (0, 5)], [(1.5, 4), (6, 10)]],
    "L": [[(0, 0), (0, 10), (6.5, 10)]],
    "M": [[(0, 10), (0, 0), (3.5, 6), (7, 0), (7, 10)]],
    "N": [[(0, 10), (0, 0), (7, 10), (7, 0)]],
    "O": [[(1.5, 0), (5, 0), (7, 2), (7, 8), (5, 10), (1.5, 10), (0, 8), (0, 2), (1.5, 0)]],
    "P": [[(0, 0), (0, 10)], [(0, 0), (4.5, 0), (6.5, 2), (4.5, 4.5), (0, 4.5)]],
    "Q": [[(1.5, 0), (5, 0), (7, 2), (7, 8), (5, 10), (1.5, 10), (0, 8), (0, 2), (1.5, 0)],
          [(4.5, 7), (7, 10)]],
    "R": [[(0, 0), (0, 10)], [(0, 0), (4.5, 0), (6.5, 2), (4.5, 4.5), (0, 4.5)],
          [(2, 4.5), (6.5, 10)]],
    "S": [[(6, 1), (4, 0), (2, 0.5), (0.5, 2), (1, 4), (3, 5), (5.5, 6), (6.5, 8), (5, 10), (3, 10), (1, 9)]],
    "T": [[(0, 0), (7, 0)], [(3.5, 0), (3.5, 10)]],
    "U": [[(0, 0), (0, 8), (1.5, 10), (5, 10), (7, 8), (7, 0)]],
    "V": [[(0, 0), (3.5, 10), (7, 0)]],
    "W": [[(0, 0), (1.5, 10), (3.5, 4), (5.5, 10), (7, 0)]],
    "X": [[(0, 0), (7, 10)], [(7, 0), (0, 10)]],
    "Y": [[(0, 0), (3.5, 5), (7, 0)], [(3.5, 5), (3.5, 10)]],
    "Z": [[(0, 0), (7, 0), (0, 10), (7, 10)]],
    "0": [[(1.5, 0), (5, 0), (7, 2), (7, 8), (5, 10), (1.5, 10), (0, 8), (0, 2), (1.5, 0)]],
    "1": [[(2, 2), (3.5, 0), (3.5, 10)], [(0, 10), (7, 10)]],
    "2": [[(0.5, 1.5), (2, 0), (5, 0), (6.5, 1.5), (6.5, 3.5), (0, 10), (7, 10)]],
    "3": [[(0.5, 0), (4.5, 0), (6.5, 1.5), (5, 3.5), (3, 4.5)],
          [(3, 4.5), (5.5, 5.5), (6.5, 7.5), (5, 10), (0.5, 10)]],
    "4": [[(5.5, 0), (5.5, 10)], [(0, 6.5), (6, 6.5)], [(5.5, 0), (0.5, 6.5)]],
    "5": [[(6, 0), (0, 0), (0, 4.5), (4, 4.5), (6, 6), (6, 8.5), (4, 10), (0, 10)]],
    "6": [[(5.5, 0.5), (3, 0), (1, 1.5), (0, 4), (0, 8), (1.5, 10), (4.5, 10), (6, 8), (6, 6), (4, 4.5), (1, 4.5)]],
    "7": [[(0, 0), (7, 0), (3, 10)]],
    "8": [[(2, 0), (5, 0), (6.5, 1.5), (5, 3), (2, 3), (0.5, 1.5), (2, 0)],
          [(2, 4), (5, 4), (6.5, 6), (6.5, 8.5), (5, 10), (2, 10), (0.5, 8.5), (0.5, 6), (2, 4)]],
    "9": [[(1, 9.5), (3, 10), (5, 8.5), (6, 6), (6, 2), (4.5, 0), (1.5, 0), (0, 2), (0, 4), (2, 5.5), (4.5, 5.5), (6, 4)]],
    " ": [],
    ".": [[(3, 9), (3, 9)]],
    ",": [[(3, 8.5), (3, 9.5), (2, 11)]],
    ":": [[(3, 2.5), (3, 2.5)], [(3, 8.5), (3, 8.5)]],
    ";": [[(3, 2.5), (3, 2.5)], [(3, 8.5), (3, 9.5), (2, 11)]],
    "!": [[(3.5, 0), (3.5, 7)], [(3.5, 9), (3.5, 9)]],
    "?": [[(1.5, 2), (3, 0), (5, 0), (6, 2), (6, 3.5), (3.5, 6), (3.5, 7.5)], [(3.5, 9), (3.5, 9)]],
    "-": [[(0.5, 5), (6.5, 5)]],
    "—": [[(0, 5), (7, 5)]],
    "/": [[(6.5, 10), (0.5, 0)]],
    "(": [[(4, 0), (2, 2.5), (2, 7.5), (4, 10)]],
    ")": [[(3, 0), (5, 2.5), (5, 7.5), (3, 10)]],
    "&": [[(5.5, 0), (3, 0.5), (1, 2.5), (1, 5), (2.5, 6.5), (6.5, 10)],
          [(1, 8), (2.5, 10), (5, 10), (6.5, 8), (5, 6.5), (2, 6.5)]],
    "%": [[(1, 0), (2, 0), (2, 2), (1, 2), (1, 0)],
          [(5, 8), (6, 8), (6, 10), (5, 10), (5, 8)], [(6.5, 10), (0.5, 0)]],
    "$": [[(5, 1), (3, 0), (1, 1), (1, 3), (3, 4.5), (5, 5.5), (6, 7.5), (5, 9.5), (3, 10), (1, 9)],
          [(3.5, -1), (3.5, 11)]],
    "+": [[(3.5, 2), (3.5, 8)], [(0.5, 5), (6.5, 5)]],
    "=": [[(0.5, 3.5), (6.5, 3.5)], [(0.5, 6.5), (6.5, 6.5)]],
    '"': [[(2, 0), (1.5, 2.5)], [(4.5, 0), (4, 2.5)]],
    "'": [[(4, 0), (3, 2)]],
    "•": [[(3.5, 4.5), (3.5, 4.5)]],
    "·": [[(3.5, 4.5), (3.5, 4.5)]],
}

ADVANCE = 8.0  # glyph cell width in font units


def text_width(text, scale):
    return len(text) * ADVANCE * scale


def draw_glyph(cv, ch, x, y, scale, color, thick):
    strokes = FONT.get(ch)
    if not strokes:
        return
    for stroke in strokes:
        for (ax, ay), (bx, by) in zip(stroke, stroke[1:]):
            cv.line(x + ax * scale, y + ay * scale,
                    x + bx * scale, y + by * scale, color, thick)
        if len(stroke) == 1:
            px, py = stroke[0]
            cv.disc(x + px * scale, y + py * scale, max(1, thick // 2), color)


def draw_text(cv, x, y, text, scale, color, thick=1, spacing=0.0):
    """Draw text at (x, y) = top-left of the cap line. Returns end x."""
    cx = float(x)
    for ch in text.upper():
        draw_glyph(cv, ch, cx, y, scale, color, thick)
        cx += ADVANCE * scale + spacing
    return cx


def draw_text_centered(cv, cx, y, text, scale, color, thick=1, spacing=0.0):
    w = text_width(text, scale) + spacing * max(0, len(text) - 1)
    draw_text(cv, cx - w / 2, y, text, scale, color, thick, spacing)


def wrap_lines(text, scale, max_w):
    """Greedy word wrap on the fixed-width stroke font."""
    words = text.upper().split(" ")
    lines = []
    cur = ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if text_width(trial, scale) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_block(cv, x, y, text, scale, color, max_w, leading, thick=1):
    """Draw a wrapped paragraph; returns the y just below the last line."""
    for line in wrap_lines(text, scale, max_w):
        draw_text(cv, x, y, line, scale, color, thick)
        y += leading
    return y


def png_bytes(cv):
    """Encode the canvas as a deterministic PNG (filter 0, zlib level 9)."""
    raw = bytearray()
    for yy in range(cv.h):
        raw.append(0)
        raw += cv.px[yy * cv.w * 3:(yy + 1) * cv.w * 3]

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        out += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return out

    ihdr = struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    return png


# --- the five stories -------------------------------------------------------
LEAD = {
    "kicker": "STRAIT OF HORMUZ  •  LEAD STORY",
    "headline": "THREE TANKERS HIT MINES IN HORMUZ",
    "deck": ("IRAN SAYS THE SHIPS CAUGHT FIRE UNDER US ESCORT. "
             "THE CLAIM IS UNVERIFIED. OIL NEARS A 3-MONTH LOW."),
}

STORIES = [
    {
        "kicker": "GAZA",
        "headline": "ISRAEL KILLS HAMAS SECURITY CHIEF",
        "deck": ("NAEEM ABU NAHEL, 50, DIES IN A GAZA CITY STRIKE. "
                 "SEVEN KILLED ACROSS THE STRIP ON TUESDAY."),
        "art": "city",
    },
    {
        "kicker": "UKRAINE",
        "headline": "RUSSIAN STRIKE KILLS 2 IN ZAPORIZHZHIA",
        "deck": ("40 WOUNDED, FOUR OF THEM CHILDREN. HOMES AND A "
                 "FIVE-STOREY BLOCK HIT OVERNIGHT."),
        "art": "block",
    },
    {
        "kicker": "BUSINESS",
        "headline": "SANOFI BUYS INSMED FOR $41BN",
        "deck": ("$175 A SHARE IN CASH, ITS BIGGEST DEAL IN 20 YEARS. "
                 "TWO LUNG DRUGS LEAD THE PRIZE."),
        "art": "pill",
    },
    {
        "kicker": "NEPAL",
        "headline": "QUAKE SHAKES NEPAL NEAR TIBET",
        "deck": ("MAGNITUDE 5.6 AT 7:17 AM IN TAPLEJUNG. FELT IN "
                 "KATHMANDU. NO CASUALTIES REPORTED."),
        "art": "quake",
    },
]


# --- picture panels: flat shapes, no text inside ----------------------------
def starburst(cv, cx, cy, r_out, r_in, points, c):
    import math
    pts = []
    for i in range(points * 2):
        ang = -math.pi / 2 + i * math.pi / points
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    cv.poly(pts, c)


def art_tanker(cv, x, y, w, h):
    cv.rect(x, y, w, h, SKY)
    cv.disc(x + w - 52, y + 34, 22, GOLD)          # low sun
    cv.rect(x, y + int(h * 0.62), w, h - int(h * 0.62), SEA)
    cv.line(x, y + int(h * 0.62), x + w, y + int(h * 0.62), PAPER, 2)
    # dashed shipping lane
    for i in range(6):
        cv.rect(x + 14 + i * 52, y + int(h * 0.74), 30, 3, PAPER)
    # tanker hull with slanted bow
    hx, hy = x + 30, y + int(h * 0.66)
    cv.poly([(hx, hy), (hx + 210, hy), (hx + 240, hy + 26), (hx + 210, hy + 34),
             (hx, hy + 34)], INK)
    cv.rect(hx + 30, hy - 30, 62, 30, PAPER)       # superstructure
    cv.rect(hx + 100, hy - 46, 26, 46, RED)        # funnel
    for i in range(4):
        cv.rect(hx + 38 + i * 14, hy - 22, 8, 8, INK)
    # mine with spikes
    mx, my = x + w - 66, y + int(h * 0.8)
    for a in range(8):
        import math
        ang = a * math.pi / 4
        cv.line(mx, my, mx + 20 * math.cos(ang), my + 20 * math.sin(ang), INK, 3)
    cv.disc(mx, my, 11, INK)
    # explosion above the hull, clear of the funnel
    starburst(cv, hx + 175, hy - 58, 46, 20, 9, ORANGE)
    starburst(cv, hx + 175, hy - 58, 28, 12, 9, GOLD)
    starburst(cv, hx + 175, hy - 58, 13, 6, 9, PAPER)


def art_city(cv, x, y, w, h):
    cv.rect(x, y, w, h, (240, 217, 181))
    cv.disc(x + w - 40, y + 26, 18, GOLD)
    base = y + h
    towers = [(0, 0.55), (0.22, 0.78), (0.45, 0.45), (0.66, 0.68), (0.86, 0.5)]
    for fx, fh in towers:
        tw = int(w * 0.16)
        tx = x + int(w * fx)
        th = int(h * fh)
        cv.rect(tx, base - th, tw, th, INK)
        for wy in range(3):
            wyy = base - th + 8 + wy * 14
            if wyy + 7 > base - 3:
                break
            for wx in range(2):
                cv.rect(tx + 6 + wx * 12, wyy, 6, 7, PAPER)
    # smoke plume over the middle tower, sized to the panel
    for i in range(4):
        r = int(h * (0.22 + 0.08 * i))
        cv.disc(x + int(w * 0.53) + i * 3, y + int(h * 0.15) + i * int(h * 0.16), r, GREY)
    starburst(cv, x + int(w * 0.53), y + int(h * 0.2), int(h * 0.32), int(h * 0.14), 8, RED)


def art_block(cv, x, y, w, h):
    cv.rect(x, y, w, h, LIGHT)
    bx, by = x + int(w * 0.18), y + int(h * 0.14)
    bw, bh = int(w * 0.5), int(h * 0.72)
    cv.rect(bx, by, bw, bh, (150, 148, 140))
    for row in range(4):
        for col in range(3):
            cv.rect(bx + 12 + col * 34, by + 12 + row * 26, 18, 14, PAPER)
    # broken corner and rubble
    cv.poly([(bx + bw, by), (bx + bw, by + 40), (bx + bw - 46, by)], INK)
    cv.poly([(bx - 8, by + bh), (bx + 60, by + bh), (bx + 26, by + bh - 26)], GREY)
    cv.poly([(bx + 70, by + bh), (bx + 150, by + bh), (bx + 108, by + bh - 18)], INK)
    # smoke
    for i, r in enumerate((10, 14, 18)):
        cv.disc(bx + bw - 10 + i * 5, by + 4 + i * 10, r, GREY)
    draw_text(cv, x + int(w * 0.74), y + int(h * 0.16), "2 DEAD", 1.5, RED, 3)
    draw_text(cv, x + int(w * 0.74), y + int(h * 0.16) + 20, "40 HURT", 1.5, INK, 3)


def art_pill(cv, x, y, w, h):
    cv.rect(x, y, w, h, (214, 232, 222))
    cx, cy = x + int(w * 0.5), y + int(h * 0.5)
    half = max(10, int(h * 0.36))  # capsule half-height, fits the panel
    cap = min(110, int(w * 0.24))
    cv.rect(cx - cap, cy - half, cap, 2 * half, RED)
    cv.rect(cx, cy - half, cap, 2 * half, PAPER)
    cv.disc(cx - cap, cy, half, RED)
    cv.disc(cx + cap, cy, half, PAPER)
    cv.outline_rect(cx - cap - half, cy - half, 2 * cap + 2 * half, 2 * half, INK, 3)
    cv.line(cx, cy - half, cx, cy + half, INK, 3)
    # coins tucked at the panel's lower corners, fully inside the frame
    for dx in (-int(w * 0.32), int(w * 0.32)):
        cv.disc(cx + dx, cy + int(h * 0.22), 11, GOLD)
        draw_text(cv, cx + dx - 4, cy + int(h * 0.22) - 8, "$", 1.2, INK, 2)


def art_quake(cv, x, y, w, h):
    cv.rect(x, y, w, h, SKY)
    base = y + h
    cv.poly([(x, base), (x + int(w * 0.34), y + int(h * 0.18)), (x + int(w * 0.62), base)], (90, 107, 122))
    cv.poly([(x + int(w * 0.34), y + int(h * 0.18)), (x + int(w * 0.26), y + int(h * 0.36)),
             (x + int(w * 0.42), y + int(h * 0.36))], PAPER)
    cv.poly([(x + int(w * 0.3), base), (x + int(w * 0.72), y + int(h * 0.08)), (x + w, base)], (70, 88, 104))
    cv.poly([(x + int(w * 0.72), y + int(h * 0.08)), (x + int(w * 0.62), y + int(h * 0.3)),
             (x + int(w * 0.82), y + int(h * 0.3))], PAPER)
    # seismograph zigzag, amplitude scaled to the panel height
    pts = []
    px = x + 12
    py = base - int(h * 0.4)
    amp = min(1.0, h / 90.0)
    zig = [0, -26, 14, -40, 8, 22, -18, 30, -8, 0]
    for d in zig:
        pts.append((px, py + d * amp))
        px += 26
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        cv.line(ax, ay, bx, by, RED, 4)
    cv.line(x + 12, base - 34, x + 12, base - 34, RED, 4)


ART = {"tanker": art_tanker, "city": art_city, "block": art_block,
       "pill": art_pill, "quake": art_quake}


# --- page layout ------------------------------------------------------------
M = 30  # margin


def rule(cv, y, thick=3, color=INK):
    cv.rect(M, y, W - 2 * M, thick, color)


def draw_masthead(cv):
    draw_text_centered(cv, W // 2, 30, "THE DAILY GLOBE", 6.0, INK, 5, spacing=6.0)
    draw_text_centered(cv, W // 2, 108, "TUESDAY, 24 NOVEMBER 2026", 1.7, INK, 2, spacing=2.0)
    draw_text_centered(cv, W // 2, 132, "FIVE STORIES  •  FIRST REPORTED TODAY  •  ONE DAY IN THE WORLD",
                       1.35, RED, 2, spacing=1.0)
    rule(cv, 158, 3)
    rule(cv, 164, 1)


def draw_lead(cv):
    y = 182
    draw_text(cv, M, y, LEAD["kicker"], 1.7, RED, 2, spacing=1.0)
    y += 30
    draw_block(cv, M, y, LEAD["headline"], 3.0, INK, W - 2 * M, 36, thick=4)
    y += 78
    # deck on the left, picture on the right
    deck_w = 560
    draw_block(cv, M, y, LEAD["deck"], 1.6, INK, deck_w, 26, thick=2)
    px, py, pw, ph = 620, y - 6, W - M - 620, 168
    cv.outline_rect(px, py, pw, ph, INK, 3)
    cv.clip_to(px + 3, py + 3, pw - 6, ph - 6)
    ART["tanker"](cv, px + 3, py + 3, pw - 6, ph - 6)
    cv.clip_clear()
    draw_text(cv, M, y + 108, "OIL: BRENT $88.97, NEAR A 3-MONTH LOW AS HORMUZ",
              1.45, INK, 2)
    draw_text(cv, M, y + 134, "SHIPPING RISK PERSISTS.  •  SOURCES: REUTERS, IRNA",
              1.45, INK, 2)


def draw_story(cv, x, y, w, story):
    draw_text(cv, x, y, story["kicker"], 1.6, RED, 2, spacing=1.0)
    y += 28
    y = draw_block(cv, x, y, story["headline"], 2.1, INK, w, 26, thick=3)
    y += 6
    y = draw_block(cv, x, y, story["deck"], 1.45, INK, w, 22, thick=2)
    y += 10
    art_h = 60
    cv.outline_rect(x, y, w, art_h, INK, 3)
    cv.clip_to(x + 3, y + 3, w - 6, art_h - 6)
    ART[story["art"]](cv, x + 3, y + 3, w - 6, art_h - 6)
    cv.clip_clear()
    return y + art_h


def draw_page():
    cv = Canvas(W, H, PAPER)
    cv.outline_rect(8, 8, W - 16, H - 16, INK, 4)
    draw_masthead(cv)
    draw_lead(cv)
    rule(cv, 452, 2)
    # row 2: Gaza | Ukraine
    col_w = (W - 2 * M - 26) // 2
    draw_story(cv, M, 468, col_w, STORIES[0])
    draw_story(cv, M + col_w + 26, 468, col_w, STORIES[1])
    rule(cv, 700, 2)
    # row 3: Business | Nepal
    draw_story(cv, M, 716, col_w, STORIES[2])
    draw_story(cv, M + col_w + 26, 716, col_w, STORIES[3])
    rule(cv, 926, 2)
    draw_text_centered(cv, W // 2, 942,
                       "EVERY STORY FIRST REPORTED TUESDAY 24 NOVEMBER 2026",
                       1.4, INK, 2, spacing=1.0)
    draw_text_centered(cv, W // 2, 968, "THE DAILY GLOBE  •  ONE PAGE, ONE DAY",
                       1.2, GREY, 2, spacing=1.0)
    return cv


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    data = png_bytes(draw_page())
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as f:
        f.write(data)
    print(f"wrote {path} ({len(data)} bytes)")


if __name__ == "__main__":
    sys.exit(main())

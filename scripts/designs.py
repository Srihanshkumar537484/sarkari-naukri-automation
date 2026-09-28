"""
designs.py - Post (1080x1350) aur Reel (1080x1920, animated) banane ka engine.

30 templates = 6 layouts x 5 color palettes. Har naye asset ke liye agla
template use hota hai (rotation), isliye posts/reels lagatar alag dikhte hain.

Sirf Pillow + ffmpeg use hota hai (dono GitHub Actions pe free hain).
"""

import glob
import math
import os
import re
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, features

W = 1080
POST_H = 1350
REEL_H = 1920
FPS = 24

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.normpath(os.path.join(HERE, "..", "fonts"))


# ----------------------------------------------------------------- fonts
def _pick(*paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_DEJAVU_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

_NOTO = "/usr/share/fonts/truetype/noto"

LATIN = {
    "bold": _pick(os.path.join(FONT_DIR, "Poppins-Bold.ttf"), os.path.join(_NOTO, "NotoSans-Bold.ttf"), _DEJAVU_B),
    "medium": _pick(os.path.join(FONT_DIR, "Poppins-Medium.ttf"), os.path.join(_NOTO, "NotoSans-Medium.ttf"), _DEJAVU),
    "regular": _pick(os.path.join(FONT_DIR, "Poppins-Regular.ttf"), os.path.join(_NOTO, "NotoSans-Regular.ttf"), _DEJAVU),
}


def _deva(weight):
    dirs = [
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/opentype/noto",
        "/usr/share/fonts/noto",
        "/usr/share/fonts/truetype/google-fonts",
    ]
    for d in dirs:
        hits = sorted(glob.glob(os.path.join(d, f"NotoSansDevanagari-{weight}.ttf")))
        if hits:
            return hits[0]
    return None


DEVA = {"bold": _deva("Bold"), "medium": _deva("Medium"), "regular": _deva("Regular")}
DEVA["medium"] = DEVA["medium"] or DEVA["bold"]
# Hindi tabhi image mein daalenge jab shaping (raqm) + font dono maujood hon
HINDI_OK = bool(features.check("raqm") and DEVA["bold"] and DEVA["regular"])

_font_cache = {}
_RS = 1.0   # rows ka size (jagah kam ho to chhota)
_FS = 1.0   # reel mein text bada rakhne ke liye (build_scene set karta hai)


def has_deva(s):
    return any("\u0900" <= c <= "\u097f" for c in s)


def font(weight, size, text=""):
    path = DEVA[weight] if (HINDI_OK and has_deva(text)) else LATIN[weight]
    size = int(size * _FS)
    key = (path, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(path, size)
    return _font_cache[key]


def fs(size):
    return int(size * _FS)


def clean_text(s, allow_hindi=None):
    """Emoji/symbols hata deta hai (font mein nahi hote, box ban jaate hain)."""
    if allow_hindi is None:
        allow_hindi = HINDI_OK
    out = []
    for c in s:
        o = ord(c)
        if 0x0900 <= o <= 0x097F:
            if allow_hindi:
                out.append(c)
        elif 0x20 <= o < 0x2000 or o in (0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x20B9):
            out.append(c)
        elif c in "\n\t":
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


_dummy = ImageDraw.Draw(Image.new("L", (1, 1)))


def tw(text, f):
    return _dummy.textlength(text, font=f)


def wrap(text, f, max_w, max_lines=None):
    words = text.split()
    lines, cur = [], ""
    for wd in words:
        t = f"{cur} {wd}".strip()
        if tw(t, f) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and tw(last + "...", f) > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip() + "..."
    return lines


def fit_title(text, max_w, max_h, max_lines=5, ratio=1.22, sizes=(94, 86, 78, 70, 62, 56, 50, 45, 40)):
    for s in sizes:
        f = font("bold", s, text)
        es = f.size
        lines = wrap(text, f, max_w)
        if len(lines) <= max_lines and len(lines) * es * ratio <= max_h:
            return f, lines, es
    f = font("bold", sizes[-1], text)
    es = f.size
    n = max(1, int(max_h // (es * ratio)))
    return f, wrap(text, f, max_w, max_lines=min(n, max_lines)), es


# ------------------------------------------------------------- graphics
def rr_mask(w, h, r, scale=3):
    m = Image.new("L", (w * scale, h * scale), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * scale - 1, h * scale - 1], radius=r * scale, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def box(w, h, r, fill=None, outline=None, ow=0):
    """Rounded rectangle sprite (RGBA). fill/outline = (r,g,b[,a])."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    m = rr_mask(w, h, r)
    if fill is not None:
        a = fill[3] if len(fill) > 3 else 255
        layer = Image.new("RGBA", (w, h), tuple(fill[:3]) + (0,))
        layer.putalpha(m.point(lambda v: int(v * a / 255)))
        img.alpha_composite(layer)
    if outline is not None and ow > 0:
        inner = Image.new("L", (w, h), 0)
        im = rr_mask(max(1, w - 2 * ow), max(1, h - 2 * ow), max(1, r - ow))
        inner.paste(im, (ow, ow))
        ring = ImageChops.subtract(m, inner)
        a = outline[3] if len(outline) > 3 else 255
        layer = Image.new("RGBA", (w, h), tuple(outline[:3]) + (0,))
        layer.putalpha(ring.point(lambda v: int(v * a / 255)))
        img.alpha_composite(layer)
    return img


def gradient(w, h, c1, c2, mode="v"):
    g = Image.linear_gradient("L")
    v = g.resize((w, h))
    if mode == "v":
        mask = v
    elif mode == "h":
        mask = g.rotate(90).resize((w, h))
    else:
        mask = ImageChops.add(v, g.rotate(90).resize((w, h)), scale=2)
    return Image.composite(Image.new("RGB", (w, h), tuple(c2)), Image.new("RGB", (w, h), tuple(c1)), mask)


def aa_layer(size, fn, scale=2):
    big = Image.new("RGBA", (size[0] * scale, size[1] * scale), (0, 0, 0, 0))
    fn(ImageDraw.Draw(big), scale)
    return big.resize(size, Image.LANCZOS)


def circles(size, specs):
    def fn(d, s):
        for cx, cy, r, col in specs:
            d.ellipse([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s], fill=col)
    return aa_layer(size, fn)


def dots(size, gap, r, col):
    def fn(d, s):
        for y in range(gap // 2, size[1], gap):
            for x in range(gap // 2, size[0], gap):
                d.ellipse([(x - r) * s, (y - r) * s, (x + r) * s, (y + r) * s], fill=col)
    return aa_layer(size, fn)


def stripes(size, gap, wid, col, slant=1.0):
    def fn(d, s):
        w, h = size
        x = -h * slant
        while x < w + h:
            d.polygon([(x * s, 0), ((x + wid) * s, 0), ((x + wid + h * slant) * s, h * s), ((x + h * slant) * s, h * s)], fill=col)
            x += gap
    return aa_layer(size, fn)


def text_sprite(lines, f, fill, line_h, pad=6, align="left", width=None, glow=None):
    if isinstance(lines, str):
        lines = [lines]
    wmax = int(max(tw(l, f) for l in lines)) if lines else 1
    bw = int(width or wmax) + 2 * pad
    bh = int(line_h * len(lines)) + 2 * pad
    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        lw = tw(l, f)
        x = pad if align == "left" else (bw - lw) / 2 if align == "center" else bw - pad - lw
        d.text((x, pad + i * line_h), l, font=f, fill=fill)
    if glow:
        g = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        for i, l in enumerate(lines):
            lw = tw(l, f)
            x = pad if align == "left" else (bw - lw) / 2 if align == "center" else bw - pad - lw
            gd.text((x, pad + i * line_h), l, font=f, fill=glow)
        g = g.filter(ImageFilter.GaussianBlur(14))
        g.alpha_composite(img)
        img = g
    return img


def with_shadow(sprite, blur=16, dy=10, alpha=80):
    pad = blur * 2
    w, h = sprite.size
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", sprite.size, (0, 0, 0, 0))
    sh.putalpha(sprite.getchannel("A").point(lambda v: int(v * alpha / 255)))
    out.alpha_composite(sh, (pad, pad + dy))
    out = out.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(sprite, (pad, pad))
    return out, pad


# -------------------------------------------------------------- palettes
class Pal:
    def __init__(self, bg1, bg2, accent, accent2, ink):
        self.bg1, self.bg2, self.accent, self.accent2, self.ink = bg1, bg2, accent, accent2, ink


PALETTES = [
    Pal((14, 27, 66), (33, 62, 140), (255, 193, 7), (64, 196, 255), (14, 27, 66)),      # navy + gold
    Pal((4, 64, 48), (14, 120, 88), (255, 214, 0), (140, 240, 180), (4, 50, 38)),        # emerald
    Pal((110, 12, 30), (184, 28, 60), (255, 210, 60), (255, 150, 170), (90, 10, 25)),    # crimson
    Pal((46, 16, 96), (112, 48, 186), (255, 94, 170), (255, 214, 0), (46, 16, 96)),      # violet
    Pal((6, 52, 72), (10, 112, 132), (255, 140, 40), (120, 230, 230), (6, 52, 72)),      # ocean
]


# ----------------------------------------------------------------- scene
class Scene:
    def __init__(self, mode):
        self.mode = mode
        self.w = W
        self.h = REEL_H if mode == "reel" else POST_H
        self.vs = self.h / POST_H
        self.top = 230 if mode == "reel" else 70          # reels: upar IG UI ke liye jagah
        self.bottom = self.h - (370 if mode == "reel" else 70)
        self.bg = None
        self.els = []
        self.tscale = 1.0   # title ko chhota karne ka factor (rows fit karne ke liye)
        self.dropped = 0    # kitni rows jagah ki kami se hat gayi

    def add(self, sprite, x, y, kind, idx=0):
        self.els.append({"img": sprite, "x": int(x), "y": int(y), "kind": kind, "idx": idx})


def _rows_sprites(rows, width, avail_h, gap, builder, sc=None):
    """Rows ke sprites banata hai; jagah kam ho to (highlight ko bacha ke) baaki rows hata deta hai."""
    items = [(builder(lbl, val, hi, width), hi) for (lbl, val, hi) in rows]
    total = lambda its: sum(i[0].size[1] for i in its) + gap * max(0, len(its) - 1)
    dropped = 0
    while items and total(items) > avail_h:
        idx = next((i for i in range(len(items) - 1, -1, -1) if not items[i][1]), len(items) - 1)
        items.pop(idx)
        dropped += 1
    if sc is not None:
        sc.dropped = dropped
    return [i[0] for i in items]


def _row(label, value, width, *, fill, label_col, value_col, bar=None, outline=None, ow=0, radius=24,
         lsize=28, vsize=44, align="left", glow=None):
    label = label.upper()
    fv = font("bold", vsize * _RS, value)
    fl = font("medium", lsize * _RS, label)
    padx = 34
    inner_w = width - 2 * padx - (18 if bar else 0)
    vlines = wrap(value, fv, inner_w, max_lines=2)
    lsize, vsize = fl.size, fv.size
    vline_h = vsize * 1.3
    h = int(22 + lsize * 1.45 + len(vlines) * vline_h + 20)
    img = box(width, h, radius, fill=fill, outline=outline, ow=ow)
    if bar:
        bar_img = box(12, h - 36, 6, fill=bar)
        img.alpha_composite(bar_img, (22, 18))
    x0 = padx + (18 if bar else 0)
    ls = text_sprite(label, fl, label_col, lsize * 1.45, pad=0)
    vs_ = text_sprite(vlines, fv, value_col, vline_h, pad=0, align=align, width=inner_w)
    if align == "center":
        img.alpha_composite(ls, (int((width - ls.size[0]) / 2), 18))
        img.alpha_composite(vs_, (int((width - vs_.size[0]) / 2), int(20 + lsize * 1.45)))
    else:
        img.alpha_composite(ls, (x0, 18))
        img.alpha_composite(vs_, (x0, int(20 + lsize * 1.45)))
    if glow:
        g = box(width, h, radius, outline=glow, ow=4).filter(ImageFilter.GaussianBlur(10))
        g.alpha_composite(img)
        img = g
    return img


def _chip(text, f, fg, bg, padx=34, pady=14, outline=None, ow=0):
    lw = int(tw(text, f)) + 2 * padx
    lh = int(f.size * 1.3) + 2 * pady
    img = box(lw, lh, lh // 2, fill=bg, outline=outline, ow=ow)
    t = text_sprite(text, f, fg, f.size * 1.3, pad=0)
    img.alpha_composite(t, (padx, pady))
    return img


def _footer(sc, text, f, col, y, align="center", x=None, kind="footer", box_h=None):
    parts = [p.strip() for p in text.split("|") if p.strip()]
    lines = [" | ".join(parts)] if parts else [text]
    limit = sc.w - 110 if align == "center" else sc.w - (x or 72) - 50
    if len(parts) > 1 and tw(lines[0], f) > limit:
        lines = parts
    lh = f.size * 1.4
    wmax = int(max(tw(l, f) for l in lines))
    sp = text_sprite(lines, f, col, lh, pad=0, align="center" if align == "center" else "left", width=wmax)
    if box_h is not None:
        y = y + (box_h - sp.size[1]) / 2
    elif len(lines) > 1:
        y = y - (len(lines) - 1) * lh          # neeche ka edge wahi rahe
    if align == "center":
        x = (sc.w - sp.size[0]) / 2
    sc.add(sp, x if x is not None else 72, y, kind)


def _title_to_scene(sc, lines, f, size, fill, x, y, align="left", ratio=1.22, glow=None, width=None, hl=None):
    for i, l in enumerate(lines):
        sp = text_sprite(l, f, fill, size * ratio, pad=4, align=align, width=width, glow=glow)
        if hl:
            lw = int(tw(l, f)) + 24
            bar = box(lw, int(size * 0.42), 8, fill=hl)
            base = Image.new("RGBA", (max(sp.size[0], lw + 8), sp.size[1]), (0, 0, 0, 0))
            base.alpha_composite(bar, (0, int(size * 0.72)))
            base.alpha_composite(sp)
            sp = base
        xx = x if align == "left" else (sc.w - sp.size[0]) / 2
        sc.add(sp, xx, y + i * size * ratio, "title", i)
    return y + len(lines) * size * ratio


# --------------------------------------------------------------- layouts
def layout_banner(sc, P, data):
    w, h, vs = sc.w, sc.h, sc.vs
    bg = gradient(w, h, P.bg1, P.bg2, "v").convert("RGBA")
    bg.alpha_composite(circles((w, h), [(w * 0.92, h * 0.62, 380, P.accent2 + (34,)), (-40, h * 0.92, 280, P.accent + (28,))]))
    band_h = int((150 if sc.mode == "post" else 150) * _FS)
    band_y = 0 if sc.mode == "post" else 210
    bd = ImageDraw.Draw(bg)
    bd.rectangle([0, band_y, w, band_y + band_h], fill=P.accent)
    for i in range(3):   # slanted stripes
        x = w - 250 + i * 54
        bd.polygon([(x, band_y), (x + 28, band_y), (x - 22, band_y + band_h), (x - 50, band_y + band_h)], fill=P.ink)
    fb = 0 if sc.mode == "post" else 290
    foot_h = 118
    foot_y = h - fb - foot_h
    bd.rectangle([0, foot_y, w, foot_y + foot_h], fill=tuple(int(c * 0.55) for c in P.bg1))
    sc.bg = bg.convert("RGB")

    chip_f = font("bold", 54, data["chip"])
    cs = text_sprite(data["chip"], chip_f, P.ink, chip_f.size * 1.3, pad=0)
    sc.add(cs, 72, band_y + (band_h - chip_f.size * 1.3) / 2, "chip")

    top = band_y + band_h + int(70 * vs)
    bottom = foot_y - 40
    f, lines, size = fit_title(data["title"], w - 144, (bottom - top) * 0.46 * sc.tscale)
    y = _title_to_scene(sc, lines, f, size, (255, 255, 255), 72, top)
    sc.add(box(170, 12, 6, fill=P.accent), 72, y + 18, "title", len(lines))
    y += 62

    gap = int(20 * vs)
    def builder(lbl, val, hi, width):
        if hi:
            return _row(lbl, val, width, fill=P.accent + (255,), label_col=P.ink, value_col=P.ink)
        return _row(lbl, val, width, fill=(255, 255, 255, 30), label_col=(205, 218, 245), value_col=(255, 255, 255), bar=P.accent)
    for i, sp in enumerate(_rows_sprites(data["rows"], w - 144, bottom - y, gap, builder, sc)):
        sc.add(sp, 72, y, "row", i)
        y += sp.size[1] + gap
    _footer(sc, f'{data["handle"]} | {data["tg"]}', font("medium", 27, ""), (255, 255, 255), foot_y, box_h=foot_h)


def layout_card(sc, P, data):
    w, h, vs = sc.w, sc.h, sc.vs
    bg = gradient(w, h, P.bg1, P.bg2, "d").convert("RGBA")
    bg.alpha_composite(circles((w, h), [(120, 160, 210, P.accent + (60,)), (w - 60, h * 0.45, 260, P.accent2 + (44,)),
                                        (w * 0.3, h - 120, 320, (255, 255, 255, 20))]))
    sc.bg = bg.convert("RGB")
    cw = w - 120
    inner = cw - 90
    f, lines, size = fit_title(data["title"], inner, (sc.bottom - sc.top) * 0.36 * sc.tscale, ratio=1.22)
    title_h = len(lines) * size * 1.22
    gap = int(16 * vs)
    def builder(lbl, val, hi, width):
        if hi:
            return _row(lbl, val, width, fill=P.accent + (255,), label_col=P.ink, value_col=P.ink, radius=20, lsize=26, vsize=42)
        return _row(lbl, val, width, fill=(P.bg1[0], P.bg1[1], P.bg1[2], 14), label_col=(90, 96, 120), value_col=P.ink,
                    bar=P.bg2, radius=20, lsize=26, vsize=42)
    avail = (sc.bottom - sc.top) - 110 - title_h - 150
    rows = _rows_sprites(data["rows"], inner, avail, gap, builder, sc)
    rows_h = sum(r.size[1] for r in rows) + gap * max(0, len(rows) - 1)
    card_h = int(70 + title_h + 40 + rows_h + 60)
    stack = card_h + 40 + 60
    y0 = sc.top + max(0, ((sc.bottom - sc.top) - stack) / 2) + 40
    card = box(cw, card_h, 46, fill=(255, 255, 255, 255))
    card, pad = with_shadow(card, blur=22, dy=14, alpha=110)
    sc.add(card, 60 - pad, y0 - pad, "deco")
    chip = _chip(data["chip"], font("bold", 34, data["chip"]), P.ink, P.accent)
    sc.add(chip, 90, y0 - chip.size[1] / 2 - 6, "chip")
    y = _title_to_scene(sc, lines, f, size, P.ink, 60 + 45, y0 + 60, hl=None)
    y += 26
    for i, sp in enumerate(rows):
        sc.add(sp, 60 + 45, y, "row", i)
        y += sp.size[1] + gap
    _footer(sc, f'{data["handle"]}  |  {data["tg"]}', font("medium", 27, ""), (255, 255, 255), y0 + card_h + 34)


def layout_poster(sc, P, data):
    w, h, vs = sc.w, sc.h, sc.vs
    bg = Image.new("RGBA", (w, h), P.bg1 + (255,))
    bg.alpha_composite(gradient(w, h, P.bg1, P.bg2, "v").convert("RGBA"))
    bg.alpha_composite(stripes((w, h), 130, 50, (255, 255, 255, 14), slant=0.5))
    bg.alpha_composite(circles((w, h), [(w / 2, h * 0.34, 430, P.accent + (34,)), (w / 2, h * 0.34, 330, P.accent + (30,))]))
    sc.bg = bg.convert("RGB")
    top, bottom = sc.top, sc.bottom
    chip = _chip(data["chip"], font("bold", 38, data["chip"]), P.ink, P.accent, padx=42, pady=16)
    sc.add(chip, (w - chip.size[0]) / 2, top + 20, "chip")
    tag = text_sprite("SARKARI NAUKRI ONE OVER", font("medium", 26, ""), P.accent2, 36, pad=0, align="center")
    sc.add(tag, (w - tag.size[0]) / 2, top + 20 + chip.size[1] + 22, "deco")
    ty = top + 20 + chip.size[1] + 100
    f, lines, size = fit_title(data["title"].upper() if not has_deva(data["title"]) else data["title"], w - 160,
                               (bottom - ty) * 0.42 * sc.tscale, max_lines=5, ratio=1.2)
    y = _title_to_scene(sc, lines, f, size, (255, 255, 255), 0, ty, align="center", ratio=1.2)
    sc.add(box(220, 8, 4, fill=P.accent), (w - 220) / 2, y + 22, "title", len(lines))
    sc.add(box(90, 8, 4, fill=P.accent2), (w - 90) / 2, y + 40, "title", len(lines))
    y += 90
    gap = int(18 * vs)
    def builder(lbl, val, hi, width):
        if hi:
            return _row(lbl, val, width, fill=P.accent + (255,), label_col=P.ink, value_col=P.ink, align="center", radius=30)
        return _row(lbl, val, width, fill=(255, 255, 255, 16), label_col=P.accent, value_col=(255, 255, 255),
                    outline=(255, 255, 255, 150), ow=3, align="center", radius=30)
    for i, sp in enumerate(_rows_sprites(data["rows"], w - 200, bottom - y - 110, gap, builder, sc)):
        sc.add(sp, 100, y, "row", i)
        y += sp.size[1] + gap
    _footer(sc, data["handle"], font("bold", 34, ""), P.accent, bottom - 70)
    _footer(sc, data["tg"], font("medium", 26, ""), (255, 255, 255), bottom - 24)


def layout_split(sc, P, data):
    w, h, vs = sc.w, sc.h, sc.vs
    light = (244, 246, 251)
    bg = Image.new("RGBA", (w, h), light + (255,))
    split = int(h * (0.44 if sc.mode == "post" else 0.40))
    top_img = gradient(w, h, P.bg1, P.bg2, "d")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([(0, 0), (w, 0), (w, split - 90), (0, split + 90)], fill=255)
    bg.paste(top_img, (0, 0), mask)
    bg.alpha_composite(circles((w

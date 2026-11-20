# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure-Python font header reader (no external deps).

Reads only the tables needed: name / OS/2 / post / cmap.
Supports .ttf / .otf / .ttc (first face, same as Blender).
"""

import os
import struct

# ---------------------------------------------------------------- low level


def _u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def _i16(b, o):
    return struct.unpack_from(">h", b, o)[0]


def _u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def _read_tables(f):
    """Return {tag: (offset, length)} for the first face."""
    f.seek(0)
    head = f.read(12)
    if len(head) < 12:
        raise ValueError("too small")
    base = 0
    if head[:4] == b"ttcf":
        f.seek(12)
        base = struct.unpack(">I", f.read(4))[0]
        f.seek(base)
        head = f.read(12)
    num = _u16(head, 4)
    if num == 0 or num > 200:
        raise ValueError("bad table count")
    f.seek(base + 12)
    raw = f.read(16 * num)
    tables = {}
    for i in range(num):
        tag = raw[i * 16:i * 16 + 4].decode("latin-1")
        off = _u32(raw, i * 16 + 8)
        ln = _u32(raw, i * 16 + 12)
        tables[tag] = (off, ln)
    return tables


def _read(f, tables, tag, maxlen=None):
    if tag not in tables:
        return None
    off, ln = tables[tag]
    if maxlen is not None:
        ln = min(ln, maxlen)
    f.seek(off)
    return f.read(ln)


# ---------------------------------------------------------------- name table

def _decode_name(raw, pid):
    try:
        if pid in (0, 3):
            return raw.decode("utf-16-be")
        return raw.decode("mac_roman")
    except Exception:
        return ""


def _parse_names(b):
    """Return dict {(nameID, lang): string} picking Windows/Unicode records."""
    out = {}
    if not b or len(b) < 6:
        return out
    count = _u16(b, 2)
    str_off = _u16(b, 4)
    for i in range(count):
        r = 6 + i * 12
        if r + 12 > len(b):
            break
        pid, eid, lid, nid, ln, off = struct.unpack_from(">HHHHHH", b, r)
        if nid not in (1, 2, 4, 16, 17):
            continue
        s = b[str_off + off:str_off + off + ln]
        if pid == 3:
            lang = "ja" if lid == 0x0411 else ("en" if lid == 0x0409 else None)
        elif pid == 1 and lid == 0:
            lang = "mac"
        else:
            lang = None
        if lang is None:
            continue
        txt = _decode_name(s, pid).strip("\x00 ")
        if txt and (nid, lang) not in out:
            out[(nid, lang)] = txt
    return out


# ---------------------------------------------------------------- cmap

def _parse_cmap(b):
    """Return a callable cp -> bool, or None."""
    if not b or len(b) < 4:
        return None
    n = _u16(b, 2)
    subs = {}
    for i in range(n):
        pid, eid, off = struct.unpack_from(">HHI", b, 4 + i * 8)
        subs[(pid, eid)] = off
    order = [(3, 10), (0, 6), (0, 4), (3, 1), (0, 3), (0, 1), (0, 0), (3, 0)]
    for key in order:
        if key not in subs:
            continue
        off = subs[key]
        fmt = _u16(b, off)
        if fmt == 12:
            ngroups = _u32(b, off + 12)
            groups = []
            p = off + 16
            for _ in range(ngroups):
                s, e, _g = struct.unpack_from(">III", b, p)
                groups.append((s, e))
                p += 12
            return lambda cp, g=groups: any(s <= cp <= e for s, e in g)
        if fmt == 4:
            segx2 = _u16(b, off + 6)
            seg = segx2 // 2
            ends = struct.unpack_from(">%dH" % seg, b, off + 14)
            starts = struct.unpack_from(">%dH" % seg, b, off + 16 + segx2)
            ranges = [(s, e) for s, e in zip(starts, ends) if not (s == 0xFFFF and e == 0xFFFF)]
            return lambda cp, r=ranges: cp <= 0xFFFF and any(s <= cp <= e for s, e in r)
    return None


def missing_chars(path, text):
    """Return list of characters in *text* not covered by the font (spaces ignored)."""
    try:
        with open(path, "rb") as f:
            t = _read_tables(f)
            cov = _parse_cmap(_read(f, t, "cmap"))
    except Exception:
        return []
    if cov is None:
        return []
    seen = []
    for ch in text:
        if ch.isspace() or ch in seen:
            continue
        if not cov(ord(ch)):
            seen.append(ch)
    return seen


# ---------------------------------------------------------------- category

CAT_JA = "JA"
CAT_SANS = "SANS"
CAT_SERIF = "SERIF"
CAT_SCRIPT = "SCRIPT"
CAT_DECO = "DECO"
CAT_MONO = "MONO"
CAT_SYMBOL = "SYMBOL"

_KW = [
    # (category, keywords) – checked against lower-cased names
    (CAT_MONO, ("mono", "courier", "consol", "等幅", "code", "terminal", "fixedsys")),
    (CAT_SCRIPT, ("script", "brush", "hand", "毛筆", "筆", "行書", "楷書", "草書", "教科書",
                  "kaisho", "gyosho", "kyokasho", "calligraph", "signature", "ink free")),
    (CAT_DECO, ("pop", "ポップ", "display", "deco", "stencil", "comic", "jokerman", "chiller",
                "impact", "showcard", "broadway", "bauhaus", "ravie")),
    (CAT_SERIF, ("mincho", "明朝", "serif", "batang", "song", "ming", "宋", "times", "georgia",
                 "garamond", "bodoni", "cambria", "century", "palatino", "book antiqua")),
    (CAT_SANS, ("gothic", "ゴシック", "sans", "丸ゴ", "maru", "round", "gulim", "dotum", "hei",
                "黑", "黒", "meiryo", "メイリオ", "arial", "helvetica", "segoe", "verdana",
                "tahoma", "calibri", "yu gothic", "游ゴ", "noto sans", "bizud")),
]


def _classify(names_lower, panose, fam_class, fixed_pitch):
    cats = set()
    if fixed_pitch or (panose and panose[0] == 2 and panose[3] == 9):
        cats.add(CAT_MONO)

    # keywords first (reliable for Japanese fonts whose PANOSE is often 0)
    kw_hit = False
    for cat, kws in _KW:
        if any(k in n for n in names_lower for k in kws):
            # "sans serif" must not also become SERIF
            if cat == CAT_SERIF and any("sans" in n for n in names_lower):
                continue
            cats.add(cat)
            if cat != CAT_MONO:
                kw_hit = True
                break

    if not kw_hit and panose:
        ft = panose[0]
        if ft == 3:
            cats.add(CAT_SCRIPT)
        elif ft == 4:
            cats.add(CAT_DECO)
        elif ft == 5:
            cats.add(CAT_SYMBOL)
        elif ft == 2:
            ss = panose[1]
            if 11 <= ss <= 15:
                cats.add(CAT_SANS)
            elif 2 <= ss <= 10:
                cats.add(CAT_SERIF)
    if not (cats - {CAT_MONO}):
        hi = (fam_class >> 8) & 0xFF
        if hi in (1, 2, 3, 4, 5, 7):
            cats.add(CAT_SERIF)
        elif hi == 8:
            cats.add(CAT_SANS)
        elif hi == 9:
            cats.add(CAT_DECO)
        elif hi == 10:
            cats.add(CAT_SCRIPT)
        elif hi == 12:
            cats.add(CAT_SYMBOL)
    return cats


# ---------------------------------------------------------------- public

def read_font_info(path):
    """Return dict with display names and categories, or None if unreadable."""
    with open(path, "rb") as f:
        t = _read_tables(f)
        names = _parse_names(_read(f, t, "name"))
        os2 = _read(f, t, "OS/2", 64)
        post = _read(f, t, "post", 16)
        cov = _parse_cmap(_read(f, t, "cmap"))

    def pick(*keys):
        for k in keys:
            if k in names:
                return names[k]
        return ""

    family = pick((16, "en"), (1, "en"), (16, "mac"), (1, "mac"), (16, "ja"), (1, "ja"))
    family_ja = pick((16, "ja"), (1, "ja"))
    style = pick((17, "en"), (2, "en"), (17, "mac"), (2, "mac"))
    full = pick((4, "en"), (4, "mac"), (4, "ja"))
    if not family:
        family = os.path.splitext(os.path.basename(path))[0]

    panose = None
    fam_class = 0
    if os2 and len(os2) >= 42:
        fam_class = _i16(os2, 30)
        panose = tuple(os2[32:42])
    fixed = bool(post and len(post) >= 16 and _u32(post, 12) != 0)

    is_ja = bool(cov and cov(0x3042) and cov(0x6F22))  # あ / 漢
    lower = [s.lower() for s in (family, family_ja, full, os.path.basename(path)) if s]
    cats = _classify(lower, panose, fam_class, fixed)
    if is_ja:
        cats.add(CAT_JA)

    return {
        "family": family,
        "family_ja": family_ja,
        "style": style or "Regular",
        "cats": sorted(cats),
    }


FONT_EXTS = (".ttf", ".otf", ".ttc")


def default_font_dirs():
    dirs = []
    if os.name == "nt":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(os.path.join(windir, "Fonts"))
        la = os.environ.get("LOCALAPPDATA")
        if la:
            dirs.append(os.path.join(la, "Microsoft", "Windows", "Fonts"))
    elif os.uname().sysname == "Darwin":
        dirs += ["/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    else:
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
                 os.path.expanduser("~/.local/share/fonts")]
    return [d for d in dirs if os.path.isdir(d)]


def list_font_files(dirs):
    seen = set()
    out = []
    for d in dirs:
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if fn.lower().endswith(FONT_EXTS):
                    p = os.path.normpath(os.path.join(root, fn))
                    key = os.path.normcase(p)
                    if key not in seen:
                        seen.add(key)
                        out.append(p)
    return out

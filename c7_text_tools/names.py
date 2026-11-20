# SPDX-License-Identifier: GPL-3.0-or-later
"""文字からオブジェクト名を作る共通処理。"""

MAX_BYTES = 63  # Blender の名前の上限（UTF-8）


def text_name(text, suffix=""):
    """「{テキスト}{suffix}」。改行（\\n や実際の改行）は空白、上限に収まるよう末尾を切る。"""
    base = " ".join(text.replace("\\n", " ").split()) or "Text"
    limit = MAX_BYTES - len(suffix.encode("utf-8"))
    while len(base.encode("utf-8")) > limit:
        base = base[:-1]
    return base.rstrip() + suffix

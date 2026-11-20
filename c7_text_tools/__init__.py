# SPDX-License-Identifier: GPL-3.0-or-later
"""C7 Text Tools

文字編集まわりをまとめたアドオン。
- かなスケール（平仮名・カタカナ・記号を文字種ごとにサイズ変更／1文字カーニング）
- 普通のテキスト → かなスケール／バラ文字へ送る
- 1文字ずつバラす（エンプティ＋コレクションで親子付け）
- アウトライン（フチだけ別オブジェクト・自動追従）
- フォントプレビュー（任意の文字でフォントを一覧・適用）
3D View > Sidebar (N) > C7
"""

bl_info = {
    "name": "C7 Text Tools",
    "author": "Yumi",
    "version": (0, 8, 4),
    "blender": (5, 0, 0),
    "location": "3D View > Sidebar (N) > C7",
    "description": "かなスケール・1文字調整・Skew・アウトライン・バラ文字・フォントプレビュー",
    "category": "Add Curve",
}

from . import outline, kana, split, convert, font_preview

_modules = (outline, kana, split, convert, font_preview)


def register():
    for m in _modules:
        m.register()


def unregister():
    for m in reversed(_modules):
        m.unregister()

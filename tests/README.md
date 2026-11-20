# tests / テスト

Run add-on tests without opening Blender, using the `bpy` module from pip.
pip の `bpy` モジュール(Blender を Python モジュールとして使えるもの)で、Blender を起動せずに動作確認します。

The `bpy` version must match its Python version (4.2 → Python 3.11, 5.x → Python 3.13).
`bpy` は対応する Python のバージョンでしか入りません(4.2 → Python 3.11、5.x → Python 3.13)。

```sh
# Blender 4.2
uv venv -p 3.11 venv311 && uv pip install -p venv311 "bpy==4.2.*"
venv311/bin/python tests/test_c7_color_clip.py c7_color_clip/__init__.py

# Blender 5.x
uv venv -p 3.13 venv313 && uv pip install -p venv313 "bpy>=5"
venv313/bin/python tests/test_c7_color_clip.py c7_color_clip/__init__.py

# C7 Text Tools (Blender 5.x only / 5.x のみ)
venv313/bin/python tests/test_c7_text_tools.py c7_text_tools
```

(Windows: `venv311\Scripts\python` instead of `venv311/bin/python`)

- `test_c7_color_clip.py` swaps `HOME` for a temp folder, so your real `~/BlenderColorClip` is never touched.
  テスト中は HOME を一時フォルダに差し替えるので、実際の `~/BlenderColorClip` には触れません。
- Last result / 最新結果: Blender 4.2.23 LTS 93/93, 5.3.0 93/93 PASS
- `test_c7_text_tools.py` needs at least one Japanese font installed. Font Preview favorites/cache go to a temp HOME.
  日本語フォントが1つ以上入っている環境で実行してください。フォントプレビューのお気に入り・キャッシュは一時フォルダに保存します。
- Last result / 最新結果 (C7 Text Tools): Blender 5.3.0 49/49 PASS

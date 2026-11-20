# SPDX-License-Identifier: GPL-3.0-or-later
"""C7 Text Tools: フォントプレビュー

3D View > Sidebar (N) > C7 tab.
Type any sample text, browse installed fonts as thumbnails rendered with
that text, filter by category / favorites, click to apply to selected
text objects.
"""

import json
import os

import bpy
import blf
import gpu
from bpy.props import (BoolProperty, EnumProperty, FloatVectorProperty,
                       IntProperty, StringProperty)
from mathutils import Matrix

from . import fontmeta

# ------------------------------------------------------------------ storage

def _config_dir():
    d = bpy.utils.user_resource('CONFIG', path="c7_font_preview", create=True)
    return d


def _json_load(name, default):
    p = os.path.join(_config_dir(), name)
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _json_save(name, data):
    p = os.path.join(_config_dir(), name)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[C7 Font Preview] save failed:", e)


class _State:
    fonts = []          # list of dicts: path, family, family_ja, style, cats, label
    favorites = set()   # normcased paths
    pcoll = None        # bpy.utils.previews collection
    preview_key = ""    # text/settings signature the current previews were made with
    offscreen = None
    offscreen_size = (0, 0)
    filtered_cache = None


S = _State()


def _fav_key(path):
    return os.path.normcase(os.path.normpath(path))


def load_favorites():
    S.favorites = set(_json_load("favorites.json", []))


def save_favorites():
    _json_save("favorites.json", sorted(S.favorites))


# ------------------------------------------------------------------ scanning

def scan_fonts(force=False):
    files = fontmeta.list_font_files(fontmeta.default_font_dirs())
    cache = {} if force else _json_load("font_cache.json", {})
    new_cache = {}
    fonts = []
    for p in files:
        try:
            st = os.stat(p)
        except OSError:
            continue
        sig = [st.st_size, int(st.st_mtime)]
        c = cache.get(p)
        if c and c.get("sig") == sig:
            info = c["info"]
        else:
            try:
                info = fontmeta.read_font_info(p)
            except Exception:
                continue
        new_cache[p] = {"sig": sig, "info": info}
        name = info["family_ja"] or info["family"]
        style = info["style"]
        label = name if style.lower() in ("regular", "normal", "標準") else f"{name} {style}"
        fonts.append(dict(info, path=p, label=label))
    fonts.sort(key=lambda d: d["label"].lower())
    _json_save("font_cache.json", new_cache)
    S.fonts = fonts
    S.filtered_cache = None
    return len(fonts)


# ------------------------------------------------------------------ filtering

CATEGORY_ITEMS = [
    ('ALL', "すべて", "全フォント"),
    ('FAV', "★お気に入り", "お気に入り登録したフォント"),
    ('JA', "日本語", "ひらがな・漢字を含むフォント"),
    ('SANS', "ゴシック/サンセリフ", ""),
    ('SERIF', "明朝/セリフ", ""),
    ('SCRIPT', "筆・手書き", ""),
    ('DECO', "装飾・ディスプレイ", ""),
    ('MONO', "等幅", ""),
]


def filtered_fonts(props):
    sig = (props.category, props.search.lower(), props.ja_only, len(S.fonts), len(S.favorites))
    if S.filtered_cache and S.filtered_cache[0] == sig:
        return S.filtered_cache[1]
    q = props.search.lower().strip()
    out = []
    for f in S.fonts:
        cats = f["cats"]
        cat = props.category
        if cat == 'FAV':
            if _fav_key(f["path"]) not in S.favorites:
                continue
        elif cat != 'ALL' and cat not in cats:
            continue
        if props.ja_only and "JA" not in cats:
            continue
        if q:
            hay = " ".join((f["family"], f["family_ja"], f["style"],
                            os.path.basename(f["path"]))).lower()
            if q not in hay:
                continue
        out.append(f)
    S.filtered_cache = (sig, out)
    return out


# ------------------------------------------------------------------ rendering

PREVIEW_W = 256
PREVIEW_H = 256


def _protected_paths():
    v = bpy.context.preferences.view
    out = set()
    for attr in ("font_path_ui", "font_path_ui_mono"):
        p = getattr(v, attr, "")
        if p:
            out.add(_fav_key(bpy.path.abspath(p)))
    return out


def _get_offscreen(w, h):
    if S.offscreen is None or S.offscreen_size != (w, h):
        if S.offscreen is not None:
            try:
                S.offscreen.free()
            except Exception:
                pass
        S.offscreen = gpu.types.GPUOffScreen(w, h, format='RGBA16F')
        S.offscreen_size = (w, h)
    return S.offscreen


def _split_lines(text, n):
    """Split *text* into n lines of roughly equal length (prefer spaces)."""
    if n <= 1:
        return [text]
    lines = []
    rest = text
    for i in range(n - 1, 0, -1):
        target = len(rest) / (i + 1)
        cut = round(target)
        # look for a space near the target
        best = None
        for d in range(0, max(2, int(target * 0.4)) + 1):
            for c in (cut - d, cut + d):
                if 0 < c < len(rest) and rest[c] == " ":
                    best = c
                    break
            if best is not None:
                break
        if best is None:
            best = max(1, min(len(rest) - 1, cut))
        lines.append(rest[:best].strip())
        rest = rest[best:].strip()
        if not rest:
            break
    if rest:
        lines.append(rest)
    return [l for l in lines if l] or [text]


def render_preview_pixels(path, text, dark=True, text_color=None):
    """Draw *text* with font at *path*. Returns flat float list (RGBA) or None."""
    w, h = PREVIEW_W, PREVIEW_H
    fid = blf.load(path)
    if fid == -1:
        return None
    try:
        blf.enable(fid, blf.NO_FALLBACK)
        missing = fontmeta.missing_chars(path, text)
        draw_text = "".join(ch for ch in text if ch not in missing) or text

        # choose line count that gives the largest glyph size
        margin = 0.88
        ref = 100
        blf.size(fid, ref)
        best = None
        for n in range(1, 5):
            if n > max(1, len(draw_text.replace(" ", ""))):
                break
            lines = _split_lines(draw_text, n)
            maxw = max(blf.dimensions(fid, l)[0] for l in lines) or 1
            lh_ratio = 1.3
            s = min(w * margin / maxw * ref, h * margin / (len(lines) * lh_ratio))
            if best is None or s > best[0]:
                best = (s, lines)
        size, lines = best
        size = max(4, min(size, h * 0.8))

        off = _get_offscreen(w, h)
        bg = (0.11, 0.11, 0.12, 1.0) if dark else (0.93, 0.93, 0.93, 1.0)
        fg = text_color or ((0.95, 0.95, 0.95, 1.0) if dark else (0.08, 0.08, 0.08, 1.0))

        with off.bind():
            fb = gpu.state.active_framebuffer_get()
            fb.clear(color=bg)
            with gpu.matrix.push_pop():
                gpu.matrix.load_matrix(Matrix.Identity(4))
                gpu.matrix.load_projection_matrix(Matrix((
                    (2.0 / w, 0, 0, -1.0),
                    (0, 2.0 / h, 0, -1.0),
                    (0, 0, 1.0, 0),
                    (0, 0, 0, 1.0))))
                gpu.state.blend_set('ALPHA')
                blf.size(fid, size)
                blf.color(fid, *fg)
                lh = size * 1.3
                total = lh * len(lines)
                top = (h + total) / 2.0
                for i, line in enumerate(lines):
                    lw = blf.dimensions(fid, line)[0]
                    y = top - lh * (i + 1) + size * 0.32
                    blf.position(fid, (w - lw) / 2.0, y, 0)
                    blf.draw(fid, line)
                if missing:
                    # small warning with Blender's default font (id 0)
                    blf.size(0, 15)
                    blf.color(0, 1.0, 0.45, 0.35, 1.0)
                    msg = "未対応: " + "".join(missing[:8]) + ("…" if len(missing) > 8 else "")
                    blf.position(0, 6, 6, 0)
                    blf.draw(0, msg)
                gpu.state.blend_set('NONE')
            buf = fb.read_color(0, 0, w, h, 4, 0, 'FLOAT')
        buf.dimensions = w * h * 4
        return buf
    finally:
        if _fav_key(path) not in _protected_paths():
            try:
                blf.unload(path)
            except Exception:
                pass


def _preview_signature(props):
    return "%s|%d|%s" % (props.sample_text, props.dark_bg, tuple(round(c, 3) for c in props.text_color))


def ensure_previews(props, fonts):
    """Render previews for *fonts* if missing. Returns number rendered."""
    if S.pcoll is None:
        return 0
    sig = _preview_signature(props)
    if sig != S.preview_key:
        S.pcoll.clear()
        S.preview_key = sig
    text = (props.sample_text or "Aa").replace("\\n", " ")
    n = 0
    for f in fonts:
        key = f["path"]
        if key in S.pcoll:
            continue
        px = None
        try:
            px = render_preview_pixels(key, text, props.dark_bg,
                                       tuple(props.text_color) + (1.0,) if props.use_text_color else None)
        except Exception as e:
            print("[C7 Font Preview] render failed:", key, e)
        p = S.pcoll.new(key)
        p.image_size = (PREVIEW_W, PREVIEW_H)
        if px is not None:
            p.image_pixels_float.foreach_set(px)
        n += 1
    return n


def page_fonts(props):
    fonts = filtered_fonts(props)
    per = props.per_page
    pages = max(1, (len(fonts) + per - 1) // per)
    page = min(max(props.page, 0), pages - 1)
    return fonts[page * per:(page + 1) * per], page, pages, len(fonts)


def _tag_redraw():
    wm = bpy.context.window_manager
    if not wm:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _render_current_page():
    try:
        props = bpy.context.window_manager.c7_font_preview
        fonts, *_ = page_fonts(props)
        if ensure_previews(props, fonts):
            _tag_redraw()
    except Exception as e:
        print("[C7 Font Preview]", e)
    return None


def _refresh_page_deferred():
    """Render the current page outside of draw() via a one-shot timer."""
    if not bpy.app.timers.is_registered(_render_current_page):
        bpy.app.timers.register(_render_current_page, first_interval=0.0)


def _on_change(self, context):
    _refresh_page_deferred()


def _on_filter_change(self, context):
    self["page"] = 0
    S.filtered_cache = None
    _refresh_page_deferred()


# ------------------------------------------------------------------ properties

class C7FP_Props(bpy.types.PropertyGroup):
    sample_text: StringProperty(
        name="プレビュー文字", default="あいう アイウ 永 Abc 123",
        description="サムネイルに表示する文字", update=_on_change)
    category: EnumProperty(name="カテゴリ", items=CATEGORY_ITEMS, default='ALL',
                           update=_on_filter_change)
    search: StringProperty(name="検索", default="", options={'TEXTEDIT_UPDATE'},
                           description="フォント名・ファイル名で絞り込み",
                           update=_on_filter_change)
    ja_only: BoolProperty(name="日本語のみ", default=False, update=_on_filter_change,
                          description="ひらがな・漢字を含むフォントだけ表示")
    page: IntProperty(name="ページ", default=0, min=0, update=_on_change)
    per_page: IntProperty(name="1ページの数", default=12, min=4, max=60,
                          update=_on_filter_change)
    columns: IntProperty(name="列数", default=2, min=1, max=6)
    thumb_scale: IntProperty(name="サムネサイズ", default=6, min=3, max=15)
    dark_bg: BoolProperty(name="暗い背景", default=True, update=_on_change)
    use_text_color: BoolProperty(name="文字色を指定", default=False, update=_on_change)
    text_color: FloatVectorProperty(name="文字色", subtype='COLOR', size=3, min=0, max=1,
                                    default=(0.78, 0.765, 0.882), update=_on_change)
    show_settings: BoolProperty(name="表示設定", default=False)


# ------------------------------------------------------------------ operators

def _is_kana(o):
    return o is not None and o.type == 'CURVE' and getattr(o, "c7_kana", None) is not None \
        and o.c7_kana.is_c7


def _is_text(o):
    return o is not None and (o.type == 'FONT' or _is_kana(o))


def _target_text_objects(context):
    objs = [o for o in context.selected_objects if _is_text(o)]
    ao = context.active_object
    if _is_text(ao) and ao not in objs:
        objs.append(ao)
    return objs


class C7FP_OT_apply(bpy.types.Operator):
    bl_idname = "c7fp.apply_font"
    bl_label = "フォントを適用"
    bl_description = "選択中のテキストオブジェクトにこのフォントを適用"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        objs = _target_text_objects(context)
        if not objs:
            self.report({'WARNING'}, "テキストオブジェクトを選択してください")
            return {'CANCELLED'}
        try:
            vf = bpy.data.fonts.load(self.filepath, check_existing=True)
        except Exception as e:
            self.report({'ERROR'}, f"読み込めませんでした: {e}")
            return {'CANCELLED'}
        for o in objs:
            if _is_kana(o):
                o.c7_kana.font = vf  # 更新時に自動で再生成
            else:
                o.data.font = vf
        self.report({'INFO'}, f"{vf.name} を {len(objs)} 個に適用")
        return {'FINISHED'}


class C7FP_OT_toggle_fav(bpy.types.Operator):
    bl_idname = "c7fp.toggle_favorite"
    bl_label = "お気に入り"
    bl_description = "お気に入りに追加／解除"
    bl_options = {'INTERNAL'}

    filepath: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        k = _fav_key(self.filepath)
        if k in S.favorites:
            S.favorites.discard(k)
        else:
            S.favorites.add(k)
        save_favorites()
        S.filtered_cache = None
        if context.window_manager.c7_font_preview.category == 'FAV':
            _refresh_page_deferred()
        return {'FINISHED'}


class C7FP_OT_page(bpy.types.Operator):
    bl_idname = "c7fp.page"
    bl_label = "ページ移動"
    bl_options = {'INTERNAL'}

    step: IntProperty(default=1)

    def execute(self, context):
        props = context.window_manager.c7_font_preview
        _f, page, pages, _n = page_fonts(props)
        props.page = (page + self.step) % pages
        return {'FINISHED'}


class C7FP_OT_rescan(bpy.types.Operator):
    bl_idname = "c7fp.rescan"
    bl_label = "フォント再スキャン"
    bl_description = "インストール済みフォントを読み直す（新しく入れたフォントを反映）"

    full: BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        n = scan_fonts(force=self.full)
        if S.pcoll is not None:
            S.pcoll.clear()
        S.preview_key = ""
        _refresh_page_deferred()
        self.report({'INFO'}, f"{n} フォント")
        return {'FINISHED'}


def _sample_body(context):
    """プレビュー欄の文字（\\n は改行）。"""
    return context.window_manager.c7_font_preview.sample_text


class C7FP_OT_apply_text(bpy.types.Operator):
    bl_idname = "c7fp.apply_text"
    bl_label = "選択テキストに反映"
    bl_description = "プレビュー欄の文字を、選択中のテキストの中身にする（\\n で改行）"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(_target_text_objects(context)) and \
            context.mode in {'OBJECT', 'EDIT_TEXT', 'EDIT_CURVE'}

    def execute(self, context):
        text = _sample_body(context)
        objs = _target_text_objects(context)
        ao = context.active_object
        if ao is not None and ao.type == 'FONT' and ao.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for o in objs:
            if _is_kana(o):
                o.c7_kana.text = text
            else:
                o.data.body = text.replace("\\n", "\n")
        self.report({'INFO'}, f"{len(objs)} 個に反映")
        return {'FINISHED'}


def text_object_name(body, suffix="_text"):
    from .names import text_name
    return text_name(body, suffix)


class C7FP_OT_new_text(bpy.types.Operator):
    bl_idname = "c7fp.new_text"
    bl_label = "この文字で新規テキスト"
    bl_description = "プレビュー欄の文字とこのフォントで、3Dカーソル位置に新しいテキストを作る"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            vf = bpy.data.fonts.load(self.filepath, check_existing=True)
        except Exception as e:
            self.report({'ERROR'}, f"読み込めませんでした: {e}")
            return {'CANCELLED'}
        body = _sample_body(context).replace("\\n", "\n") or "Text"
        name = text_object_name(body)
        cu = bpy.data.curves.new(name, 'FONT')
        cu.body = body
        cu.font = vf
        ob = bpy.data.objects.new(name, cu)
        context.collection.objects.link(ob)
        ob.location = context.scene.cursor.location
        for o in context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        return {'FINISHED'}


class C7FP_OT_use_current_text(bpy.types.Operator):
    bl_idname = "c7fp.use_object_text"
    bl_label = "選択テキストの文字を使う"
    bl_description = "アクティブなテキストオブジェクトの文字をプレビュー文字にする"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return _is_text(context.active_object)

    def execute(self, context):
        o = context.active_object
        # 改行は \\n のまま持つ（反映し直したときに改行が戻るように）
        raw = o.c7_kana.text if _is_kana(o) else o.data.body.replace("\n", "\\n")
        body = raw.strip()
        if body:
            context.window_manager.c7_font_preview.sample_text = body[:120]
        return {'FINISHED'}


# ------------------------------------------------------------------ UI

def _current_font_key(context):
    o = context.active_object
    font = None
    if _is_kana(o):
        font = o.c7_kana.font
    elif o is not None and o.type == 'FONT':
        font = o.data.font
    if font and font.filepath:
        return _fav_key(bpy.path.abspath(font.filepath))
    return None


class C7FP_PT_main(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "C7"
    bl_label = "C7 Font Preview"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        props = context.window_manager.c7_font_preview

        row = layout.row(align=True)
        row.prop(props, "sample_text", text="")
        row.operator(C7FP_OT_use_current_text.bl_idname, text="", icon='EYEDROPPER')
        layout.operator(C7FP_OT_apply_text.bl_idname, icon='PASTEDOWN')

        row = layout.row(align=True)
        row.prop(props, "category", text="")
        row.prop(props, "ja_only", text="日本語", toggle=True)
        layout.prop(props, "search", text="", icon='VIEWZOOM')

        box = layout.box()
        r = box.row()
        r.prop(props, "show_settings", icon='TRIA_DOWN' if props.show_settings else 'TRIA_RIGHT',
               emboss=False)
        if props.show_settings:
            col = box.column(align=True)
            col.prop(props, "columns")
            col.prop(props, "thumb_scale")
            col.prop(props, "per_page")
            col = box.column()
            col.prop(props, "dark_bg")
            r = col.row(align=True)
            r.prop(props, "use_text_color", text="")
            sub = r.row()
            sub.active = props.use_text_color
            sub.prop(props, "text_color", text="文字色")
            col.operator(C7FP_OT_rescan.bl_idname, icon='FILE_REFRESH')

        if not S.fonts:
            layout.operator(C7FP_OT_rescan.bl_idname, text="フォントを読み込む", icon='FILE_REFRESH')
            return

        fonts, page, pages, total = page_fonts(props)

        row = layout.row(align=True)
        row.operator(C7FP_OT_page.bl_idname, text="", icon='TRIA_LEFT').step = -1
        row.label(text=f"{page + 1} / {pages}   ({total})")
        row.operator(C7FP_OT_page.bl_idname, text="", icon='TRIA_RIGHT').step = 1

        if not fonts:
            layout.label(text="該当するフォントがありません", icon='INFO')
            return

        need_render = S.pcoll is None or S.preview_key != _preview_signature(props) or \
            any(f["path"] not in S.pcoll for f in fonts)
        if need_render:
            _refresh_page_deferred()

        has_target = bool(_target_text_objects(context))
        cur = _current_font_key(context)

        hint = layout.row()
        hint.scale_y = 0.8
        if has_target:
            hint.label(text="✓ フォント名を押すと適用", icon='INFO')
        else:
            hint.label(text="テキストを選択 → フォント名で適用", icon='INFO')

        grid = layout.grid_flow(row_major=True, columns=props.columns,
                                even_columns=True, even_rows=False, align=False)
        for f in fonts:
            cell = grid.column(align=True)
            k = _fav_key(f["path"])
            if S.pcoll is not None and f["path"] in S.pcoll:
                cell.template_icon(icon_value=S.pcoll[f["path"]].icon_id, scale=props.thumb_scale)
            else:
                cell.label(text="…生成中")
            r = cell.row(align=True)
            sub = r.row(align=True)
            sub.enabled = has_target
            op = sub.operator(C7FP_OT_apply.bl_idname, text=f["label"],
                              icon='CHECKMARK', depress=(k == cur))
            op.filepath = f["path"]
            fav = k in S.favorites
            r.operator(C7FP_OT_new_text.bl_idname, text="", icon='ADD').filepath = f["path"]
            r.operator(C7FP_OT_toggle_fav.bl_idname, text="",
                       icon='SOLO_ON' if fav else 'SOLO_OFF').filepath = f["path"]

        row = layout.row(align=True)
        row.operator(C7FP_OT_page.bl_idname, text="", icon='TRIA_LEFT').step = -1
        row.label(text=f"{page + 1} / {pages}")
        row.operator(C7FP_OT_page.bl_idname, text="", icon='TRIA_RIGHT').step = 1


# ------------------------------------------------------------------ register

classes = (
    C7FP_Props,
    C7FP_OT_apply,
    C7FP_OT_toggle_fav,
    C7FP_OT_page,
    C7FP_OT_rescan,
    C7FP_OT_use_current_text,
    C7FP_OT_apply_text,
    C7FP_OT_new_text,
    C7FP_PT_main,
)


def _initial_scan():
    try:
        scan_fonts()
    except Exception as e:
        print("[C7 Font Preview] scan failed:", e)
    _tag_redraw()
    return None


def register():
    import bpy.utils.previews
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.WindowManager.c7_font_preview = bpy.props.PointerProperty(type=C7FP_Props)
    S.pcoll = bpy.utils.previews.new()
    S.preview_key = ""
    load_favorites()
    bpy.app.timers.register(_initial_scan, first_interval=0.5)


def unregister():
    import bpy.utils.previews
    for fn in (_initial_scan, _render_current_page):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
    if S.pcoll is not None:
        bpy.utils.previews.remove(S.pcoll)
        S.pcoll = None
    if S.offscreen is not None:
        try:
            S.offscreen.free()
        except Exception:
            pass
        S.offscreen = None
    del bpy.types.WindowManager.c7_font_preview
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

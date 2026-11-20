"""C7 Text Tools: かなスケールテキスト（文字種ごとにサイズを変えたカーブ文字）"""

import math
import os
import re
import unicodedata

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

# ---------------------------------------------------------------------------
# 文字種の判定
# ---------------------------------------------------------------------------
CAT_BASE, CAT_HIRA, CAT_KATA, CAT_SYM = 0, 1, 2, 3


def classify(c):
    o = ord(c)
    if 0x3041 <= o <= 0x3096 or 0x309D <= o <= 0x309F:
        return CAT_HIRA
    if o == 0x30FB:  # ・ は記号扱い
        return CAT_SYM
    if 0x30A1 <= o <= 0x30FF or 0x31F0 <= o <= 0x31FF or 0xFF66 <= o <= 0xFF9D:
        return CAT_KATA
    if c in "々〆〇ヶ":
        return CAT_BASE
    if unicodedata.category(c)[0] in "PS":
        return CAT_SYM
    return CAT_BASE


# ---------------------------------------------------------------------------
# グリフ計測・キャッシュ（サイズ1で計測し、使うときに拡大縮小）
# ---------------------------------------------------------------------------
_glyph_cache = {}   # (font_key, char) -> list of spline dicts
_adv_cache = {}     # (font_key, char) -> advance
_metric_cache = {}  # font_key -> dict(em, center)


def _font_key(font):
    return (font.name, font.filepath)


def _temp_curve(font, body, mat_last=False):
    cu = bpy.data.curves.new("_c7tmp", "FONT")
    cu.font = font
    cu.body = body
    cu.size = 1.0
    if mat_last:
        cu.body_format[len(body) - 1].material_index = 1
    ob = bpy.data.objects.new("_c7tmp", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    ob_eval = ob.evaluated_get(dg)
    curve = ob_eval.to_curve(dg)
    data = []
    for sp in curve.splines:
        d = {
            "type": sp.type,
            "cyclic": sp.use_cyclic_u,
            "mat": sp.material_index,
        }
        if sp.type == "BEZIER":
            d["pts"] = [
                (p.co.copy(), p.handle_left.copy(), p.handle_right.copy(),
                 p.handle_left_type, p.handle_right_type)
                for p in sp.bezier_points
            ]
        else:
            d["pts"] = [p.co.copy() for p in sp.points]
        data.append(d)
    ob_eval.to_curve_clear()
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return data


def _min_x(splines, mat=None):
    xs = []
    for d in splines:
        if mat is not None and d["mat"] != mat:
            continue
        for p in d["pts"]:
            xs.append(p[0].x if d["type"] == "BEZIER" else p.x)
    return min(xs) if xs else None


def _y_range(splines):
    ys = []
    for d in splines:
        for p in d["pts"]:
            ys.append(p[0].y if d["type"] == "BEZIER" else p.y)
    return (min(ys), max(ys)) if ys else (0.0, 0.0)


def glyph(font, c):
    key = (_font_key(font), c)
    if key not in _glyph_cache:
        _glyph_cache[key] = _temp_curve(font, c) if not c.isspace() else []
    return _glyph_cache[key]


def advance(font, c):
    """文字送り幅（サイズ1）。'H'+c+'H' と 'HH' の最後のHの位置差で測る。"""
    key = (_font_key(font), c)
    if key not in _adv_cache:
        a = _min_x(_temp_curve(font, "H" + c + "H", True), 1)
        b = _min_x(_temp_curve(font, "HH", True), 1)
        _adv_cache[key] = (a - b) if (a is not None and b is not None) else 0.0
    return _adv_cache[key]


def metrics(font):
    fk = _font_key(font)
    if fk not in _metric_cache:
        em = advance(font, "\u3000") or advance(font, "漢") or 1.0
        lo, hi = _y_range(glyph(font, "口"))
        center = (lo + hi) / 2 if hi > lo else em * 0.38
        _metric_cache[fk] = {"em": em, "center": center}
    return _metric_cache[fk]


def clear_cache():
    _glyph_cache.clear()
    _adv_cache.clear()
    _metric_cache.clear()


# ---------------------------------------------------------------------------
# 組版・生成
# ---------------------------------------------------------------------------
def _scale_of(st, cat):
    return {
        CAT_BASE: 1.0,
        CAT_HIRA: st.scale_hira / 100.0,
        CAT_KATA: st.scale_kata / 100.0,
        CAT_SYM: st.scale_sym / 100.0,
    }[cat]


def _offset_y(st, cat):
    return {
        CAT_BASE: 0.0,
        CAT_HIRA: st.offset_hira,
        CAT_KATA: st.offset_kata,
        CAT_SYM: st.offset_sym,
    }[cat]


def layout(st):
    """[(char, cat, scale, x, y, shear)] を返す（座標は文字の原点＝ベースライン左端）"""
    font = st.font
    m = metrics(font)
    em, center = m["em"], m["center"]
    size = st.size
    text = st.text.replace("\\n", "\n")
    lines = text.split("\n")

    kern = {k.index: k.value for k in st.kernings}
    adj = {a.index: a for a in st.char_adjust}
    base_skew = st.skew

    placed = []
    gi = 0  # 改行も含めた通し番号（0始まり）
    for li, line in enumerate(lines):
        y_line = -li * st.line_spacing * em * size
        x = 0.0
        row = []
        for c in line:
            ci = gi
            gi += 1
            cat = classify(c)
            a = adj.get(ci)
            s = _scale_of(st, cat) * (a.scale / 100.0 if a else 1.0)
            cs = size * s
            y = y_line
            if st.align_mode == "CENTER":
                y += center * (size - cs)
            y += _offset_y(st, cat) * em * size
            if a:
                y += a.rise * em * size
            ang = base_skew + (a.skew if a else 0.0)
            shear = math.tan(max(-1.4, min(1.4, ang)))
            row.append((c, cat, cs, x, y, shear))
            x += advance(font, c) * cs + st.tracking * em * size
            if ci != len(text) - 1 and text[ci + 1] != "\n":
                x += kern.get(ci, 0.0) * em * size
        gi += 1  # 改行ぶん
        if row:
            x -= st.tracking * em * size  # 末尾の字間は除く
        if st.align_x == "CENTER":
            shift = -x / 2
        elif st.align_x == "RIGHT":
            shift = -x
        else:
            shift = 0.0
        placed.extend((c, cat, cs, px + shift, py, sh) for c, cat, cs, px, py, sh in row)
    return placed


def emit_char(cu, font, c, cs, px, py, sh, mat, ox=0.0, oy=0.0):
    """1文字分の輪郭を cu に追加（ox, oy は差し引く原点）。"""
    px -= ox
    py -= oy
    for d in glyph(font, c):
        if d["type"] == "BEZIER":
            sp = cu.splines.new("BEZIER")
            pts = d["pts"]
            sp.bezier_points.add(len(pts) - 1)
            for bp, (co, hl, hr, tl, tr) in zip(sp.bezier_points, pts):
                bp.co = ((co.x + sh * co.y) * cs + px, co.y * cs + py, 0.0)
                bp.handle_left = ((hl.x + sh * hl.y) * cs + px, hl.y * cs + py, 0.0)
                bp.handle_right = ((hr.x + sh * hr.y) * cs + px, hr.y * cs + py, 0.0)
                bp.handle_left_type = tl
                bp.handle_right_type = tr
        else:
            sp = cu.splines.new(d["type"])
            pts = d["pts"]
            sp.points.add(len(pts) - 1)
            for p, co in zip(sp.points, pts):
                p.co = ((co.x + sh * co.y) * cs + px, co.y * cs + py, 0.0, co.w)
        sp.use_cyclic_u = d["cyclic"]
        sp.material_index = mat


def char_bounds(font, c, cs, px, py, sh):
    """配置後の1文字の (min_x, min_y, max_x, max_y)。輪郭がなければ None。"""
    xs, ys = [], []
    for d in glyph(font, c):
        for p in d["pts"]:
            co = p[0] if d["type"] == "BEZIER" else p
            xs.append((co.x + sh * co.y) * cs + px)
            ys.append(co.y * cs + py)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def rebuild(ob):
    st = ob.c7_kana
    cu = ob.data
    cu.splines.clear()
    if st.font is None or not st.text:
        cu.update_tag()
        return
    for c, cat, cs, px, py, sh in layout(st):
        if c.isspace():
            continue
        mat = cat if st.use_cat_material else 0
        emit_char(cu, st.font, c, cs, px, py, sh, mat)
    cu.update_tag()
    if ob.c7_outline.target is not None:
        from . import outline
        outline.sync(ob, force=True)


def _on_update(self, context):
    ob = self.id_data
    if isinstance(ob, bpy.types.Object) and ob.type == "CURVE" and ob.c7_kana.is_c7:
        rebuild(ob)


def _strip_dup(name):
    """「名前.001」の .001 を除いた名前。"""
    return re.sub(r"\.\d{3}$", "", name)


def apply_auto_name(ob, force=False):
    """名前が自動で付けたもののままなら、今の文字に合わせて付け直す。"""
    from .names import text_name
    st = ob.c7_kana
    if not force and _strip_dup(ob.name) != st.auto_name:
        return
    new = text_name(st.text, "_kana")
    if _strip_dup(ob.name) != new:
        ob.name = new
        if ob.data and ob.data.users == 1:
            ob.data.name = new
        out = ob.c7_outline.target
        if out is not None:
            out.name = ob.name + "_outline"
    st.auto_name = new


def _on_text_update(self, context):
    ob = self.id_data
    if isinstance(ob, bpy.types.Object) and ob.type == "CURVE" and ob.c7_kana.is_c7:
        if self.auto_name:
            apply_auto_name(ob)
        rebuild(ob)


def _on_font_update(self, context):
    _on_update(self, context)


# ---------------------------------------------------------------------------
# プロパティ
# ---------------------------------------------------------------------------
class C7KernItem(bpy.types.PropertyGroup):
    index: IntProperty(name="位置", description="何文字目の後ろか（0始まり・改行も1文字）")
    value: FloatProperty(name="カーニング", step=1, description="全角1文字分＝1.0", update=_on_update)


def _flat_text(st):
    return st.text.replace("\\n", "\n")


def _kern_find(st, idx):
    for i, k in enumerate(st.kernings):
        if k.index == idx:
            return i, k
    return -1, None


def _kern_get(self):
    _, k = _kern_find(self, self.kern_cursor - 1)
    return k.value if k else 0.0


def _kern_set(self, value):
    idx = self.kern_cursor - 1
    i, k = _kern_find(self, idx)
    if abs(value) < 1e-6:
        if i >= 0:
            self.kernings.remove(i)
    elif k:
        k.value = value
    else:
        k = self.kernings.add()
        k.index = idx
        k.value = value
    ob = self.id_data
    if isinstance(ob, bpy.types.Object) and ob.type == "CURVE" and ob.c7_kana.is_c7:
        rebuild(ob)


def kern_pair_label(st, idx):
    t = _flat_text(st)
    if not (0 <= idx < len(t) - 1):
        return None
    a, b = t[idx], t[idx + 1]
    if a == "\n" or b == "\n":
        return None
    return f"「{a}」と「{b}」の間"


class C7CharAdjust(bpy.types.PropertyGroup):
    index: IntProperty(name="位置", description="何文字目か（0始まり・改行も1文字）")
    rise: FloatProperty(name="高さ", default=0.0, update=_on_update)
    skew: FloatProperty(name="傾き", default=0.0, subtype="ANGLE", update=_on_update)
    scale: FloatProperty(name="サイズ", default=100.0, subtype="PERCENTAGE", update=_on_update)


_ADJ_DEFAULTS = {"rise": 0.0, "skew": 0.0, "scale": 100.0}


def _adj_find(st, idx):
    for i, a in enumerate(st.char_adjust):
        if a.index == idx:
            return i, a
    return -1, None


def _rebuild_owner(st):
    ob = st.id_data
    if isinstance(ob, bpy.types.Object) and ob.type == "CURVE" and ob.c7_kana.is_c7:
        rebuild(ob)


def _adj_accessors(field):
    default = _ADJ_DEFAULTS[field]

    def _get(self):
        _, a = _adj_find(self, self.kern_cursor - 1)
        return getattr(a, field) if a else default

    def _set(self, value):
        idx = self.kern_cursor - 1
        i, a = _adj_find(self, idx)
        if a is None:
            if abs(value - default) < 1e-6:
                return
            a = self.char_adjust.add()
            a.index = idx
        setattr(a, field, value)
        # 全部初期値に戻ったら項目ごと消す
        if all(abs(getattr(a, f) - d) < 1e-6 for f, d in _ADJ_DEFAULTS.items()):
            self.char_adjust.remove(_adj_find(self, idx)[0])
        _rebuild_owner(self)
    return _get, _set


_rise_get, _rise_set = _adj_accessors("rise")
_cskew_get, _cskew_set = _adj_accessors("skew")
_cscale_get, _cscale_set = _adj_accessors("scale")


def char_at(st, idx):
    t = _flat_text(st)
    if 0 <= idx < len(t) and t[idx] != "\n":
        return t[idx]
    return None


class C7KanaSettings(bpy.types.PropertyGroup):
    is_c7: BoolProperty(default=False, options={"HIDDEN"})
    text: StringProperty(
        name="テキスト", default="平仮名を小さく",
        description="改行は \\n と入力", update=_on_text_update)
    auto_name: StringProperty(options={"HIDDEN"},
                              description="自動で付けた名前（手で変えていなければ文字に追従）")
    font: PointerProperty(name="フォント", type=bpy.types.VectorFont, update=_on_font_update)
    size: FloatProperty(name="サイズ", default=1.0, min=0.001, soft_max=10, update=_on_update)

    scale_hira: FloatProperty(name="平仮名", default=75.0, min=1, soft_max=200, max=500,
                              subtype="PERCENTAGE", update=_on_update)
    scale_kata: FloatProperty(name="カタカナ", default=75.0, min=1, soft_max=200, max=500,
                              subtype="PERCENTAGE", update=_on_update)
    scale_sym: FloatProperty(name="記号・句読点", default=100.0, min=1, soft_max=200, max=500,
                             subtype="PERCENTAGE", update=_on_update)

    offset_hira: FloatProperty(name="平仮名", default=0.0, soft_min=-0.5, soft_max=0.5, step=1,
                               description="上下の微調整（全角1文字分＝1.0）", update=_on_update)
    offset_kata: FloatProperty(name="カタカナ", default=0.0, soft_min=-0.5, soft_max=0.5, step=1,
                               description="上下の微調整（全角1文字分＝1.0）", update=_on_update)
    offset_sym: FloatProperty(name="記号・句読点", default=0.0, soft_min=-0.5, soft_max=0.5, step=1,
                              description="上下の微調整（全角1文字分＝1.0）", update=_on_update)

    align_mode: EnumProperty(
        name="揃え位置",
        items=[("BASELINE", "下揃え", "ベースラインで揃える"),
               ("CENTER", "中央揃え", "文字の中心の高さで揃える")],
        default="BASELINE", update=_on_update)
    align_x: EnumProperty(
        name="行揃え",
        items=[("LEFT", "左", ""), ("CENTER", "中央", ""), ("RIGHT", "右", "")],
        default="LEFT", update=_on_update)
    tracking: FloatProperty(name="字間", default=0.0, soft_min=-0.5, soft_max=1.0, step=1,
                            description="全角1文字分＝1.0", update=_on_update)
    line_spacing: FloatProperty(name="行送り", default=1.2, min=0.1, soft_max=3.0, update=_on_update)
    kernings: CollectionProperty(type=C7KernItem)
    char_adjust: CollectionProperty(type=C7CharAdjust)
    skew: FloatProperty(
        name="傾き（全体）", default=0.0, subtype="ANGLE", soft_min=math.radians(-45),
        soft_max=math.radians(45), description="プラスで右に傾く（イタリック風）", update=_on_update)
    char_rise: FloatProperty(
        name="高さ", get=_rise_get, set=_rise_set, step=1, soft_min=-0.5, soft_max=0.5,
        description="選んだ文字を上下に動かす（全角1文字分＝1.0、プラスで上）")
    char_skew: FloatProperty(
        name="傾き", get=_cskew_get, set=_cskew_set, subtype="ANGLE",
        soft_min=math.radians(-45), soft_max=math.radians(45),
        description="選んだ文字だけ追加で傾ける（全体の傾きに足される）")
    char_scale: FloatProperty(
        name="サイズ", get=_cscale_get, set=_cscale_set, subtype="PERCENTAGE",
        min=1, soft_max=200, max=500, description="選んだ文字だけ拡大縮小（文字種のサイズに掛け算）")
    kern_cursor: IntProperty(
        name="文字", default=1, min=1, soft_max=50,
        description="調整する文字の番号（1始まり・改行も1文字）。カーニングはこの文字と次の文字の間")
    kern_value: FloatProperty(
        name="カーニング", get=_kern_get, set=_kern_set, step=1,
        soft_min=-0.5, soft_max=0.5,
        description="選んだ文字と次の文字の間隔（全角1文字分＝1.0、マイナスで詰める）")
    use_cat_material: BoolProperty(
        name="文字種ごとにマテリアル番号を分ける", default=False,
        description="0:漢字など 1:平仮名 2:カタカナ 3:記号", update=_on_update)


# ---------------------------------------------------------------------------
# オペレーター
# ---------------------------------------------------------------------------
_JP_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
    r"C:\Windows\Fonts\msgothic.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def _default_font():
    for f in bpy.data.fonts:
        if f.filepath and f.name != "Bfont Regular":
            return f
    for p in _JP_FONT_CANDIDATES:
        if os.path.exists(p):
            return bpy.data.fonts.load(p, check_existing=True)
    return None


class C7KANA_OT_add(bpy.types.Operator):
    bl_idname = "c7kana.add"
    bl_label = "かなスケールテキストを追加"
    bl_description = "文字種ごとにサイズを変えられる日本語テキスト（カーブ）を3Dカーソル位置に追加"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cu = bpy.data.curves.new("C7KanaText", "CURVE")
        cu.dimensions = "2D"
        cu.fill_mode = "BOTH"
        ob = bpy.data.objects.new("C7KanaText", cu)
        context.collection.objects.link(ob)
        ob.location = context.scene.cursor.location
        for o in context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        st = ob.c7_kana
        st.is_c7 = True
        apply_auto_name(ob, force=True)
        font = _default_font()
        if font is None:
            self.report({"WARNING"}, "日本語フォントを選んでください")
        else:
            st.font = font  # update で rebuild
        rebuild(ob)
        return {"FINISHED"}


class C7KANA_OT_rebuild(bpy.types.Operator):
    bl_idname = "c7kana.rebuild"
    bl_label = "再生成"
    bl_description = "フォントのキャッシュを消して作り直す（フォントを差し替えたときなど）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == "CURVE" and ob.c7_kana.is_c7

    def execute(self, context):
        clear_cache()
        rebuild(context.active_object)
        return {"FINISHED"}


class C7KANA_OT_kern_remove(bpy.types.Operator):
    bl_idname = "c7kana.kern_remove"
    bl_label = "カーニングを削除"
    bl_options = {"REGISTER", "UNDO"}
    index: IntProperty(default=-1)

    def execute(self, context):
        ob = context.active_object
        st = ob.c7_kana
        if self.index < 0:
            st.kernings.clear()
        else:
            i, _ = _kern_find(st, self.index)
            if i >= 0:
                st.kernings.remove(i)
        rebuild(ob)
        return {"FINISHED"}


class C7KANA_OT_kern_jump(bpy.types.Operator):
    bl_idname = "c7kana.kern_jump"
    bl_label = "この位置を選ぶ"
    bl_options = {"INTERNAL"}
    index: IntProperty()

    def execute(self, context):
        context.active_object.c7_kana.kern_cursor = self.index + 1
        return {"FINISHED"}


class C7KANA_OT_char_reset(bpy.types.Operator):
    bl_idname = "c7kana.char_reset"
    bl_label = "1文字の調整をリセット"
    bl_description = "この文字のカーニング・高さ・傾き・サイズを元に戻す（-1で全部）"
    bl_options = {"REGISTER", "UNDO"}
    index: IntProperty(default=-1)

    def execute(self, context):
        ob = context.active_object
        st = ob.c7_kana
        if self.index < 0:
            st.kernings.clear()
            st.char_adjust.clear()
        else:
            i, _ = _kern_find(st, self.index)
            if i >= 0:
                st.kernings.remove(i)
            i, _ = _adj_find(st, self.index)
            if i >= 0:
                st.char_adjust.remove(i)
        rebuild(ob)
        return {"FINISHED"}


def _adjust_summary(st, idx):
    parts = []
    _, k = _kern_find(st, idx)
    if k:
        parts.append(f"字間{k.value:+.2f}")
    _, a = _adj_find(st, idx)
    if a:
        if abs(a.rise) > 1e-6:
            parts.append(f"高さ{a.rise:+.2f}")
        if abs(a.skew) > 1e-6:
            parts.append(f"傾き{math.degrees(a.skew):+.0f}°")
        if abs(a.scale - 100) > 1e-6:
            parts.append(f"{a.scale:.0f}%")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# パネル
# ---------------------------------------------------------------------------
_CHAR_BUTTON_MAX = 60


class C7KANA_PT_main(bpy.types.Panel):
    bl_label = "C7 Text（かなスケール）"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "C7"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        layout.operator("c7kana.add", icon="OUTLINER_OB_FONT")
        ob = context.active_object
        if ob is not None and ob.type == "FONT":
            box = layout.box()
            box.label(text=f"普通のテキスト「{ob.name}」から", icon="OUTLINER_OB_FONT")
            col = box.column(align=True)
            col.operator("c7kana.from_text", text="かなスケールへ送る",
                         icon="FORWARD").mode = "KANA"
            col.operator("c7kana.from_text", text="バラ文字へ送る",
                         icon="MOD_EXPLODE").mode = "SPLIT"
            return
        if not (ob and ob.type == "CURVE" and ob.c7_kana.is_c7):
            layout.label(text="C7テキストを選択すると編集できます", icon="INFO")
            return
        st = ob.c7_kana

        col = layout.column(align=True)
        col.prop(st, "text", text="")
        col.template_ID(st, "font", open="font.open")
        layout.prop(st, "size")

        box = layout.box()
        box.label(text="文字種ごとのサイズ")
        c = box.column(align=True)
        c.prop(st, "scale_hira")
        c.prop(st, "scale_kata")
        c.prop(st, "scale_sym")
        box.prop(st, "align_mode", expand=True)

        box = layout.box()
        box.label(text="上下の微調整")
        c = box.column(align=True)
        c.prop(st, "offset_hira")
        c.prop(st, "offset_kata")
        c.prop(st, "offset_sym")

        box = layout.box()
        box.label(text="組み")
        box.prop(st, "align_x", expand=True)
        c = box.column(align=True)
        c.prop(st, "tracking")
        c.prop(st, "line_spacing")
        c.prop(st, "skew")
        box.prop(st, "use_cat_material")

        self.draw_char_adjust(layout, st)

        layout.operator("c7kana.rebuild", icon="FILE_REFRESH")
        layout.separator()
        layout.operator("c7kana.split", icon="MOD_EXPLODE")

    @staticmethod
    def draw_char_adjust(layout, st):
        box = layout.box()
        box.label(text="1文字ずつの調整", icon="SMALL_CAPS")
        text = _flat_text(st)
        adjusted = {k.index for k in st.kernings} | {a.index for a in st.char_adjust}
        cur = st.kern_cursor - 1

        # 文字ボタン（押すとその文字を選択）
        grid = box.grid_flow(row_major=True, columns=10, even_columns=True, align=True)
        for i, c in enumerate(text[:_CHAR_BUTTON_MAX]):
            if c == "\n":
                op = grid.operator("c7kana.kern_jump", text="↵", emboss=False)
            else:
                label = "␣" if c == " " else c
                if i in adjusted and i != cur:
                    label += "•"
                op = grid.operator("c7kana.kern_jump", text=label, depress=(i == cur))
            op.index = i
        if len(text) > _CHAR_BUTTON_MAX:
            box.label(text=f"（{_CHAR_BUTTON_MAX + 1}文字目以降は番号で選んでください）")

        box.prop(st, "kern_cursor")
        ch = char_at(st, cur)
        if ch is None:
            box.label(text="（改行・範囲外は調整できません）", icon="ERROR")
        else:
            col = box.column(align=True)
            col.label(text=f"「{ch}」を調整")
            col.prop(st, "char_rise")
            col.prop(st, "char_skew")
            col.prop(st, "char_scale")
            label = kern_pair_label(st, cur)
            if label:
                col.prop(st, "kern_value", text="次の文字との間")
            r = box.row()
            r.enabled = cur in adjusted
            r.operator("c7kana.char_reset", text="この文字をリセット",
                       icon="LOOP_BACK").index = cur

        if adjusted:
            col = box.column(align=True)
            col.label(text="調整済みの文字")
            for idx in sorted(adjusted):
                r = col.row(align=True)
                c = char_at(st, idx) or "?"
                op = r.operator("c7kana.kern_jump", text=f"{idx + 1}「{c}」 {_adjust_summary(st, idx)}",
                                emboss=False, depress=(idx == cur))
                op.index = idx
                r.operator("c7kana.char_reset", text="", icon="X").index = idx
            box.operator("c7kana.char_reset", text="1文字の調整を全部リセット",
                         icon="TRASH").index = -1


classes = (C7KernItem, C7CharAdjust, C7KanaSettings, C7KANA_OT_char_reset, C7KANA_OT_add, C7KANA_OT_rebuild,
           C7KANA_OT_kern_remove, C7KANA_OT_kern_jump, C7KANA_PT_main)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Object.c7_kana = PointerProperty(type=C7KanaSettings)


def unregister():
    del bpy.types.Object.c7_kana
    for c in reversed(classes):
        bpy.utils.unregister_class(c)



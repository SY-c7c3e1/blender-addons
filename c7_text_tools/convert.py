# SPDX-License-Identifier: GPL-3.0-or-later
"""C7 Text Tools: 普通のテキストオブジェクト → かなスケール／バラ文字へ送る

- 文字・フォント・サイズ・傾き・行揃え・位置/回転/拡大・親・マテリアル・押し出し/ベベル・
  モディファイア・アウトラインを引き継ぐ
- 元の普通テキスト（とそのフチ）は非表示で残す
"""

import math

import bpy
from bpy.props import EnumProperty
from mathutils import Matrix

from . import kana, outline

_ALIGN = {"LEFT": "LEFT", "CENTER": "CENTER", "RIGHT": "RIGHT"}
_CURVE_ATTRS = ("extrude", "bevel_depth", "bevel_resolution", "bevel_mode", "offset",
                "resolution_u", "use_fill_caps")


def _hide(o):
    if o is None:
        return
    o.hide_render = True
    try:
        o.hide_set(True)
    except RuntimeError:
        o.hide_viewport = True


def _line_pitch(font, space_line):
    """普通のテキスト（サイズ1）での行送りの実測値。"""
    def low_y(body):
        cu = bpy.data.curves.new("_c7pitch", "FONT")
        cu.font = font
        cu.body = body
        cu.size = 1.0
        cu.space_line = space_line
        ob = bpy.data.objects.new("_c7pitch", cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        c = ev.to_curve(dg)
        ys = [p.co.y for sp in c.splines for p in sp.bezier_points] + \
             [p.co.y for sp in c.splines for p in sp.points]
        ev.to_curve_clear()
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
        return min(ys) if ys else 0.0
    return low_y("H") - low_y("H\nH")


def _font_min(tc, neutral):
    """テキストの文字の輪郭の左下（ローカル座標）。neutral=True なら位置ずらし・上下揃えを無効にして測る。"""
    cu = tc.copy()
    if neutral:
        cu.offset_x = 0.0
        cu.offset_y = 0.0
        cu.align_y = "TOP_BASELINE"
    ob = bpy.data.objects.new("_c7min", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    c = ev.to_curve(dg)
    xs, ys = [], []
    for sp in c.splines:
        for p in sp.bezier_points:
            xs.append(p.co.x); ys.append(p.co.y)
        for p in sp.points:
            xs.append(p.co.x); ys.append(p.co.y)
    ev.to_curve_clear()
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return (min(xs), min(ys)) if xs else (0.0, 0.0)


def _font_shift(tc):
    """原点移動（オフセット）や上下揃えによる、文字のずれ量。"""
    try:
        ax, ay = _font_min(tc, False)
        bx, by = _font_min(tc, True)
        return ax - bx, ay - by
    except Exception:
        return 0.0, 0.0


def font_to_kana(context, src):
    """普通のテキスト src から、かなスケールのオブジェクトを作って返す。"""
    tc = src.data
    from .names import text_name
    nm = text_name(tc.body, "_kana")
    cu = bpy.data.curves.new(nm, "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    for a in _CURVE_ATTRS:
        try:
            setattr(cu, a, getattr(tc, a))
        except Exception:
            pass
    for m in tc.materials:
        cu.materials.append(m)

    ob = bpy.data.objects.new(nm, cu)
    for col in (src.users_collection or [context.scene.collection]):
        col.objects.link(ob)
    ob.parent = src.parent
    ob.parent_type = src.parent_type
    ob.matrix_parent_inverse = src.matrix_parent_inverse.copy()
    ob.location = src.location
    ob.rotation_mode = src.rotation_mode
    ob.rotation_euler = src.rotation_euler
    ob.rotation_quaternion = src.rotation_quaternion
    ob.scale = src.scale
    # 原点を動かしたテキスト（オフセット）や上下揃えのずれを、位置で補正
    dx, dy = _font_shift(tc)
    if abs(dx) > 1e-7 or abs(dy) > 1e-7:
        ob.matrix_basis = ob.matrix_basis @ Matrix.Translation((dx, dy, 0.0))

    st = ob.c7_kana
    st.is_c7 = True
    st.auto_name = nm
    # 値を入れるたびに作り直さないよう、フォントは最後に入れる
    st.text = tc.body.replace("\n", "\\n")
    st.size = tc.size
    st.align_x = _ALIGN.get(tc.align_x, "LEFT")
    st.skew = math.atan(tc.shear)
    font = tc.font if tc.font is not None else kana._default_font()
    try:
        em = kana.metrics(font)["em"] or 1.0
        st.line_spacing = max(0.1, _line_pitch(font, tc.space_line) / em)
    except Exception:
        st.line_spacing = 1.2 * tc.space_line
    st.font = font
    kana.rebuild(ob)

    outline._copy_modifiers(src, ob)

    # アウトラインを引き継ぐ
    so = src.c7_outline
    if so.target is not None:
        dst = ob.c7_outline
        dst.width = so.width
        dst.color = so.color
        dst.depth = so.depth
        dcu = bpy.data.curves.new(ob.name + "_outline", "CURVE")
        out = bpy.data.objects.new(ob.name + "_outline", dcu)
        for col in ob.users_collection:
            col.objects.link(out)
        out.c7_outline.is_outline = True
        out.c7_outline.source = ob
        dst.target = out
        outline.sync(ob, force=True)
        _hide(so.target)

    _hide(src)
    for o in context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    return ob


class C7KANA_OT_from_text(bpy.types.Operator):
    bl_idname = "c7kana.from_text"
    bl_label = "普通のテキストから送る"
    bl_description = "普通のテキストを、かなスケール（またはバラ文字）に変換する。元のテキストは非表示で残る"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(items=[("KANA", "かなスケールへ送る", ""),
                              ("SPLIT", "バラ文字へ送る", "")], default="KANA",
                       options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, props):
        if props.mode == "SPLIT":
            return "かなスケールに変換して、そのまま1文字ずつバラす。元のテキストは非表示で残る"
        return "文字・フォント・サイズ・位置・マテリアルなどを引き継いで、かなスケールに変換する。" \
               "元のテキストは非表示で残る"

    @classmethod
    def poll(cls, context):
        o = context.active_object
        return o is not None and o.type == "FONT"

    def execute(self, context):
        src = context.active_object
        if src.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if not src.data.body.strip():
            self.report({"WARNING"}, "文字が空です")
            return {"CANCELLED"}
        ob = font_to_kana(context, src)
        if self.mode == "SPLIT":
            bpy.ops.c7kana.split()
        else:
            self.report({"INFO"}, f"かなスケール「{ob.name}」に変換しました（元のテキストは非表示）")
        return {"FINISHED"}


classes = (C7KANA_OT_from_text,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

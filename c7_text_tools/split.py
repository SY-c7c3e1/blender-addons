# SPDX-License-Identifier: GPL-3.0-or-later
"""C7 Text Tools: かなスケールのテキストを1文字ずつのオブジェクトにバラす

- 元テキストは非表示で残す（直して再度バラせる）
- 新しいコレクション「<元の名前>_split」に、まとめ用エンプティ＋1文字ずつのカーブ
- エンプティは文字全体の中心（向き・拡大は元テキストと同じ）、各文字の原点は文字の中心
- 元テキストにアウトラインがあれば、各文字にも線だけのフチを子として付ける
"""

import bpy
from mathutils import Matrix

from . import kana, outline

_CURVE_ATTRS = ("dimensions", "fill_mode", "extrude", "bevel_depth", "bevel_resolution",
                "bevel_mode", "offset", "resolution_u", "use_fill_caps", "twist_mode")


def _copy_curve_settings(src_cu, dst_cu):
    for a in _CURVE_ATTRS:
        if hasattr(src_cu, a):
            try:
                setattr(dst_cu, a, getattr(src_cu, a))
            except Exception:
                pass
    for m in src_cu.materials:
        dst_cu.materials.append(m)


def _make_char_outline(src, char_ob, name, coll):
    st = src.c7_outline
    cu = char_ob.data.copy()
    cu.name = name
    cu.dimensions = "3D"
    cu.fill_mode = "FULL"
    cu.extrude = 0.0
    cu.bevel_depth = 0.0
    cu.offset = 0.0
    cu.materials.clear()
    mat = outline._get_material(src)
    cu.materials.append(mat)
    for sp in cu.splines:
        sp.material_index = 0
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    ob.parent = char_ob
    ob.location = (0.0, 0.0, -st.depth)
    ng = outline._stroke_group()
    gm = ob.modifiers.new(outline.GN_MOD, "NODES")
    gm.node_group = ng
    outline._set_input(gm, ng, "Radius", st.width * src.c7_kana.size * 0.5)
    outline._set_input(gm, ng, "Material", mat)
    return ob


def _copy_mods_after(src, dst):
    """dst の既存モディファイア（線のノード）の後ろに、src のモディファイアを足す。"""
    for m in src.modifiers:
        try:
            n = dst.modifiers.new(m.name, m.type)
        except Exception:
            continue
        for k, v in outline._mod_props(m):
            try:
                setattr(n, k, v)
            except Exception:
                pass


class C7KANA_OT_split(bpy.types.Operator):
    bl_idname = "c7kana.split"
    bl_label = "1文字ずつバラす"
    bl_description = ("文字を1文字ずつのオブジェクトに分けて、エンプティの子として新しいコレクションに置く。"
                      "元のテキストは非表示で残る")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return kana_ok(ob)

    def execute(self, context):
        src = context.active_object
        st = src.c7_kana
        placed = [p for p in kana.layout(st) if not p[0].isspace()]
        if not placed:
            self.report({"WARNING"}, "バラす文字がありません")
            return {"CANCELLED"}

        # コレクション（元テキストと同じ場所に作る）
        parent_coll = src.users_collection[0] if src.users_collection else context.scene.collection
        from .names import text_name
        split_name = text_name(st.text, "_split")
        base = split_name[:-len("_split")]
        coll = bpy.data.collections.new(split_name)
        parent_coll.children.link(coll)

        # 各文字の範囲と、全体の中心（元テキストのローカル座標）
        items = []
        for c, cat, cs, px, py, sh in placed:
            b = kana.char_bounds(st.font, c, cs, px, py, sh)
            if b is not None:
                items.append((c, cat, cs, px, py, sh, b))
        if not items:
            self.report({"WARNING"}, "バラす文字がありません")
            return {"CANCELLED"}
        gx = (min(i[6][0] for i in items) + max(i[6][2] for i in items)) / 2.0
        gy = (min(i[6][1] for i in items) + max(i[6][3] for i in items)) / 2.0

        # まとめ用エンプティ：文字全体の中心。向き・拡大は元テキストと同じ
        empty = bpy.data.objects.new(split_name, None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = max(0.2, st.size * 0.5)
        coll.objects.link(empty)
        empty.matrix_world = src.matrix_world @ Matrix.Translation((gx, gy, 0.0))

        has_outline = src.c7_outline.target is not None
        n = 0
        for c, cat, cs, px, py, sh, b in items:
            cx, cy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
            n += 1
            name = text_name(base, f"_{n:02d}_{c}")
            cu = bpy.data.curves.new(name, "CURVE")
            _copy_curve_settings(src.data, cu)
            mat = cat if st.use_cat_material else 0
            kana.emit_char(cu, st.font, c, cs, px, py, sh, mat, cx, cy)
            ob = bpy.data.objects.new(name, cu)
            coll.objects.link(ob)
            ob.parent = empty
            ob.location = (cx - gx, cy - gy, 0.0)
            ob["c7_char"] = c
            ob["c7_char_index"] = n
            outline._copy_modifiers(src, ob)  # パス沿いなどはそのまま
            if has_outline:
                o2 = _make_char_outline(src, ob, name + "_outline", coll)
                _copy_mods_after(src, o2)

        # 元テキスト（とフチ）は非表示で残す
        for o in (src, src.c7_outline.target):
            if o is None:
                continue
            o.hide_render = True
            try:
                o.hide_set(True)
            except RuntimeError:
                o.hide_viewport = True

        for o in context.selected_objects:
            o.select_set(False)
        empty.select_set(True)
        context.view_layer.objects.active = empty
        self.report({"INFO"}, f"{n} 文字にバラしました（元のテキストは非表示で残しています）")
        return {"FINISHED"}


def kana_ok(ob):
    return ob is not None and ob.type == "CURVE" and ob.c7_kana.is_c7 \
        and ob.c7_kana.font is not None and bool(ob.c7_kana.text)


classes = (C7KANA_OT_split,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

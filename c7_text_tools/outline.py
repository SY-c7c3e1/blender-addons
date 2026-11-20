# SPDX-License-Identifier: GPL-3.0-or-later
"""C7 Text Tools: アウトライン（フチ）

テキスト（かなスケール／通常のテキストオブジェクト）にフチだけの別オブジェクトを付ける。
- フチは元テキストの子。元の文字・フォント・モディファイアの変更に自動で追従
- 太さ・色・奥行きのずらしをパネルで調整
"""

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, FloatProperty, FloatVectorProperty, PointerProperty

_last_sig = {}  # outline object pointer -> signature


# ------------------------------------------------------------------ helpers

def is_kana(o):
    return o is not None and o.type == "CURVE" and o.c7_kana.is_c7


def is_text(o):
    return o is not None and (o.type == "FONT" or is_kana(o))


def outline_source(o):
    """o がフチならその元テキスト、テキストならそれ自身を返す。"""
    if o is None:
        return None
    if o.c7_outline.is_outline:
        return o.c7_outline.source
    return o if is_text(o) else None


def _char_size(src):
    return src.c7_kana.size if is_kana(src) else src.data.size


def _font_sig(cu):
    keys = ("body", "size", "shear", "space_character", "space_word", "space_line",
            "align_x", "align_y", "offset_x", "offset_y", "extrude", "bevel_depth",
            "bevel_resolution", "resolution_u", "fill_mode", "small_caps_scale",
            "use_fast_edit")
    sig = [getattr(cu, k, None) for k in keys]
    for k in ("font", "font_bold", "font_italic", "font_bold_italic", "follow_curve"):
        v = getattr(cu, k, None)
        sig.append(v.name if v else None)
    sig.append(tuple((tb.x, tb.y, tb.width, tb.height) for tb in cu.text_boxes))
    return tuple(sig)


_SKIP_MOD_PROPS = {"rna_type", "name", "type", "is_override_data", "persistent_uid",
                   "is_active", "is_override_data_editable", "execution_time"}


def _mod_props(m):
    out = []
    for p in m.bl_rna.properties:
        if p.identifier in _SKIP_MOD_PROPS or p.is_readonly:
            continue
        if p.type == "COLLECTION":
            continue
        try:
            v = getattr(m, p.identifier)
        except Exception:
            continue
        if p.type in {"FLOAT", "INT", "BOOLEAN"} and getattr(p, "array_length", 0):
            v = tuple(v)
        out.append((p.identifier, v))
    return out


def _mods_sig(o):
    sig = []
    for m in o.modifiers:
        props = []
        for k, v in _mod_props(m):
            props.append((k, v.name if isinstance(v, bpy.types.ID) else v))
        sig.append((m.name, m.type, tuple(props)))
    return tuple(sig)


def _copy_modifiers(src, dst):
    dst.modifiers.clear()
    for m in src.modifiers:
        try:
            n = dst.modifiers.new(m.name, m.type)
        except Exception:
            continue
        for k, v in _mod_props(m):
            try:
                setattr(n, k, v)
            except Exception:
                pass


def _get_material(src):
    st = src.c7_outline
    name = "C7_Outline_" + src.name
    mat = st.material
    if mat is None:
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        st.material = mat
    col = tuple(st.color)
    mat.diffuse_color = col
    try:
        if not mat.use_nodes:
            mat.use_nodes = True
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf:
            bsdf.inputs["Base Color"].default_value = col
    except Exception:
        pass
    return mat


# ------------------------------------------------------------------ geometry nodes (かなスケール用)

GN_NAME = "C7_OutlineLine"
GN_MOD = "C7 Outline"


def _stroke_group():
    """輪郭に沿った線だけを作るノード（円形プロファイルを平たく潰した帯・塗りなし）。"""
    ng = bpy.data.node_groups.get(GN_NAME)
    if ng is not None:
        return ng
    ng = bpy.data.node_groups.new(GN_NAME, "GeometryNodeTree")
    itf = ng.interface
    itf.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    s_r = itf.new_socket("Radius", in_out="INPUT", socket_type="NodeSocketFloat")
    s_r.default_value = 0.02
    s_r.min_value = 0.0
    itf.new_socket("Material", in_out="INPUT", socket_type="NodeSocketMaterial")
    itf.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi = N.new("NodeGroupInput"); gi.location = (-800, 0)
    go = N.new("NodeGroupOutput"); go.location = (600, 0)
    circ = N.new("GeometryNodeCurvePrimitiveCircle"); circ.location = (-600, -250)
    circ.inputs["Resolution"].default_value = 12
    c2m = N.new("GeometryNodeCurveToMesh"); c2m.location = (-400, 0)
    pos = N.new("GeometryNodeInputPosition"); pos.location = (-400, -250)
    mul = N.new("ShaderNodeVectorMath"); mul.operation = "MULTIPLY"; mul.location = (-200, -250)
    mul.inputs[1].default_value = (1.0, 1.0, 0.0)
    setp = N.new("GeometryNodeSetPosition"); setp.location = (0, 0)
    setm = N.new("GeometryNodeSetMaterial"); setm.location = (300, 0)
    L.new(gi.outputs[0], c2m.inputs["Curve"])
    L.new(gi.outputs["Radius"], circ.inputs["Radius"])
    L.new(circ.outputs["Curve"], c2m.inputs["Profile Curve"])
    L.new(c2m.outputs["Mesh"], setp.inputs["Geometry"])
    L.new(pos.outputs["Position"], mul.inputs[0])
    L.new(mul.outputs["Vector"], setp.inputs["Position"])
    L.new(setp.outputs["Geometry"], setm.inputs["Geometry"])
    L.new(gi.outputs["Material"], setm.inputs["Material"])
    L.new(setm.outputs["Geometry"], go.inputs[0])
    return ng


def _socket_id(ng, name):
    for it in ng.interface.items_tree:
        if getattr(it, "in_out", None) == "INPUT" and it.name == name:
            return it.identifier
    return name


def _set_input(mod, ng, name, value):
    """ジオメトリノード入力の値を設定（5.x の properties.inputs と旧方式の両対応）。"""
    sid = _socket_id(ng, name)
    props = getattr(mod, "properties", None)
    if props is not None and hasattr(props, "inputs"):
        getattr(props.inputs, sid).value = value
    else:
        mod[sid] = value


# ------------------------------------------------------------------ sync

def sync(src, force=False):
    """元テキスト src のフチを作り直す（変化がなければ何もしない）。"""
    st = src.c7_outline
    out = st.target
    if out is None:
        return
    if out.name not in bpy.data.objects:
        st.target = None
        return
    data_sig = ("KANA",) if is_kana(src) else _font_sig(src.data)
    sig = (data_sig, _mods_sig(src), round(st.width, 6), round(st.depth, 6),
           tuple(round(c, 4) for c in st.color), round(_char_size(src), 6))
    key = out.as_pointer()
    if not force and _last_sig.get(key) == sig:
        return
    _last_sig[key] = sig

    # フチは常に「線だけ」のカーブオブジェクト（古い版の FONT 型フチは作り直す）
    if out.type != "CURVE":
        out = _replace_with_curve_object(src, out)

    old = out.data
    if is_kana(src):
        new = src.data.copy()
    else:
        new = _font_to_curve(src)
    new.name = out.name
    # ノードに輪郭（カーブ）のまま渡すため、塗り・押し出しを切る
    new.dimensions = "3D"
    new.fill_mode = "FULL"
    new.extrude = 0.0
    new.bevel_depth = 0.0
    new.offset = 0.0
    new.materials.clear()
    new.materials.append(_get_material(src))
    for sp in new.splines:
        sp.material_index = 0
    out.data = new
    if old is not None and old.users == 0 and isinstance(old, bpy.types.Curve):
        bpy.data.curves.remove(old)

    # 位置：元の子・少し奥へ
    if out.parent != src:
        out.parent = src
    out.matrix_parent_inverse.identity()
    out.location = (0.0, 0.0, -st.depth)
    out.rotation_euler = (0.0, 0.0, 0.0)
    out.scale = (1.0, 1.0, 1.0)

    # 線にするノードを先頭に → その後に元のモディファイア（パス変形など）
    _copy_modifiers(src, out)
    ng = _stroke_group()
    gm = out.modifiers.new(GN_MOD, "NODES")
    gm.node_group = ng
    _set_input(gm, ng, "Radius", st.width * _char_size(src) * 0.5)
    _set_input(gm, ng, "Material", new.materials[0])
    idx = len(out.modifiers) - 1
    if idx > 0:
        out.modifiers.move(idx, 0)


def _font_to_curve(src):
    """テキストオブジェクトの文字の輪郭を、通常のカーブデータとして取り出す。"""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = src.evaluated_get(dg)
    tmp = ev.to_curve(dg, apply_modifiers=False)
    cu = bpy.data.curves.new("_c7outline", "CURVE")
    for sp in tmp.splines:
        n = cu.splines.new(sp.type)
        if sp.type == "BEZIER":
            n.bezier_points.add(len(sp.bezier_points) - 1)
            for a, b in zip(sp.bezier_points, n.bezier_points):
                b.co = a.co
                b.handle_left_type = a.handle_left_type
                b.handle_right_type = a.handle_right_type
                b.handle_left = a.handle_left
                b.handle_right = a.handle_right
        else:
            n.points.add(len(sp.points) - 1)
            for a, b in zip(sp.points, n.points):
                b.co = a.co
        n.use_cyclic_u = sp.use_cyclic_u
        n.resolution_u = sp.resolution_u
    cu.resolution_u = src.data.resolution_u
    ev.to_curve_clear()
    return cu


def _replace_with_curve_object(src, old_out):
    cu = bpy.data.curves.new(old_out.name, "CURVE")
    out = bpy.data.objects.new(old_out.name, cu)
    for col in (old_out.users_collection or src.users_collection):
        col.objects.link(out)
    out.c7_outline.is_outline = True
    out.c7_outline.source = src
    _last_sig.pop(old_out.as_pointer(), None)
    old_data = old_out.data
    bpy.data.objects.remove(old_out)
    if old_data is not None and old_data.users == 0:
        bpy.data.curves.remove(old_data)
    out.name = src.name + "_outline"
    src.c7_outline.target = out
    return out


def sync_all(force=False):
    srcs = [o for o in bpy.data.objects
            if o.c7_outline.target is not None and not o.c7_outline.is_outline and is_text(o)]
    for o in srcs:
        if True:
            try:
                sync(o, force)
            except Exception as e:
                print("[C7 Text Tools] outline sync failed:", o.name, e)


@persistent
def _on_depsgraph(scene, depsgraph):
    sync_all()


@persistent
def _on_load(_dummy):
    _last_sig.clear()
    sync_all(force=True)


# ------------------------------------------------------------------ props

def _on_setting(self, context):
    src = self.id_data
    if isinstance(src, bpy.types.Object) and is_text(src):
        sync(src, force=True)


class C7OutlineSettings(bpy.types.PropertyGroup):
    target: PointerProperty(type=bpy.types.Object, name="フチのオブジェクト")
    material: PointerProperty(type=bpy.types.Material)
    is_outline: BoolProperty(default=False, options={"HIDDEN"})
    source: PointerProperty(type=bpy.types.Object, name="元テキスト")
    width: FloatProperty(name="線の太さ", default=0.02, min=0.0, soft_max=0.2, step=0.1,
                         description="線の太さ（文字サイズに対する割合、0.1＝文字サイズの10%）。線は輪郭の真ん中に乗る",
                         update=_on_setting)
    color: FloatVectorProperty(name="色", subtype="COLOR", size=4, min=0, max=1,
                               default=(0.05, 0.05, 0.08, 1.0), update=_on_setting)
    depth: FloatProperty(name="奥へずらす", default=0.002, min=0.0, soft_max=0.1, step=0.01,
                         unit="LENGTH", description="フチを文字の後ろに置く距離",
                         update=_on_setting)


# ------------------------------------------------------------------ operators

class C7OUT_OT_add(bpy.types.Operator):
    bl_idname = "c7text.outline_add"
    bl_label = "アウトラインを追加"
    bl_description = "選択中のテキストに、輪郭の線だけのオブジェクト（塗りなし）を付ける"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(is_text(o) and o.c7_outline.target is None
                   for o in context.selected_objects + [context.active_object] if o)

    def execute(self, context):
        targets = {o for o in context.selected_objects if is_text(o)}
        if is_text(context.active_object):
            targets.add(context.active_object)
        n = 0
        for src in targets:
            if src.c7_outline.target is not None:
                continue
            cu = bpy.data.curves.new(src.name + "_outline", "CURVE")
            out = bpy.data.objects.new(src.name + "_outline", cu)
            for col in src.users_collection:
                col.objects.link(out)
            out.c7_outline.is_outline = True
            out.c7_outline.source = src
            out.hide_select = False
            src.c7_outline.target = out
            sync(src, force=True)
            n += 1
        self.report({"INFO"}, f"{n} 個にアウトラインを追加")
        return {"FINISHED"}


class C7OUT_OT_remove(bpy.types.Operator):
    bl_idname = "c7text.outline_remove"
    bl_label = "アウトラインを削除"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        src = outline_source(context.active_object)
        return src is not None and src.c7_outline.target is not None

    def execute(self, context):
        src = outline_source(context.active_object)
        out = src.c7_outline.target
        src.c7_outline.target = None
        _last_sig.pop(out.as_pointer(), None)
        data = out.data
        bpy.data.objects.remove(out)
        if data is not None and data.users == 0:
            bpy.data.curves.remove(data)
        context.view_layer.objects.active = src
        src.select_set(True)
        return {"FINISHED"}


class C7OUT_OT_select_source(bpy.types.Operator):
    bl_idname = "c7text.outline_select_source"
    bl_label = "元テキストを選択"
    bl_options = {"INTERNAL", "UNDO"}

    def execute(self, context):
        src = outline_source(context.active_object)
        if src:
            for o in context.selected_objects:
                o.select_set(False)
            src.select_set(True)
            context.view_layer.objects.active = src
        return {"FINISHED"}


# ------------------------------------------------------------------ panel

class C7OUT_PT_main(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "C7"
    bl_label = "C7 アウトライン"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        ao = context.active_object
        src = outline_source(ao)
        if src is None:
            layout.label(text="テキストを選択してください", icon="INFO")
            return
        if ao is not src:
            layout.operator(C7OUT_OT_select_source.bl_idname, text=f"元テキスト: {src.name}",
                            icon="OUTLINER_OB_FONT")
        st = src.c7_outline
        if st.target is None:
            layout.operator(C7OUT_OT_add.bl_idname, icon="MOD_SKIN")
            return
        col = layout.column(align=True)
        col.prop(st, "width")
        col.prop(st, "color")
        col.prop(st, "depth")
        layout.label(text=f"フチ: {st.target.name}", icon="OBJECT_DATA")
        layout.operator(C7OUT_OT_remove.bl_idname, icon="X")


classes = (C7OutlineSettings, C7OUT_OT_add, C7OUT_OT_remove, C7OUT_OT_select_source,
           C7OUT_PT_main)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Object.c7_outline = PointerProperty(type=C7OutlineSettings)
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    bpy.app.handlers.load_post.append(_on_load)


def unregister():
    for lst, fn in ((bpy.app.handlers.depsgraph_update_post, _on_depsgraph),
                    (bpy.app.handlers.load_post, _on_load)):
        if fn in lst:
            lst.remove(fn)
    del bpy.types.Object.c7_outline
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

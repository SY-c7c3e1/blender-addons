bl_info = {
    "name": "C7 Render Folder",
    "author": "Yumi",
    "version": (1, 1, 0),
    "blender": (4, 2, 0),
    "location": "Properties > Output > C7 Render Folder",
    "description": "連番書き出し時に「保存先/名前/名前_####」を自動設定",
    "category": "Render",
}

import bpy
import re


# ---------- ユーティリティ ----------

INVALID_CHARS = r'[\\/:*?"<>|{}]'  # Windowsで使えない文字 + パステンプレートの{}


def sanitize(name: str) -> str:
    name = re.sub(INVALID_CHARS, "_", name).strip().strip("_")
    return name


def get_active_collection_name(context):
    view_layer = getattr(context, "view_layer", None) or context.scene.view_layers[0]
    alc = view_layer.active_layer_collection
    if alc is None:
        return ""
    return alc.collection.name


def get_output_name(context):
    props = context.scene.c7rf_props
    if props.name_mode == "COLLECTION":
        raw = get_active_collection_name(context)
    else:
        raw = props.custom_name
    return sanitize(raw)


def build_output_path(context):
    props = context.scene.c7rf_props
    base = props.base_dir.rstrip("/\\")
    name = get_output_name(context)
    if not base or not name:
        return None
    return f"{base}/{name}/{name}_####"


def apply_path(context):
    path = build_output_path(context)
    if path is None:
        return False
    context.scene.render.filepath = path
    return True


# ---------- プロパティ ----------

class C7RF_Props(bpy.types.PropertyGroup):
    base_dir: bpy.props.StringProperty(
        name="保存先",
        description="この中に「名前」フォルダが作られます",
        subtype="DIR_PATH",
        options={"PATH_SUPPORTS_BLEND_RELATIVE"},
        default="//render/",
    )
    name_mode: bpy.props.EnumProperty(
        name="名前",
        items=[
            ("CUSTOM", "任意", "名前を手入力"),
            ("COLLECTION", "選択中のコレクション", "アウトライナーでアクティブなコレクション名を使う"),
        ],
        default="CUSTOM",
    )
    custom_name: bpy.props.StringProperty(
        name="名前",
        default="",
    )


# ---------- オペレーター ----------

class C7RF_OT_apply(bpy.types.Operator):
    bl_idname = "c7rf.apply_path"
    bl_label = "出力パスに適用"
    bl_description = "保存先/名前/名前_#### を出力パスに設定"

    def execute(self, context):
        if not apply_path(context):
            self.report({"WARNING"}, "保存先と名前を設定してください")
            return {"CANCELLED"}
        self.report({"INFO"}, f"出力パス: {context.scene.render.filepath}")
        return {"FINISHED"}


class C7RF_OT_render(bpy.types.Operator):
    bl_idname = "c7rf.render_animation"
    bl_label = "適用して連番レンダリング"
    bl_description = "出力パスを設定してからアニメーションをレンダリング"

    def execute(self, context):
        if not apply_path(context):
            self.report({"WARNING"}, "保存先と名前を設定してください")
            return {"CANCELLED"}
        bpy.ops.render.render("INVOKE_DEFAULT", animation=True)
        return {"FINISHED"}


# ---------- パネル ----------

class C7RF_PT_panel(bpy.types.Panel):
    bl_label = "C7 Render Folder"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "output"

    def draw(self, context):
        layout = self.layout
        props = context.scene.c7rf_props

        layout.prop(props, "base_dir")
        layout.prop(props, "name_mode", expand=True)

        if props.name_mode == "CUSTOM":
            layout.prop(props, "custom_name", text="名前")
        else:
            row = layout.row()
            row.enabled = False
            row.label(text=f"コレクション: {get_active_collection_name(context) or '(なし)'}",
                      icon="OUTLINER_COLLECTION")

        # プレビュー
        path = build_output_path(context)
        box = layout.box()
        if path:
            box.label(text=path.replace("####", "0001") + context.scene.render.file_extension,
                      icon="FILE_FOLDER")
        else:
            box.label(text="保存先と名前を設定してください", icon="ERROR")

        col = layout.column(align=True)
        col.operator("c7rf.apply_path", icon="CHECKMARK")
        col.operator("c7rf.render_animation", icon="RENDER_ANIMATION")


# ---------- 登録 ----------

classes = (C7RF_Props, C7RF_OT_apply, C7RF_OT_render, C7RF_PT_panel)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.c7rf_props = bpy.props.PointerProperty(type=C7RF_Props)


def unregister():
    del bpy.types.Scene.c7rf_props
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()

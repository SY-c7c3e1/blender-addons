bl_info = {
    "name": "C7 Color Clip",
    "author": "Yumi",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "3D View / Shader Editor > N Panel > Color Clip",
    "description": "案件ごとのカラーパレットからマテリアルへ色をコピペ・適用",
    "category": "Material",
}

import bpy
import json
import os
import re
import shutil
from bpy.app.handlers import persistent
from bpy.props import (StringProperty, FloatVectorProperty, CollectionProperty,
                       IntProperty, EnumProperty, BoolProperty)
from bpy.types import Operator, Panel, PropertyGroup
from bpy_extras.io_utils import ImportHelper

DATA_DIR = os.path.join(os.path.expanduser("~"), "BlenderColorClip")
DATA_PATH = os.path.join(DATA_DIR, "palettes.json")

POLL_INTERVAL = 2.0      # 他の Blender による変更の確認間隔（秒）
SAVE_DELAY = 0.5         # 色見本ドラッグ中の保存を間引く待ち時間（秒）

_DATA = {"active": "", "palettes": {}}
_mtime = None            # 最後に読み書きしたときのファイル更新時刻
_pending = {}            # (パレット名, 色index, サブindex) -> {"name", "hex"} 未保存の編集
_expanded = set()        # 開いている色 (パレット名, 色の名前)。Blenderごと・保存しない
_enum_cache = []
_suppress = False

# ------------------------------------------------------------
# 色変換
# ------------------------------------------------------------
HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def normalize_hex(s):
    if not s or not isinstance(s, str):
        return None
    s = s.strip().replace("＃", "#").replace(" ", "")
    m = HEX_RE.match(s)
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h.upper()


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def hex_to_linear(h):
    h = normalize_hex(h) or "#FFFFFF"
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), 1.0)


def linear_to_hex(col):
    return "#{:02X}{:02X}{:02X}".format(
        *(int(round(linear_to_srgb(c) * 255)) for c in col[:3]))

# ------------------------------------------------------------
# データ保存 / 読み込み
# ------------------------------------------------------------
def _file_mtime():
    try:
        return os.stat(DATA_PATH).st_mtime_ns
    except OSError:
        return None


def _clean_swatches(sws, allow_children):
    """色のリストを整える。戻り値: (整形後リスト, 不正な項目を捨てたか)"""
    dropped = False
    clean = []
    for sw in sws:
        h = normalize_hex(sw.get("hex")) if isinstance(sw, dict) else None
        if not h:
            dropped = True
            continue
        item = dict(sw)
        item["name"] = str(sw.get("name", ""))
        item["hex"] = h
        if "children" in item:
            ch = item["children"]
            if allow_children and isinstance(ch, list):
                item["children"], bad = _clean_swatches(ch, allow_children=False)
                dropped = dropped or bad
            else:
                del item["children"]
                dropped = True
        clean.append(item)
    return clean, dropped


def sanitize(d):
    """読み込んだ JSON を安全な形に整える。構造が根本的に違えば None。
    未知のキー（AE 側などで追加される想定）はそのまま残す。
    戻り値: (整形後データ, 不正な項目を捨てたか)"""
    if not isinstance(d, dict) or not isinstance(d.get("palettes"), dict):
        return None, True
    dropped = False
    pals = {}
    for pname, sws in d["palettes"].items():
        if not isinstance(sws, list):
            sws, dropped = [], True
        clean, bad = _clean_swatches(sws, allow_children=True)
        dropped = dropped or bad
        pals[str(pname)] = clean
    out = dict(d)
    out["palettes"] = pals
    if out.get("active") not in pals:
        out["active"] = next(iter(pals), "")
    return out, dropped


def save_data():
    """一時ファイルに書いてから置き換える（書き込み途中で落ちても壊れない）"""
    global _mtime
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DATA_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_DATA, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, DATA_PATH)
    _mtime = _file_mtime()


def _default_data():
    return {"active": "", "palettes": {}}


def load_data(keep_active=False):
    """keep_active=True のときは、このBlenderで表示中のパレットを維持する
    （別のBlenderでパレットを切り替えても、こちらの表示は変わらない）"""
    global _DATA, _mtime
    prev_active = _DATA.get("active")
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, encoding="utf-8") as f:
                raw = json.load(f)
            d, dropped = sanitize(raw)
            if d is None:
                raise ValueError("palettes が見つかりません")
            if dropped:
                print("[C7 Color Clip] 不正な項目を除外しました。元ファイルは .bak に保存します")
                try:
                    shutil.copy2(DATA_PATH, DATA_PATH + ".bak")
                except OSError:
                    pass
            _DATA = d
            _mtime = _file_mtime()
            if keep_active and prev_active in _DATA["palettes"]:
                _DATA["active"] = prev_active
            return
        except Exception as e:
            print("[C7 Color Clip] 読み込みエラー。.bak に退避して初期化します:", e)
            try:
                os.replace(DATA_PATH, DATA_PATH + ".bak")
            except OSError:
                pass
    _DATA = _default_data()
    save_data()


def sync_from_disk():
    """他のBlenderがファイルを書き換えていたら読み直す。読み直したら True"""
    if _file_mtime() == _mtime:
        return False
    load_data(keep_active=True)
    return True


def flush_pending():
    """色見本・名前の未保存の編集を、最新のファイルに重ねて保存"""
    global _pending
    if not _pending:
        return
    edits, _pending = _pending, {}
    sync_from_disk()
    for (pal, si, ci), val in edits.items():
        e = get_entry(_DATA["palettes"].get(pal, []), si, ci)
        if e is not None:
            e.update(val)
    save_data()


def commit(fn):
    """最新のファイルを読み直してから fn で変更し、保存・UI更新"""
    flush_pending()
    sync_from_disk()
    result = fn()
    save_data()
    refresh_items()
    return result


def palette_names():
    return list(_DATA["palettes"].keys())


def active_swatches():
    pals = _DATA["palettes"]
    if _DATA.get("active") not in pals:
        _DATA["active"] = next(iter(pals), "")
    return pals.get(_DATA["active"], [])


def get_entry(sws, si, ci=-1):
    """色（ci=-1）またはサブカラーの dict を返す。無ければ None"""
    if not (0 <= si < len(sws)):
        return None
    if ci < 0:
        return sws[si]
    ch = sws[si].get("children") or []
    return ch[ci] if 0 <= ci < len(ch) else None


def ensure_palette():
    if not _DATA["palettes"]:
        _DATA["palettes"]["新規パレット"] = []
        _DATA["active"] = "新規パレット"


def _tag_redraw():
    wm = bpy.context.window_manager
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type in {"VIEW_3D", "NODE_EDITOR"}:
                area.tag_redraw()


def refresh_items():
    """JSON の内容を UI 用コレクションに反映"""
    global _suppress
    wm = bpy.context.window_manager
    if wm is None:
        return
    _suppress = True
    try:
        wm.cclip_items.clear()
        for si, sw in enumerate(active_swatches()):
            entries = [(-1, sw)] + list(enumerate(sw.get("children") or []))
            for ci, e in entries:
                it = wm.cclip_items.add()
                it.si, it.ci = si, ci
                it.name = e.get("name", "")
                it.color = hex_to_linear(e.get("hex", "#FFFFFF"))
    finally:
        _suppress = False
    _tag_redraw()

# ------------------------------------------------------------
# タイマー
# ------------------------------------------------------------
def _flush_timer():
    try:
        flush_pending()
    except Exception as e:
        print("[C7 Color Clip] 保存エラー:", e)
    return None


def _poll_timer():
    try:
        if not _pending and sync_from_disk():
            refresh_items()
    except Exception as e:
        print("[C7 Color Clip] 同期エラー:", e)
    return POLL_INTERVAL

# ------------------------------------------------------------
# プロパティ
# ------------------------------------------------------------
def on_item_changed(self, context):
    if _suppress:
        return
    e = get_entry(active_swatches(), self.si, self.ci)
    if e is None:
        return
    if self.ci < 0 and e.get("name") != self.name:
        # 名前が変わったら、開いている状態も引き継ぐ
        old = (_DATA["active"], e.get("name"))
        if old in _expanded:
            _expanded.discard(old)
            _expanded.add((_DATA["active"], self.name))
    val = {"name": self.name, "hex": linear_to_hex(self.color)}
    e.update(val)
    _pending[(_DATA["active"], self.si, self.ci)] = val
    # ドラッグ中は保存を間引く（最後の変更から SAVE_DELAY 秒後に保存）
    if bpy.app.timers.is_registered(_flush_timer):
        bpy.app.timers.unregister(_flush_timer)
    bpy.app.timers.register(_flush_timer, first_interval=SAVE_DELAY)


class CCLIP_Item(PropertyGroup):
    si: IntProperty(default=-1)   # 色の番号
    ci: IntProperty(default=-1)   # サブカラーの番号（-1 なら色そのもの）
    name: StringProperty(name="名前", update=on_item_changed)
    color: FloatVectorProperty(name="色", subtype="COLOR", size=4,
                               min=0.0, max=1.0, default=(1, 1, 1, 1),
                               update=on_item_changed)


def palette_items(self, context):
    global _enum_cache
    names = palette_names()
    _enum_cache = [(str(i), n, "", i) for i, n in enumerate(names)] \
        or [("0", "(パレットなし)", "", 0)]
    return _enum_cache


def get_palette(self):
    names = palette_names()
    a = _DATA.get("active")
    return names.index(a) if a in names else 0


def set_palette(self, value):
    flush_pending()
    names = palette_names()
    if 0 <= value < len(names):
        # 表示中パレットはこのBlender固有。保存はするが、他のBlenderは自分の表示を維持する
        _DATA["active"] = names[value]
        save_data()
        refresh_items()

# ------------------------------------------------------------
# マテリアル適用 / 取得
# ------------------------------------------------------------
def apply_to_material(mat, target, col):
    n = 0
    if mat.node_tree:
        for node in mat.node_tree.nodes:
            sock = None
            if node.type == "BSDF_PRINCIPLED":
                if target == "BASE":
                    sock = node.inputs.get("Base Color")
                else:
                    sock = node.inputs.get("Emission Color") or node.inputs.get("Emission")
                    st = node.inputs.get("Emission Strength")
                    if st and not st.is_linked and st.default_value == 0:
                        st.default_value = 1.0
            elif target == "EMISSION" and node.type == "EMISSION":
                sock = node.inputs.get("Color")
            if sock and not sock.is_linked:
                sock.default_value = col
                n += 1
    if target == "BASE":
        mat.diffuse_color = col  # ソリッド表示の色も合わせる
    return n


def pick_from_material(mat, target):
    """マテリアルから色を取得。RGBノード選択中はその色、
    それ以外は適用先（Base / Emission）に合わせたソケットの色"""
    nt = mat.node_tree
    if nt:
        act = nt.nodes.active
        if act and act.type == "RGB":
            return act.outputs[0].default_value, f"{mat.name} / {act.label or act.name}"
        if target == "EMISSION":
            for node in nt.nodes:
                if node.type == "BSDF_PRINCIPLED":
                    s = node.inputs.get("Emission Color") or node.inputs.get("Emission")
                    if s:
                        return s.default_value, f"{mat.name} (Emission)"
                elif node.type == "EMISSION":
                    return node.inputs["Color"].default_value, f"{mat.name} (Emission)"
        for node in nt.nodes:
            if node.type == "BSDF_PRINCIPLED":
                return node.inputs["Base Color"].default_value, mat.name
    return mat.diffuse_color, mat.name

# ------------------------------------------------------------
# オペレーター
# ------------------------------------------------------------
class CCLIP_OT_apply(Operator):
    bl_idname = "cclip.apply"
    bl_label = "マテリアルに適用"
    bl_description = "選択オブジェクトのアクティブマテリアルにこの色を流し込みます"
    bl_options = {"REGISTER", "UNDO"}
    index: IntProperty()

    def execute(self, context):
        wm = context.window_manager
        if not (0 <= self.index < len(wm.cclip_items)):
            return {"CANCELLED"}
        col = tuple(wm.cclip_items[self.index].color)
        objs = [o for o in context.view_layer.objects if o.select_get()]
        if not objs and context.active_object:
            objs = [context.active_object]
        mats = {}
        for o in objs:
            m = o.active_material
            if m:
                mats[m.as_pointer()] = m
        if not mats:
            self.report({"WARNING"}, "マテリアルのある選択オブジェクトがありません")
            return {"CANCELLED"}
        count = sum(apply_to_material(m, wm.cclip_target, col) for m in mats.values())
        self.report({"INFO"}, f"{len(mats)} マテリアル / {count} 箇所に適用しました")
        return {"FINISHED"}


class CCLIP_OT_copy_hex(Operator):
    bl_idname = "cclip.copy_hex"
    bl_label = "HEXをコピー"
    bl_description = "HEX(sRGB)をクリップボードにコピー"
    index: IntProperty()

    def execute(self, context):
        wm = context.window_manager
        if 0 <= self.index < len(wm.cclip_items):
            h = linear_to_hex(wm.cclip_items[self.index].color)
            wm.clipboard = h
            self.report({"INFO"}, f"{h} をコピーしました")
        return {"FINISHED"}


class CCLIP_OT_add_swatch(Operator):
    bl_idname = "cclip.add_swatch"
    bl_label = "色を追加"
    bl_description = "HEXを指定して色を追加（クリップボードのHEXを自動入力）"
    name: StringProperty(name="名前", default="New Color")
    hex: StringProperty(name="HEX", default="#FFFFFF")

    def invoke(self, context, event):
        h = normalize_hex(context.window_manager.clipboard)
        if h:
            self.hex = h
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        h = normalize_hex(self.hex)
        if not h:
            self.report({"ERROR"}, "HEXの形式が正しくありません")
            return {"CANCELLED"}

        def fn():
            ensure_palette()
            active_swatches().append({"name": self.name, "hex": h})
        commit(fn)
        return {"FINISHED"}


class CCLIP_OT_add_from_material(Operator):
    bl_idname = "cclip.add_from_material"
    bl_label = "マテリアルから追加"
    bl_description = ("アクティブマテリアルの色を追加（RGBノード選択中はその色、"
                      "それ以外は適用先の Base / Emission に合わせて取得）")

    def execute(self, context):
        obj = context.active_object
        mat = obj.active_material if obj else None
        if not mat:
            self.report({"WARNING"}, "アクティブなマテリアルがありません")
            return {"CANCELLED"}
        col, name = pick_from_material(mat, context.window_manager.cclip_target)
        h = linear_to_hex(col)

        def fn():
            ensure_palette()
            active_swatches().append({"name": name, "hex": h})
        commit(fn)
        return {"FINISHED"}


class CCLIP_OT_remove_swatch(Operator):
    bl_idname = "cclip.remove_swatch"
    bl_label = "色を削除"
    index: IntProperty()

    def execute(self, context):
        items = context.window_manager.cclip_items
        if not (0 <= self.index < len(items)):
            return {"CANCELLED"}
        si, ci = items[self.index].si, items[self.index].ci

        def fn():
            sws = active_swatches()
            if ci < 0:
                if 0 <= si < len(sws):
                    sws.pop(si)
            else:
                ch = sws[si].get("children") if 0 <= si < len(sws) else None
                if ch and 0 <= ci < len(ch):
                    ch.pop(ci)
        commit(fn)
        return {"FINISHED"}


class CCLIP_OT_move_swatch(Operator):
    bl_idname = "cclip.move_swatch"
    bl_label = "並べ替え"
    index: IntProperty()
    direction: IntProperty()

    def execute(self, context):
        items = context.window_manager.cclip_items
        if not (0 <= self.index < len(items)):
            return {"CANCELLED"}
        si, ci = items[self.index].si, items[self.index].ci

        def fn():
            sws = active_swatches()
            if ci < 0:
                lst, i = sws, si
            else:
                lst, i = (sws[si].get("children") or []) if 0 <= si < len(sws) else [], ci
            j = i + self.direction
            if 0 <= i < len(lst) and 0 <= j < len(lst):
                lst[i], lst[j] = lst[j], lst[i]
        commit(fn)
        return {"FINISHED"}


class CCLIP_OT_import_palettes(Operator, ImportHelper):
    bl_idname = "cclip.import_palettes"
    bl_label = "パレットを読み込む"
    bl_description = "JSONファイルからパレットを読み込みます（palettes.json と同じ形式）"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    mode: EnumProperty(name="同じ名前のパレット", items=[
        ("RENAME", "別名で追加", "「名前 2」のように番号を付けて追加"),
        ("REPLACE", "置き換える", "同じ名前のパレットを読み込んだ内容で置き換え"),
    ], default="RENAME")

    def execute(self, context):
        try:
            with open(self.filepath, encoding="utf-8") as f:
                d, _ = sanitize(json.load(f))
        except Exception as e:
            self.report({"ERROR"}, f"読み込めませんでした: {e}")
            return {"CANCELLED"}
        if not d or not d["palettes"]:
            self.report({"WARNING"}, "パレットが見つかりませんでした")
            return {"CANCELLED"}
        added = []

        def fn():
            for name, sws in d["palettes"].items():
                new, k = name, 2
                if self.mode == "RENAME":
                    while new in _DATA["palettes"]:
                        new = f"{name} {k}"
                        k += 1
                _DATA["palettes"][new] = sws
                added.append(new)
            _DATA["active"] = added[0]
        commit(fn)
        self.report({"INFO"}, f"{len(added)} パレットを読み込みました: " + ", ".join(added))
        return {"FINISHED"}


class CCLIP_OT_toggle(Operator):
    bl_idname = "cclip.toggle"
    bl_label = "開く / 閉じる"
    bl_description = "サブカラーを表示・非表示"
    index: IntProperty()

    def execute(self, context):
        items = context.window_manager.cclip_items
        if 0 <= self.index < len(items):
            key = (_DATA["active"], items[self.index].name)
            if key in _expanded:
                _expanded.discard(key)
            else:
                _expanded.add(key)
        return {"FINISHED"}


class CCLIP_OT_new_palette(Operator):
    bl_idname = "cclip.new_palette"
    bl_label = "新規パレット"
    name: StringProperty(name="パレット名", default="新規案件")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        def fn():
            base = self.name.strip() or "新規案件"
            name, k = base, 2
            while name in _DATA["palettes"]:
                name = f"{base} {k}"
                k += 1
            _DATA["palettes"][name] = []
            _DATA["active"] = name
        commit(fn)
        return {"FINISHED"}


class CCLIP_OT_delete_palette(Operator):
    bl_idname = "cclip.delete_palette"
    bl_label = "このパレットを削除しますか？"
    bl_description = "表示中のパレットを削除（元に戻せません）"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        def fn():
            a = _DATA.get("active")
            if a in _DATA["palettes"]:
                del _DATA["palettes"][a]
                _DATA["active"] = next(iter(_DATA["palettes"]), "")
        commit(fn)
        return {"FINISHED"}

# ------------------------------------------------------------
# パネル
# ------------------------------------------------------------
def draw_panel(layout, context):
    wm = context.window_manager

    row = layout.row(align=True)
    row.prop(wm, "cclip_palette", text="")
    row.operator("cclip.new_palette", text="", icon="ADD")
    row.operator("cclip.import_palettes", text="", icon="IMPORT")
    row.operator("cclip.delete_palette", text="", icon="TRASH")

    row = layout.row(align=True)
    row.prop(wm, "cclip_target", expand=True)

    layout.prop(wm, "cclip_edit", text="編集モード", icon="GREASEPENCIL", toggle=True)

    col = layout.column(align=True)
    items = wm.cclip_items
    pal = _DATA.get("active")
    # 色ごとのサブカラー数と、色の個数
    n_child = {}
    for it in items:
        if it.ci >= 0:
            n_child[it.si] = n_child.get(it.si, 0) + 1
    n_top = sum(1 for it in items if it.ci < 0)
    open_si = set()

    for i, it in enumerate(items):
        is_child = it.ci >= 0
        if is_child and it.si not in open_si:
            continue
        row = col.row(align=True)
        if is_child:
            row.label(text="", icon="BLANK1")
        elif n_child.get(it.si):
            opened = (pal, it.name) in _expanded
            if opened:
                open_si.add(it.si)
            row.operator("cclip.toggle", text="", emboss=False,
                         icon="DOWNARROW_HLT" if opened else "RIGHTARROW").index = i
        else:
            row.label(text="", icon="BLANK1")

        sp = row.split(factor=0.2, align=True)
        sp.prop(it, "color", text="")
        r = sp.row(align=True)
        last = (n_child.get(it.si, 0) if is_child else n_top) - 1
        pos = it.ci if is_child else it.si
        if wm.cclip_edit:
            r.prop(it, "name", text="")
            sub = r.row(align=True)
            sub.enabled = pos > 0
            op = sub.operator("cclip.move_swatch", text="", icon="TRIA_UP")
            op.index, op.direction = i, -1
            sub = r.row(align=True)
            sub.enabled = pos < last
            op = sub.operator("cclip.move_swatch", text="", icon="TRIA_DOWN")
            op.index, op.direction = i, 1
            r.operator("cclip.remove_swatch", text="", icon="X").index = i
        else:
            r.label(text=it.name)
            r.operator("cclip.copy_hex", text=linear_to_hex(it.color)).index = i
            r.operator("cclip.apply", text="", icon="BRUSH_DATA").index = i

    if n_top == 0:
        col.label(text="色がありません", icon="INFO")

    layout.separator()
    row = layout.row(align=True)
    row.operator("cclip.add_swatch", text="追加", icon="ADD")
    row.operator("cclip.add_from_material", text="マテリアルから", icon="EYEDROPPER")


class CCLIP_PanelBase:
    bl_region_type = "UI"
    bl_category = "Color Clip"
    bl_label = "C7 Color Clip"

    def draw(self, context):
        draw_panel(self.layout, context)


class CCLIP_PT_view3d(CCLIP_PanelBase, Panel):
    bl_idname = "CCLIP_PT_view3d"
    bl_space_type = "VIEW_3D"


class CCLIP_PT_node(CCLIP_PanelBase, Panel):
    bl_idname = "CCLIP_PT_node"
    bl_space_type = "NODE_EDITOR"

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == "ShaderNodeTree"

# ------------------------------------------------------------
# 登録
# ------------------------------------------------------------
classes = (
    CCLIP_Item,
    CCLIP_OT_apply, CCLIP_OT_copy_hex, CCLIP_OT_add_swatch,
    CCLIP_OT_add_from_material, CCLIP_OT_remove_swatch, CCLIP_OT_move_swatch,
    CCLIP_OT_new_palette, CCLIP_OT_delete_palette, CCLIP_OT_toggle,
    CCLIP_OT_import_palettes,
    CCLIP_PT_view3d, CCLIP_PT_node,
)


@persistent
def _on_load_post(_):
    refresh_items()


def _init_timer():
    refresh_items()
    return None


def register():
    for c in classes:
        bpy.utils.register_class(c)
    WM = bpy.types.WindowManager
    WM.cclip_items = CollectionProperty(type=CCLIP_Item)
    WM.cclip_palette = EnumProperty(name="パレット", items=palette_items,
                                    get=get_palette, set=set_palette)
    WM.cclip_target = EnumProperty(name="適用先", items=[
        ("BASE", "Base Color", "Principled BSDF の Base Color"),
        ("EMISSION", "Emission", "Principled の Emission Color / Emission ノード"),
    ])
    WM.cclip_edit = BoolProperty(name="編集モード", default=False)
    load_data()
    bpy.app.handlers.load_post.append(_on_load_post)
    bpy.app.timers.register(_init_timer, first_interval=0.1)
    bpy.app.timers.register(_poll_timer, first_interval=POLL_INTERVAL, persistent=True)


def unregister():
    try:
        flush_pending()
    except Exception as e:
        print("[C7 Color Clip] 保存エラー:", e)
    for t in (_flush_timer, _poll_timer, _init_timer):
        if bpy.app.timers.is_registered(t):
            bpy.app.timers.unregister(t)
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    WM = bpy.types.WindowManager
    for p in ("cclip_items", "cclip_palette", "cclip_target", "cclip_edit"):
        if hasattr(WM, p):
            delattr(WM, p)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()

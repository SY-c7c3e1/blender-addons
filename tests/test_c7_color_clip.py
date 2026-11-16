"""Color Clip 実機テスト（bpy モジュールでバックグラウンド実行）
usage: python tests/test_c7_color_clip.py c7_color_clip/__init__.py
"""
import importlib.util
import json
import os
import sys
import tempfile
import traceback

TMP_HOME = tempfile.mkdtemp(prefix="cclip_home_")
os.environ["HOME"] = TMP_HOME         # 実ユーザーの ~/BlenderColorClip を触らない
os.environ["USERPROFILE"] = TMP_HOME  # Windows はこちらを見る

import bpy  # noqa: E402

ADDON = sys.argv[1]
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def run(name, fn):
    try:
        fn()
    except Exception as e:
        results.append((name, False, repr(e)))
        print("ERROR", name)
        traceback.print_exc()


def load_module():
    spec = importlib.util.spec_from_file_location("color_clip", ADDON)
    m = importlib.util.module_from_spec(spec)
    sys.modules["color_clip"] = m
    spec.loader.exec_module(m)
    return m


# テスト用のサンプルパレット（架空の名前。色の値だけ検証しやすいものを使う）
DEF = "Sample"
FIX_UNITS = [("01 Alpha", "#90EE90"), ("02 Bravo", "#FFA500"), ("03 Charlie", "#FFFFCC"),
             ("04 Delta", "#00CCFF"), ("05 Echo", "#FFFF00"), ("06 Foxtrot", "#008000"),
             ("07 Golf", "#6600CC"), ("08 Hotel", "#FF0000"), ("09 India", "#F5F5F5"),
             ("10 Juliett", "#CC66CC"), ("11 Kilo", "#FFCCFF"), ("12 Lima", "#FF00CC"),
             ("13 Mike", "#101010"), ("14 November", "#0000FF"), ("15 Oscar", "#6880A0"),
             ("16 Papa", "#00CCBB")]
FIX_COUNTS = [3, 3, 2, 3, 2, 3, 3, 5, 2, 5, 3, 3, 3, 3, 3, 3]  # 計49


def fixture_data():
    sws = []
    for u, ((n, h), c) in enumerate(zip(FIX_UNITS, FIX_COUNTS)):
        ch = [{"name": f"{n[3]}-{k + 1}", "hex": "#%02X%02X%02X" % (u * 15 + 10, k * 45 + 20, 200 - u * 5)}
              for k in range(c)]
        sws.append({"name": n, "hex": h, "children": ch})
    return {"palettes": {DEF: sws}}


def fixture_file():
    path = os.path.join(TMP_HOME, "fixture.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fixture_data(), f, ensure_ascii=False)
    return path


def reset_to_fixture():
    d = fixture_data()
    d["active"] = DEF
    cc._DATA = d
    cc.save_data()
    cc.refresh_items()
    cc._expanded.clear()


def top(n):
    """n 番目の色（サブカラーを除く）の UI 上の index"""
    tops = [i for i, it in enumerate(bpy.context.window_manager.cclip_items) if it.ci < 0]
    return tops[n]


def ui_index(si, ci):
    for i, it in enumerate(bpy.context.window_manager.cclip_items):
        if it.si == si and it.ci == ci:
            return i
    raise KeyError((si, ci))


print("Blender", bpy.app.version_string)
cc = load_module()
check("DATA_PATH は一時HOME配下", cc.DATA_PATH.startswith(TMP_HOME), cc.DATA_PATH)

# ---------- register ----------
def t_register():
    cc.register()
    cc.refresh_items()  # timer はバックグラウンドで回らないので手動
    wm = bpy.context.window_manager
    check("register 成功 / JSON 生成", os.path.exists(cc.DATA_PATH))
    check("初回は空(内蔵パレットなし)", cc._DATA["palettes"] == {} and len(wm.cclip_items) == 0)
    r = bpy.ops.cclip.import_palettes(filepath=fixture_file())
    check("JSONから読み込み", r == {"FINISHED"})
    check("読み込み: 16色", sum(1 for it in wm.cclip_items if it.ci < 0) == 16)
    check("読み込み: 表示パレット", cc._DATA["active"] == DEF)
    # UI 上の色 → HEX が JSON の HEX と一致するか（float32 往復）
    bad = [(it.name, sw["hex"], cc.linear_to_hex(it.color))
           for it, sw in zip([it for it in wm.cclip_items if it.ci < 0], cc.active_swatches())
           if cc.linear_to_hex(it.color) != sw["hex"]]
    check("16色 HEX 往復一致 (float32経由)", not bad, bad)
    # JSON がこの時点で書き換わっていないか（refresh で update が走ると HEX が変わる恐れ）
    with open(cc.DATA_PATH, encoding="utf-8") as f:
        d = json.load(f)
    check("refresh_items で JSON が汚れない",
          [s["hex"] for s in d["palettes"][DEF]] == [h for _, h in FIX_UNITS])
run("register", t_register)


class MockLayout:
    """draw_panel を Blender の画面なしで呼ぶための記録用レイアウト"""
    def __init__(self, log):
        self.log = log
    def __getattr__(self, k):
        return None
    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
    def row(self, **kw): return MockLayout(self.log)
    def column(self, **kw): return MockLayout(self.log)
    def split(self, **kw): return MockLayout(self.log)
    def separator(self, **kw): pass
    def prop(self, data, prop, **kw):
        self.log.append(("prop", prop, getattr(data, "name", None)))
    def label(self, **kw):
        self.log.append(("label", kw.get("text"), kw.get("icon")))
    def operator(self, idname, **kw):
        op = type("Op", (), {})()
        self.log.append(("op", idname, kw.get("icon"), op))
        return op


def draw_log():
    log = []
    cc.draw_panel(MockLayout(log), bpy.context)
    return log


def t_members():
    wm = bpy.context.window_manager
    sws = cc.active_swatches()
    total = sum(len(sw.get("children", [])) for sw in sws)
    check("サブカラー49", total == 49, total)
    check("全ユニットにメンバー", all(sw.get("children") for sw in sws))
    check("サブカラーの並び", [c["name"] for c in sws[0]["children"]] == ["A-1", "A-2", "A-3"])
    check("サブカラーの HEX", sws[1]["children"][1] == fixture_data()["palettes"][DEF][1]["children"][1])
    check("UI 行数 16+49", len(wm.cclip_items) == 65, len(wm.cclip_items))
    bad = [(it.name, cc.linear_to_hex(it.color)) for it in wm.cclip_items if it.ci >= 0
           and cc.linear_to_hex(it.color) != sws[it.si]["children"][it.ci]["hex"]]
    check("メンバー HEX 往復一致", not bad, bad)
    # アイコン名が実在するか
    icons = bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items.keys()
    used = {"DOWNARROW_HLT", "RIGHTARROW", "BLANK1", "BRUSH_DATA", "TRIA_UP", "TRIA_DOWN", "X",
            "ADD", "TRASH", "GREASEPENCIL", "EYEDROPPER", "INFO"}
    check("使用アイコンが存在", used <= set(icons), used - set(icons))
    # 閉じた状態の描画: メンバーは出ない / ▶ が16個
    cc._expanded.clear()
    log = draw_log()
    toggles = [l for l in log if l[0] == "op" and l[1] == "cclip.toggle"]
    names = [l[2] for l in log if l[0] == "prop" and l[1] == "color"]
    check("閉: ▶ が16個", len(toggles) == 16 and all(t[2] == "RIGHTARROW" for t in toggles))
    check("閉: 色見本は16行", len(names) == 16, len(names))
    # 01 を開く
    bpy.ops.cclip.toggle(index=top(0))
    log = draw_log()
    names = [l[2] for l in log if l[0] == "prop" and l[1] == "color"]
    check("開: 01 の下に3つ", names[:4] == ["01 Alpha", "A-1", "A-2", "A-3"]
          and len(names) == 19, names[:5])
    applies = [l for l in log if l[0] == "op" and l[1] == "cclip.apply"]
    check("開: メンバーにも適用ボタン", len(applies) == 19)
    # 編集モードでの描画（例外なく、メンバー行に ▲▼×）
    wm.cclip_edit = True
    log = draw_log()
    wm.cclip_edit = False
    ups = [l for l in log if l[0] == "op" and l[1] == "cclip.move_swatch" and l[2] == "TRIA_UP"]
    check("編集: ▲ が 16+3", len(ups) == 19)
    check("編集: メンバー追加ボタンは無い", not any(l[0] == "op" and l[1] == "cclip.add_swatch" and l[2] == "ADD"
                                         for l in log[3:-2]))
    # メンバーに適用 / コピー
    o, m = make_obj("Member")
    select_only(o)
    wm.cclip_target = "BASE"
    i = ui_index(0, 0)  # A-1
    bpy.ops.cclip.apply(index=i)
    check("メンバー色を適用", cc.linear_to_hex(principled(m).inputs["Base Color"].default_value) == fixture_data()["palettes"][DEF][0]["children"][0]["hex"])
    check("copy_hex(メンバー)", bpy.ops.cclip.copy_hex(index=i) == {"FINISHED"})
    # メンバーの色・名前を編集 → JSON
    it = wm.cclip_items[ui_index(0, 1)]
    it.color = cc.hex_to_linear("#ABCDEF")
    it.name = "A-2改"
    cc.flush_pending()
    with open(cc.DATA_PATH, encoding="utf-8") as f:
        ch = json.load(f)["palettes"][DEF][0]["children"]
    check("メンバー編集→JSON", ch[1] == {"name": "A-2改", "hex": "#ABCDEF"}, ch[1])
    check("親の色は不変", cc.active_swatches()[0]["hex"] == "#90EE90")
    # ユニット名を変えても開いた状態を維持
    wm.cclip_items[top(0)].name = "01 Alpha改"
    check("改名後も開いたまま", (cc._DATA["active"], "01 Alpha改") in cc._expanded)
    # メンバーの並べ替え・削除
    bpy.ops.cclip.move_swatch(index=ui_index(0, 0), direction=1)
    check("メンバー並べ替え", [c["name"] for c in cc.active_swatches()[0]["children"]][:2] == ["A-2改", "A-1"])
    bpy.ops.cclip.move_swatch(index=ui_index(0, 2), direction=1)
    check("メンバー末尾で下は無視", cc.active_swatches()[0]["children"][2]["name"] == "A-3")
    bpy.ops.cclip.remove_swatch(index=ui_index(0, 2))
    check("メンバー削除", len(cc.active_swatches()[0]["children"]) == 2 and len(cc.active_swatches()) == 16)
    # ユニットごと並べ替え → メンバーもついてくる
    bpy.ops.cclip.move_swatch(index=top(0), direction=1)
    check("親の移動でサブカラーも移動", cc.active_swatches()[1]["children"][0]["name"] == "A-2改")
    # 元に戻す
    reset_to_fixture()


# ---------- シーン準備 ----------
def make_obj(name, emission_node=False):
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new(name + "_mat")
    if hasattr(mat, "use_nodes") and bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    if emission_node:
        nt = mat.node_tree
        nt.nodes.new("ShaderNodeEmission")
    me.materials.append(mat)
    return ob, mat


def select_only(*obs):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0] if obs else None


def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def approx(a, b, eps=1e-5):
    return all(abs(x - y) < eps for x, y in zip(a, b))


# ---------- apply ----------
def t_apply():
    wm = bpy.context.window_manager
    o1, m1 = make_obj("A")
    o2, m2 = make_obj("B", emission_node=True)
    o3, _ = make_obj("NoMat")
    o3.data.materials.clear()
    select_only(o1, o2)
    wm.cclip_target = "BASE"
    want = tuple(wm.cclip_items[top(7)].color)  # High×Joker #FF0000
    r = bpy.ops.cclip.apply(index=top(7))
    check("apply BASE 実行", r == {"FINISHED"}, r)
    check("Base Color socket 値", approx(principled(m1).inputs["Base Color"].default_value, want),
          tuple(principled(m1).inputs["Base Color"].default_value))
    check("diffuse_color 同期", approx(m1.diffuse_color, want))
    check("2マテリアル目にも適用", approx(principled(m2).inputs["Base Color"].default_value, want))

    wm.cclip_target = "EMISSION"
    want = tuple(wm.cclip_items[top(3)].color)  # Beit
    p = principled(m1)
    p.inputs["Emission Strength"].default_value = 0.0
    r = bpy.ops.cclip.apply(index=top(3))
    check("apply EMISSION 実行", r == {"FINISHED"})
    check("Emission Color socket 値", approx(p.inputs["Emission Color"].default_value, want))
    check("Emission Strength 0→1", p.inputs["Emission Strength"].default_value == 1.0)
    em = next(n for n in m2.node_tree.nodes if n.type == "EMISSION")
    check("Emission ノード Color", approx(em.inputs["Color"].default_value, want))

    # Strength が 0 以外なら変更しない
    p.inputs["Emission Strength"].default_value = 5.0
    bpy.ops.cclip.apply(index=top(3))
    check("Emission Strength 5 は維持", p.inputs["Emission Strength"].default_value == 5.0)

    # リンクされたソケットは上書きしない
    wm.cclip_target = "BASE"
    nt = m1.node_tree
    rgb = nt.nodes.new("ShaderNodeRGB")
    nt.links.new(rgb.outputs[0], p.inputs["Base Color"])
    before = tuple(p.inputs["Base Color"].default_value)
    bpy.ops.cclip.apply(index=0)
    check("リンク済み Base Color は不変", approx(p.inputs["Base Color"].default_value, before))
    nt.nodes.remove(rgb)

    # マテリアル無し
    select_only(o3)
    r = bpy.ops.cclip.apply(index=0)
    check("マテリアル無しは CANCELLED", r == {"CANCELLED"}, r)
    r = bpy.ops.cclip.apply(index=999)
    check("範囲外 index は CANCELLED", r == {"CANCELLED"})
    select_only(o1)
run("apply", t_apply)
run("members", t_members)

# ---------- copy hex ----------
def t_copy():
    wm = bpy.context.window_manager
    r = bpy.ops.cclip.copy_hex(index=top(1))
    check("copy_hex 実行", r == {"FINISHED"})
    cb = wm.clipboard
    check("クリップボード=#FFA500 (bgでは空の可能性あり)", cb in ("#FFA500", ""), repr(cb))
run("copy_hex", t_copy)

# ---------- add ----------
def t_add():
    wm = bpy.context.window_manager
    n = len(wm.cclip_items)
    r = bpy.ops.cclip.add_swatch(name="テスト", hex="＃abc")
    check("add_swatch 全角＃+3桁", r == {"FINISHED"} and cc.active_swatches()[-1]["hex"] == "#AABBCC",
          cc.active_swatches()[-1])
    check("UI に反映", len(wm.cclip_items) == n + 1)
    try:
        r = bpy.ops.cclip.add_swatch(name="bad", hex="#GGGGGG")
    except RuntimeError:
        r = {"CANCELLED"}
    check("不正HEXは追加されない", len(wm.cclip_items) == n + 1)

    # マテリアルから
    o, m = make_obj("Pick")
    principled(m).inputs["Base Color"].default_value = cc.hex_to_linear("#336699")
    select_only(o)
    r = bpy.ops.cclip.add_from_material()
    check("add_from_material (Principled)", cc.active_swatches()[-1]["hex"] == "#336699",
          cc.active_swatches()[-1])
    rgb = m.node_tree.nodes.new("ShaderNodeRGB")
    rgb.outputs[0].default_value = cc.hex_to_linear("#C7C3E1")
    m.node_tree.nodes.active = rgb
    bpy.ops.cclip.add_from_material()
    check("add_from_material (RGBノード)", cc.active_swatches()[-1]["hex"] == "#C7C3E1",
          cc.active_swatches()[-1])
    m.node_tree.nodes.active = principled(m)
    principled(m).inputs["Emission Color"].default_value = cc.hex_to_linear("#FF8800")
    wm.cclip_target = "EMISSION"
    bpy.ops.cclip.add_from_material()
    check("add_from_material (Emission)", cc.active_swatches()[-1]["hex"] == "#FF8800",
          cc.active_swatches()[-1])
    wm.cclip_target = "BASE"
run("add", t_add)

# ---------- 編集（UIプロパティ経由） ----------
def t_edit():
    wm = bpy.context.window_manager
    it = wm.cclip_items[0]
    it.name = "Alpha改"
    it.color = cc.hex_to_linear("#123456")
    if hasattr(cc, "flush_pending"):
        with open(cc.DATA_PATH, encoding="utf-8") as f:
            before = json.load(f)
        check("ドラッグ中は即保存しない", before["palettes"][DEF][0]["hex"] != "#123456")
        cc.flush_pending()
    with open(cc.DATA_PATH, encoding="utf-8") as f:
        sw = json.load(f)["palettes"][DEF][0]
    check("UIで名前変更→JSON", sw["name"] == "Alpha改")
    check("UIで色変更→JSON", sw["hex"] == "#123456", sw)
run("edit", t_edit)

# ---------- move / remove ----------
def t_move_remove():
    wm = bpy.context.window_manager
    a, b = cc.active_swatches()[0]["name"], cc.active_swatches()[1]["name"]
    bpy.ops.cclip.move_swatch(index=0, direction=1)
    check("move 下", [s["name"] for s in cc.active_swatches()[:2]] == [b, a])
    check("move UI反映", wm.cclip_items[0].name == b)
    bpy.ops.cclip.move_swatch(index=0, direction=-1)
    check("move 先頭で上は無視", cc.active_swatches()[0]["name"] == b)
    n = len(cc.active_swatches())
    bpy.ops.cclip.remove_swatch(index=0)
    check("remove", len(cc.active_swatches()) == n - 1
          and sum(1 for it in wm.cclip_items if it.ci < 0) == n - 1)
run("move_remove", t_move_remove)

# ---------- palettes ----------
def t_palettes():
    wm = bpy.context.window_manager
    bpy.ops.cclip.new_palette(name="案件A")
    check("new_palette", cc._DATA["active"] == "案件A" and len(wm.cclip_items) == 0)
    bpy.ops.cclip.new_palette(name="案件A")
    check("同名は連番", "案件A 2" in cc._DATA["palettes"])
    check("enum 表示=案件A 2", wm.cclip_palette == str(cc.palette_names().index("案件A 2")))
    wm.cclip_palette = "0"
    check("enum 切替→Sample", cc._DATA["active"] == DEF and len(wm.cclip_items) > 0)
    wm.cclip_palette = str(cc.palette_names().index("案件A 2"))
    bpy.ops.cclip.delete_palette()
    check("delete_palette", "案件A 2" not in cc._DATA["palettes"])
    # 全削除 → 追加で自動作成
    for _ in range(len(cc._DATA["palettes"])):
        bpy.ops.cclip.delete_palette()
    check("全削除", cc._DATA["palettes"] == {} and len(wm.cclip_items) == 0)
    check("全削除後 enum 取得OK", wm.cclip_palette == "0")
    bpy.ops.cclip.add_swatch(name="x", hex="#010203")
    check("空から追加で新規パレット", len(cc._DATA["palettes"]) == 1 and len(wm.cclip_items) == 1)
run("palettes", t_palettes)

# ---------- JSON 保存/再読込/破損 ----------
def t_json():
    snapshot = json.loads(json.dumps(cc._DATA))
    cc._DATA = {"active": "", "palettes": {}}
    cc.load_data()
    check("再読み込みで同内容", cc._DATA == snapshot)
    with open(cc.DATA_PATH, "w", encoding="utf-8") as f:
        f.write("{ broken json")
    cc.load_data()
    check("破損→.bak 退避", os.path.exists(cc.DATA_PATH + ".bak"))
    check("破損→初期化(空)", cc._DATA["palettes"] == {})
    # 構造は dict だが中身が壊れているケース
    os.remove(cc.DATA_PATH + ".bak")
    with open(cc.DATA_PATH, "w", encoding="utf-8") as f:
        json.dump({"active": "p", "palettes": {"p": [{"name": "a"}, "junk", None]}}, f)
    cc.load_data()
    try:
        cc.refresh_items()
        check("中身が不正な JSON でも refresh 可能", True)
        check("不正項目だけ除外", [s["name"] for s in cc._DATA["palettes"]["p"]] == [], cc._DATA)
        check("不正項目除外時に .bak コピー", os.path.exists(cc.DATA_PATH + ".bak"))
    except Exception as e:
        check("中身が不正な JSON でも refresh 可能", False, repr(e))
    try:
        cc.palette_items(None, bpy.context)
        with open(cc.DATA_PATH, "w", encoding="utf-8") as f:
            json.dump({"active": "p", "palettes": {"p": {"oops": 1}}}, f)
        cc.load_data()
        cc.refresh_items()
        check("palettes 値が dict でも refresh 可能", True)
    except Exception as e:
        check("palettes 値が dict でも refresh 可能", False, repr(e))
    # 未知のキーは保持
    with open(cc.DATA_PATH, "w", encoding="utf-8") as f:
        json.dump({"active": "p", "ae": {"x": 1}, "palettes": {"p": [{"name": "a", "hex": "#abc", "ae_id": 5}]}}, f)
    cc.load_data()
    cc.save_data()
    with open(cc.DATA_PATH, encoding="utf-8") as f:
        d = json.load(f)
    check("未知のキーを保持", d.get("ae") == {"x": 1} and d["palettes"]["p"][0].get("ae_id") == 5, d)
    check(".tmp が残らない", not os.path.exists(cc.DATA_PATH + ".tmp"))
run("json", t_json)

# ---------- 2つのBlenderを同時に使う想定 ----------
def t_multi():
    if not hasattr(cc, "sync_from_disk"):
        check("同時使用（v0.1は未対応）", False)
        return
    import time
    wm = bpy.context.window_manager
    reset_to_fixture()
    bpy.ops.cclip.new_palette(name="こちら表示中")
    # 「もう1台のBlender」がファイルを書き換える（色追加 + パレット切替）
    time.sleep(0.01)
    with open(cc.DATA_PATH, encoding="utf-8") as f:
        other = json.load(f)
    other["palettes"][DEF].append({"name": "他PCで追加", "hex": "#111111"})
    other["active"] = DEF
    with open(cc.DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(other, f, ensure_ascii=False)
    # こちらで色を追加 → 相手の追加が消えないか
    bpy.ops.cclip.add_swatch(name="こちらで追加", hex="#222222")
    with open(cc.DATA_PATH, encoding="utf-8") as f:
        d = json.load(f)
    check("相手の追加が残る", d["palettes"][DEF][-1]["name"] == "他PCで追加")
    check("自分の追加も入る", d["palettes"]["こちら表示中"][-1]["name"] == "こちらで追加")
    check("相手がパレットを切り替えてもこちらの表示は維持", cc._DATA["active"] == "こちら表示中")
    # ポーリングでの反映
    time.sleep(0.01)
    other = d
    other["palettes"]["こちら表示中"].append({"name": "外部追加2", "hex": "#333333"})
    with open(cc.DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(other, f, ensure_ascii=False)
    cc._poll_timer()
    check("ポーリングでUIに反映", wm.cclip_items[-1].name == "外部追加2")
    # 未保存の色編集 + 外部変更 → 両方残る
    wm.cclip_items[0].name = "編集中"
    time.sleep(0.01)
    with open(cc.DATA_PATH, encoding="utf-8") as f:
        other = json.load(f)
    other["palettes"]["新PC"] = []
    with open(cc.DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(other, f, ensure_ascii=False)
    cc._poll_timer()  # 未保存の編集があるので読み直さない
    check("未保存の編集中はポーリングで上書きしない", wm.cclip_items[0].name == "編集中")
    cc.flush_pending()
    with open(cc.DATA_PATH, encoding="utf-8") as f:
        d = json.load(f)
    check("flush で外部変更と編集が両立", "新PC" in d["palettes"] and d["palettes"]["こちら表示中"][0]["name"] == "編集中")
run("multi", t_multi)

# ---------- JSON からの読み込み ----------
def t_import():
    reset_to_fixture()
    src = fixture_file()
    bpy.ops.cclip.import_palettes(filepath=src, mode="RENAME")
    check("読み込み(別名): Sample 2", "Sample 2" in cc._DATA["palettes"] and cc._DATA["active"] == "Sample 2")
    check("読み込み(別名): 元は残る", DEF in cc._DATA["palettes"])
    cc._DATA["palettes"][DEF][0]["children"] = []
    cc.save_data()
    bpy.ops.cclip.import_palettes(filepath=src, mode="REPLACE")
    check("読み込み(置換): サブカラーが戻る", len(cc._DATA["palettes"][DEF][0]["children"]) == 3)
    check("読み込み(置換): 増えない", sorted(cc._DATA["palettes"]) == [DEF, "Sample 2"])
    with open(cc.DATA_PATH, encoding="utf-8") as f:
        check("読み込み: ファイルに保存", "Sample 2" in json.load(f)["palettes"])
    bad = os.path.join(TMP_HOME, "bad.json")
    with open(bad, "w") as f:
        f.write("{ nope")
    n = len(cc._DATA["palettes"])
    try:
        r = bpy.ops.cclip.import_palettes(filepath=bad)
    except RuntimeError:
        r = {"CANCELLED"}
    check("読み込み: 壊れたJSONは中止", r == {"CANCELLED"} and len(cc._DATA["palettes"]) == n)
    with open(bad, "w") as f:
        json.dump({"palettes": {}}, f)
    try:
        r = bpy.ops.cclip.import_palettes(filepath=bad)
    except RuntimeError:
        r = {"CANCELLED"}
    check("読み込み: 空なら中止", r == {"CANCELLED"})
    check("読み込み: 元ファイルは変更しない", json.load(open(src, encoding="utf-8")) == fixture_data())
    # 不正なサブカラー
    bad = {"active": "p", "palettes": {"p": [
        {"name": "a", "hex": "#111111", "children": "oops"},
        {"name": "b", "hex": "#222222", "children": [{"name": "ok", "hex": "#333"}, {"name": "ng"},
                                                     {"name": "孫", "hex": "#444444", "children": [{"name": "x", "hex": "#555555"}]}]}]}}
    with open(cc.DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(bad, f, ensure_ascii=False)
    cc.load_data()
    cc.refresh_items()
    p = cc._DATA["palettes"]["p"]
    check("不正: children が文字列なら除去", "children" not in p[0])
    check("不正: 壊れたメンバーだけ除外・孫は除去",
          [c["name"] for c in p[1]["children"]] == ["ok", "孫"] and "children" not in p[1]["children"][1]
          and p[1]["children"][0]["hex"] == "#333333", p[1])
    reset_to_fixture()
run("import", t_import)

# ---------- unregister / 再register ----------
def t_unreg():
    cc.unregister()
    check("unregister 成功", not hasattr(bpy.types.WindowManager, "cclip_items"))
    check("handler 除去", cc._on_load_post not in bpy.app.handlers.load_post)
    cc.register()
    cc.unregister()
    check("再 register/unregister", True)
run("unregister", t_unreg)

fails = [r for r in results if not r[1]]
print(f"\n== {bpy.app.version_string}: {len(results) - len(fails)}/{len(results)} PASS ==")
for f in fails:
    print("  FAIL:", f[0], f[2])

"""C7 Text Tools 実機テスト（bpy モジュールでバックグラウンド実行）
usage: python tests/test_c7_text_tools.py c7_text_tools
"""
import importlib.util
import math
import os
import sys
import tempfile
import traceback

TMP_HOME = tempfile.mkdtemp(prefix="c7text_home_")
os.environ["HOME"] = TMP_HOME         # 実ユーザーの設定フォルダ（お気に入り等）を触らない
os.environ["USERPROFILE"] = TMP_HOME  # Windows はこちらを見る

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

ADDON_DIR = os.path.abspath(sys.argv[1])
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


def load_package():
    name = "c7_text_tools"
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ADDON_DIR, "__init__.py"), submodule_search_locations=[ADDON_DIR])
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


# GPU（フォントのサムネ描画）は使える環境だけ
try:
    import gpu
    gpu.init()
    HAS_GPU = True
except Exception:
    HAS_GPU = False

pkg = load_package()
pkg.register()
kana = sys.modules["c7_text_tools.kana"]
fp = sys.modules["c7_text_tools.font_preview"]
outline = sys.modules["c7_text_tools.outline"]


def reset():
    bpy.ops.wm.read_homefile(use_empty=True)


def world_pts(o):
    dg = bpy.context.evaluated_depsgraph_get()
    e = o.evaluated_get(dg)
    me = e.to_mesh()
    r = [e.matrix_world @ v.co for v in me.vertices]
    e.to_mesh_clear()
    return r


def bbox(pts, nd=4):
    return [round(min(p[i] for p in pts), nd) for i in range(2)] + \
           [round(max(p[i] for p in pts), nd) for i in range(2)]


fp.scan_fonts()
JA = [f for f in fp.S.fonts if "JA" in f["cats"]]
JA_FONT = JA[0]["path"] if JA else None
print(f"fonts: {len(fp.S.fonts)}  japanese: {len(JA)}  gpu: {HAS_GPU}")


def fontmeta_missing(path, text):
    return sys.modules["c7_text_tools.fontmeta"].missing_chars(path, text)


# ---------- フォント情報 ----------
def t_fontmeta():
    check("フォントを読み込める", len(fp.S.fonts) > 0, len(fp.S.fonts))
    check("日本語フォントがある（以降のテストに必要）", JA_FONT is not None)
    props = bpy.context.window_manager.c7_font_preview
    props.category = 'JA'
    check("カテゴリ: 日本語で絞り込み", all("JA" in f["cats"] for f in fp.filtered_fonts(props)))
    props.category = 'ALL'
    props.search = "zzzz-no-such-font"
    check("検索: 該当なし", fp.filtered_fonts(props) == [])
    props.search = ""
    if JA_FONT:
        check("未対応文字の判定", fontmeta_missing(JA_FONT, "あ漢A") == [])
run("fontmeta", t_fontmeta)


# ---------- フォントプレビュー ----------
def t_preview():
    reset()
    props = bpy.context.window_manager.c7_font_preview
    props.sample_text = "ライブ\\n会場へ"
    bpy.ops.c7fp.new_text(filepath=JA_FONT)
    t = bpy.context.active_object
    check("＋: 新規テキストの名前", t.name == "ライブ 会場へ_text", t.name)
    check("＋: 改行が入る", t.data.body == "ライブ\n会場へ", repr(t.data.body))
    bpy.ops.c7kana.add()
    k = bpy.context.active_object
    t.select_set(True)
    props.sample_text = "ようこそ"
    bpy.ops.c7fp.apply_text()
    check("反映: 普通のテキスト", t.data.body == "ようこそ")
    check("反映: かなスケール", k.c7_kana.text == "ようこそ")
    other = [f for f in JA if f["path"] != JA_FONT]
    if other:
        bpy.ops.c7fp.apply_font(filepath=other[0]["path"])
        check("フォント適用: かなスケールにも", k.c7_kana.font.filepath and
              os.path.normcase(bpy.path.abspath(k.c7_kana.font.filepath)) ==
              os.path.normcase(other[0]["path"]))
    bpy.ops.c7fp.toggle_favorite(filepath=JA_FONT)
    props.category = 'FAV'
    check("お気に入り", len(fp.filtered_fonts(props)) == 1)
    bpy.ops.c7fp.toggle_favorite(filepath=JA_FONT)
    props.category = 'ALL'
    if HAS_GPU:
        props.category = 'JA'
        n = fp.ensure_previews(props, fp.page_fonts(props)[0])
        check("サムネ描画", n > 0, n)
        props.category = 'ALL'
run("preview", t_preview)


# ---------- かなスケール：名前・1文字調整 ----------
def t_kana():
    reset()
    bpy.ops.c7kana.add()
    k = bpy.context.active_object
    st = k.c7_kana
    check("追加: 名前", k.name == "平仮名を小さく_kana", k.name)
    st.text = "ライブ会場へ"
    check("文字を変えると名前も変わる", k.name == "ライブ会場へ_kana", k.name)
    k.name = "手で付けた名前"
    st.text = "ようこそ"
    check("手で変えた名前は変えない", k.name == "手で付けた名前", k.name)
    st.text = "ライブ会場へ"
    n0 = len(k.data.splines)
    st.kern_cursor = 3
    st.char_rise = 0.3
    st.kern_cursor = 4
    st.char_scale = 150
    st.kern_cursor = 5
    st.char_skew = math.radians(-20)
    st.kern_cursor = 1
    st.kern_value = -0.1
    check("1文字調整の記録", len(st.char_adjust) == 3 and len(st.kernings) == 1)
    check("調整しても文字数は同じ", len(k.data.splines) == n0)
    st.kern_cursor = 3
    st.char_rise = 0.0
    check("初期値に戻すと項目が消える", len(st.char_adjust) == 2)
    bpy.ops.c7kana.char_reset(index=-1)
    check("全部リセット", len(st.char_adjust) == 0 and len(st.kernings) == 0)
    before = bbox(world_pts(k))
    st.skew = math.radians(15)
    after = bbox(world_pts(k))
    check("全体の傾きで右上が右へ", after[2] > before[2], (before, after))
run("kana", t_kana)


# ---------- アウトライン ----------
def t_outline():
    reset()
    bpy.ops.c7kana.add()
    k = bpy.context.active_object
    k.c7_kana.text = "会場"
    bpy.ops.c7text.outline_add()
    o = k.c7_outline.target
    check("フチ: 作成・子", o is not None and o.parent == k)
    check("フチ: 名前", o.name == "会場_kana_outline", o.name)
    ng = o.modifiers[0].node_group
    check("フチ: 線だけ（塗りのノードなし）",
          not any(n.bl_idname == "GeometryNodeFillCurve" for n in ng.nodes))
    n1 = len(o.data.splines)
    k.c7_kana.text = "会場へ"
    check("フチ: 文字の変更に追従", len(o.data.splines) == len(k.data.splines) > n1)
    bpy.ops.object.text_add()
    t = bpy.context.active_object
    t.data.body = "LIVE"
    bpy.ops.c7text.outline_add()
    to = t.c7_outline.target
    t.data.body = "LIVE 2027"
    bpy.context.view_layer.update()
    outline.sync_all()
    check("フチ: 普通のテキストにも・追従", to.type == "CURVE" and len(to.data.splines) > 4)
    path = bpy.data.objects.new("path", bpy.data.curves.new("path", "CURVE"))
    bpy.context.collection.objects.link(path)
    m = k.modifiers.new("Curve", "CURVE")
    m.object = path
    outline.sync(k, force=True)
    check("フチ: モディファイアをコピー（線のノードが先頭）",
          [x.type for x in o.modifiers] == ["NODES", "CURVE"], [x.type for x in o.modifiers])
    bpy.context.view_layer.objects.active = k
    bpy.ops.c7text.outline_remove()
    check("フチ: 削除", k.c7_outline.target is None)
run("outline", t_outline)


# ---------- バラす ----------
def t_split():
    reset()
    bpy.ops.c7kana.add()
    k = bpy.context.active_object
    st = k.c7_kana
    st.text = "ライブ会場\\nようこそ"
    st.kern_cursor = 3
    st.char_rise = 0.25
    k.location = (1, 0.5, 0.3)
    k.rotation_euler = (0, 0, math.radians(20))
    k.scale = (1.5, 1.5, 1.5)
    bpy.ops.c7text.outline_add()
    before = bbox(world_pts(k))
    bpy.ops.c7kana.split()
    e = bpy.context.active_object
    chars = [c for c in e.children if not c.name.endswith("_outline")]
    check("バラす: エンプティの名前", e.name == "ライブ会場 ようこそ_split", e.name)
    check("バラす: コレクション", e.users_collection[0].name == e.name)
    check("バラす: 文字数（改行は除く）", len(chars) == 9, len(chars))
    check("バラす: 文字の名前", chars[0].name == "ライブ会場 ようこそ_01_ラ", chars[0].name)
    after = bbox([p for c in chars for p in world_pts(c)])
    check("バラす: 文字の位置が変わらない", before == after, (before, after))
    inv = e.matrix_world.inverted()
    loc = bbox([inv @ p for c in chars for p in world_pts(c)])
    check("バラす: エンプティが文字全体の中心",
          abs(loc[0] + loc[2]) < 1e-3 and abs(loc[1] + loc[3]) < 1e-3, loc)
    c = chars[3]
    lp = bbox([c.matrix_world.inverted() @ p for p in world_pts(c)])
    check("バラす: 各文字の原点が中心", abs(lp[0] + lp[2]) < 1e-3 and abs(lp[1] + lp[3]) < 1e-3, lp)
    check("バラす: 各文字にフチ", sum(1 for c in chars if c.children) == len(chars))
    check("バラす: 元は非表示で残る", k.hide_get() and k.hide_render)
run("split", t_split)


# ---------- 普通のテキストから送る ----------
def t_convert():
    reset()
    for label, setup in (
        ("左揃え", lambda t: None),
        ("中央揃え＋傾き", lambda t: (setattr(t.data, "align_x", "CENTER"), setattr(t.data, "shear", 0.25))),
        ("2行・行間1.5", lambda t: (setattr(t.data, "body", "上\n下"), setattr(t.data, "space_line", 1.5))),
        ("上下中央揃え", lambda t: setattr(t.data, "align_y", "CENTER")),
    ):
        cu = bpy.data.curves.new("t", "FONT")
        cu.body = "ライブ会場LIVE"
        cu.font = bpy.data.fonts.load(JA_FONT, check_existing=True)
        cu.size = 1.5
        t = bpy.data.objects.new("t", cu)
        bpy.context.collection.objects.link(t)
        t.location = (0.5, 0.2, 0)
        t.rotation_euler.z = math.radians(10)
        setup(t)
        bpy.context.view_layer.objects.active = t
        before = bbox(world_pts(t), 3)
        bpy.ops.c7kana.from_text(mode="KANA")
        k = bpy.context.active_object
        k.c7_kana.scale_hira = 100
        k.c7_kana.scale_kata = 100
        check(f"送る: {label} で位置が一致（かな100%）", before == bbox(world_pts(k), 3),
              (before, bbox(world_pts(k), 3)))
    # 原点を動かしたテキスト
    cu = bpy.data.curves.new("t", "FONT")
    cu.body = "ライブ会場"
    cu.font = bpy.data.fonts.load(JA_FONT, check_existing=True)
    t = bpy.data.objects.new("t", cu)
    bpy.context.collection.objects.link(t)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    t.select_set(True)
    bpy.context.view_layer.objects.active = t
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    before = bbox(world_pts(t), 3)
    bpy.ops.c7kana.from_text(mode="KANA")
    k = bpy.context.active_object
    k.c7_kana.scale_hira = 100
    k.c7_kana.scale_kata = 100
    check("送る: 原点を中心にしたテキストもずれない", before == bbox(world_pts(k), 3))
    check("送る: 名前", k.name.startswith("ライブ会場_kana"), k.name)
    check("送る: 元は非表示", t.hide_get() and t.hide_render)
    bpy.ops.object.text_add()
    t2 = bpy.context.active_object
    t2.data.body = "バラ文字"
    bpy.ops.c7kana.from_text(mode="SPLIT")
    check("バラ文字へ送る", bpy.context.active_object.name == "バラ文字_split",
          bpy.context.active_object.name)
run("convert", t_convert)


# ---------- 保存・読み込み ----------
def t_save():
    reset()
    bpy.ops.c7kana.add()
    k = bpy.context.active_object
    k.c7_kana.text = "保存テスト"
    k.c7_kana.kern_cursor = 2
    k.c7_kana.char_rise = 0.2
    bpy.ops.c7text.outline_add()
    path = os.path.join(TMP_HOME, "t.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    k = bpy.data.objects["保存テスト_kana"]
    check("保存: 設定が残る", k.c7_kana.is_c7 and len(k.c7_kana.char_adjust) == 1)
    k.c7_kana.text = "読み込み後"
    check("保存: 読み込み後もフチが追従",
          len(k.c7_outline.target.data.splines) == len(k.data.splines))
run("save", t_save)


# ---------- unregister ----------
def t_unreg():
    pkg.unregister()
    check("unregister 成功", not hasattr(bpy.types.Object, "c7_kana"))
    check("handler 除去", outline._on_depsgraph not in bpy.app.handlers.depsgraph_update_post)
    pkg.register()
    pkg.unregister()
    check("再 register/unregister", True)
run("unregister", t_unreg)

fails = [r for r in results if not r[1]]
print(f"\n== {bpy.app.version_string}: {len(results) - len(fails)}/{len(results)} PASS ==")
for f in fails:
    print("  FAIL:", f[0], f[2])
sys.exit(1 if fails else 0)

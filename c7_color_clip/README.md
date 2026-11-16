# C7 Color Clip

Per-project color palettes for Blender: copy HEX codes and apply colors to materials in one click.
案件ごとのカラーパレットから、HEXのコピーやマテリアルへの色の適用をワンクリックで行います。

## Location / 場所

**3D Viewport / Shader Editor > Sidebar (N) > Color Clip**
**3Dビュー / シェーダーエディタ > サイドバー(Nキー) > Color Clip**

## Usage / 使い方

### Apply a color / 色を塗る

1. Select objects (multiple OK). / オブジェクトを選択(複数可)
2. Choose the target. / 適用先を選ぶ
   - **Base Color** — Principled BSDF Base Color (viewport solid color is synced too). / Principled BSDF の Base Color(ソリッド表示の色も同期)
   - **Emission** — Principled Emission Color and Emission node Color. Strength 0 is set to 1. / Principled の Emission Color と Emission ノードの Color。Strength が 0 なら 1 にします
3. Click the **brush icon** on the color row. / 色の行の **ブラシアイコン** を押す

- Only the active material of each object is changed. / 対象は各オブジェクトのアクティブなマテリアルのみ
- Linked sockets are not overwritten. / ノードがつながっているソケットは上書きしません
- Undo with Ctrl+Z. / Ctrl+Z で戻せます

### Sub-colors / サブカラー

A color can hold sub-colors (e.g. a group color and its members' colors), defined in the JSON (`children`). Click **▶** to show them; they work like normal colors (HEX copy, apply, rename / recolor / reorder / delete in Edit Mode).
色の下にサブカラー(例:グループの色と、その各メンバーの色)をぶら下げられます。JSONの `children` で指定します。**▶** を押すと表示され、通常の色と同じく HEXコピー・適用、編集モードでの名前/色の変更・並べ替え・削除ができます。

- Open/closed state is per Blender and not saved. / 開閉状態は Blender ごとで、保存しません。

### Copy a color / 色をコピーする

- **HEX button** — copies the sRGB HEX to the clipboard (paste into AE / Photoshop). / HEX(sRGB)をクリップボードへ。AE・Photoshop にそのまま貼れます
- **Swatch** — drag & drop onto any other color field in Blender. / 色見本は Blender の他のカラー欄へドラッグ＆ドロップできます

### Add a color / 色を追加する

- **追加 (Add)** — HEX dialog, pre-filled from the clipboard. Full-width `＃` and 3-digit HEX (`#abc`) are accepted. / HEX入力ダイアログ。クリップボードのHEXを自動入力。全角「＃」や3桁HEX(`#abc`)も可
- **マテリアルから (From Material)** — picks from the active object's material. / アクティブなオブジェクトのマテリアルから取り込み
  - A selected RGB node wins. / RGBノードを選択中ならその色
  - Otherwise follows the target (Base / Emission). / それ以外は、選んでいる適用先(Base / Emission)の色

### Edit / 編集する

Turn on **編集モード (Edit Mode)** to rename, reorder (▲▼) and delete (×). Click a swatch to change its color (works outside Edit Mode too).
「編集モード」をオンにすると、名前の変更・▲▼で並べ替え・×で削除ができます。色見本をクリックすれば色も変えられます(編集モード外でも可)。

### Palettes / パレット(案件ごと)

The add-on starts with no palettes. Add colors, or import a palette file.
アドオンは空の状態から始まります。色を追加するか、パレットのファイルを読み込んでください。

- Switch with the dropdown at the top. / 上部のドロップダウンで切り替え
- **＋** — new palette (duplicates get a number, e.g. `案件A 2`). / 新規作成(同名なら「案件A 2」のように連番)
- **Import (↓)** — load palettes from a JSON file (same format as `palettes.json`). If a palette with the same name exists, choose **別名で追加 (Add as new)** or **置き換える (Replace)** in the file browser's side panel.
  JSONファイルからパレットを読み込み(`palettes.json` と同じ形式)。同じ名前のパレットがあるときは、ファイル選択画面の右側で「別名で追加」か「置き換える」を選べます。
- **Trash** — delete the shown palette (with confirmation; not undoable). / 表示中のパレットを削除(確認あり・Ctrl+Z では戻せません)

## Data / データ

- Saved to `~/BlenderColorClip/palettes.json` (Windows: `C:\Users\<user>\BlenderColorClip\`), shared across Blender versions.
  保存先は `~/BlenderColorClip/palettes.json`(Windows: `C:\Users\<ユーザー名>\BlenderColorClip\`)。Blenderのバージョンに依存しません。
- HEX is stored as sRGB and converted to linear inside Blender (matches the HEX shown in Blender's color picker).
  HEXは sRGB として保存し、Blender内部ではリニアに変換します(カラーピッカーのHEX表示と一致)。
- Safe with two Blenders open at once: changes are merged on save and picked up about every 2 seconds. Each Blender keeps its own shown palette.
  Blenderを2つ同時に開いても変更は消えません(保存前に読み直し、約2秒ごとに相手の変更を反映)。表示中のパレットはそれぞれ独立。
- Saves go through a temp file, so a crash mid-write won't corrupt the file.
  保存は一時ファイル経由なので、書き込み途中で落ちても壊れません。
- Unreadable JSON is moved to `palettes.json.bak` and reset. If only some entries are invalid, those are skipped and the original is copied to `.bak`.
  読めないJSONは `palettes.json.bak` に退避して初期化。一部だけ不正な場合はその項目のみ除外し、元ファイルを `.bak` にコピーします。
- Unknown keys (e.g. added by an AE script) are kept.
  未知のキー(AE側などで追加したもの)は消さずに保持します。

```json
{
  "active": "Project A",
  "palettes": {
    "Project A": [
      { "name": "Main", "hex": "#C7C3E1" },
      {
        "name": "Group 1", "hex": "#90EE90",
        "children": [
          { "name": "Member A", "hex": "#F32836" },
          { "name": "Member B", "hex": "#8FD400" }
        ]
      }
    ]
  }
}
```

## Notes / 補足

- If two Blenders save within the same instant (under ~1 s), one change may be lost.
  2台がほぼ同時(1秒未満の差)に保存すると、片方の変更が負ける可能性があります。
- Tests: see [`tests/`](../tests/). / テストは [`tests/`](../tests/) を参照。

## Ideas / 今後の候補

- Shared-drive storage for the team. / 保存先を共有ドライブにしてチームで共有
- AE JSX that reads the same `palettes.json`. / 同じ `palettes.json` を読む AE用JSXで Blender⇔AE を共通化

## Changelog / 更新履歴

- **0.3.0**
  - Sub-colors under each color (▶ to open). / 色の下にサブカラー(▶ で開閉)
  - Import palettes from JSON. / JSONからパレットを読み込み
  - No built-in palette; starts empty. / 内蔵パレットを廃止し、空の状態から開始

- **0.2.0**
  - Renamed to C7 Color Clip. / C7 Color Clipに改名
  - Robust against partly invalid JSON. / 中身が不正なJSONでも落ちないように(不正項目のみ除外、元ファイルは .bak)
  - Safe with two Blenders open. / Blender 2つ同時使用時に変更が消えないように
  - Atomic save via temp file. / 保存を一時ファイル経由にして、書き込み途中で落ちても壊れないように
  - Debounced saving while dragging swatches (0.5 s). / 色見本ドラッグ中の保存を間引き(最後の操作から0.5秒後)
  - From Material follows the target (Base / Emission). / 「マテリアルから」が適用先(Base / Emission)に合わせて色を取得
- **0.1.0** — First version. / 初版

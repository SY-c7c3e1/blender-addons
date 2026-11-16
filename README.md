# blender-addons

Blender add-ons by **c7** (Yumi).
c7(ユミ)が制作したBlenderアドオン集です。

## Add-ons / アドオン一覧

| Add-on | Description | 説明 |
|---|---|---|
| [C7 Render Folder](c7_render_folder/) | Sets the render output to `base/name/name_####` and creates the folder automatically. | 連番書き出し先を `保存先/名前/名前_####` に自動設定。フォルダも自動作成。 |
| [C7 Color Clip](c7_color_clip/) | Per-project color palettes: copy HEX and apply colors to materials in one click. | 案件ごとのカラーパレットから、HEXコピーやマテリアルへの色の適用をワンクリックで。 |

## Install / インストール

1. Zip the add-on folder (e.g. `c7_render_folder/` → `c7_render_folder.zip`).
   アドオンのフォルダ(例:`c7_render_folder/`)をzipにまとめます。
2. In Blender: **Edit > Preferences > Add-ons > ∨ (top right) > Install from Disk...** and select the zip.
   Blenderで **編集 > プリファレンス > アドオン > 右上の∨ > ディスクからインストール** を選び、zipを指定します。
3. Enable the add-on with the checkbox.
   チェックを入れて有効化します。

## Tested / 動作確認

- C7 Render Folder: Blender 5.2.3 LTS
- C7 Color Clip: Blender 4.2.23 LTS / 5.3.0 (automated tests in [`tests/`](tests/) / 自動テストは [`tests/`](tests/))

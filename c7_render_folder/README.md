# C7 Render Folder

Sets the render output path to `base/name/name_####` so each image sequence gets its own folder automatically.
連番書き出しの出力パスを `保存先/名前/名前_####` に自動設定し、名前ごとのフォルダを自動で作成します。

## Location / 場所

**Properties > Output > C7 Render Folder**
**プロパティ > 出力 > C7 Render Folder**

## Usage / 使い方

| Field | Description | 説明 |
|---|---|---|
| 保存先 (Base folder) | Parent folder. Saved in the .blend. Default `//render/`. | 親フォルダ。.blendに保存されます。初期値 `//render/` |
| 名前 (Name) | **任意 (Custom)**: type a name / **選択中のコレクション (Active collection)**: uses the active collection's name | **任意**:手入力 / **選択中のコレクション**:アウトライナーでアクティブなコレクション名 |

- **出力パスに適用 (Apply)** — sets the output path only (render later with Ctrl+F12).
  出力パスだけ設定します(あとからCtrl+F12でレンダリング)。
- **適用して連番レンダリング (Apply & Render)** — sets the path and starts rendering the animation.
  パスを設定してアニメーションレンダリングを開始します。

Example / 例: name `shotA` → `//render/shotA/shotA_0001.png`

## Notes / 補足

- Characters `\ / : * ? " < > | { }` in the name are replaced with `_` (`{}` would be read as Blender 5.x path variables).
  名前に含まれる `\ / : * ? " < > | { }` は `_` に置き換えます(`{}` はBlender 5.xのパス変数として解釈されるため)。
- Existing files follow Blender's own **Overwrite** setting.
  既存ファイルの扱いはBlender標準の「上書き」設定に従います。

## Changelog / 更新履歴

- **1.1.0** — Renamed to C7 Render Folder. / C7 Render Folderに改名
- **1.0.1** — Fixed `//` relative path warning; trimmed extra underscores. / `//` 相対パスの警告を修正、余分な `_` を除去
- **1.0.0** — First version. / 初版

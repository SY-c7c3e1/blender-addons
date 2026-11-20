# C7 Text Tools

Text tools for Japanese titles in Blender: kana scaling, per-character adjustments, skew, stroke outlines, splitting into per-character objects, and a font preview.
Blenderで日本語の文字を作るためのツール集です。かなの縮小、1文字ずつの調整、斜体（Skew）、線だけのアウトライン、1文字ずつのバラし、フォントプレビューをまとめています。

Replaces **C7 Kana Scale** and **C7 Font Preview** (disable and remove them before installing).
**C7 Kana Scale** と **C7 Font Preview** をまとめたものです。入れる前に、この2つは無効化して削除してください。

## Location / 場所

**3D Viewport > Sidebar (N) > C7**
**3Dビュー > サイドバー(Nキー) > C7**

Panels / パネル: **C7 Text(かなスケール)** → **C7 アウトライン** → **C7 Font Preview**

## Usage / 使い方

### Kana Scale text / かなスケールのテキスト

**かなスケールテキストを追加 (Add)** creates a curve text at the 3D cursor. Hiragana, katakana and symbols can each have their own size.
「追加」で3Dカーソルの位置に文字（カーブ）を作ります。平仮名・カタカナ・記号のサイズを、それぞれ別に変えられます。

- Type the text in the panel. Use `\n` for a line break. / 文字はパネルで入力。改行は `\n`
- Modifiers, materials and animation are kept when the text changes, so it works on a path too. / 文字を変えてもモディファイア・マテリアル・アニメーションはそのまま。パスに沿わせても使えます
- **傾き（全体）(Skew)** — italic-like slant; each character leans on its own baseline. / イタリック風の傾き。各文字は自分の足元を軸に傾きます
- **文字種ごとにマテリアル番号を分ける** — material index per kind (0: kanji etc. / 1: hiragana / 2: katakana / 3: symbols). / 文字種ごとにマテリアル番号を分けます

### Per-character adjust / 1文字ずつの調整

Click a character button (or set the number) to pick a character, then change:
文字ボタンを押す（または番号を入れる）と、その文字だけ調整できます。

- **高さ (Rise)** — move up/down (1.0 = one full-width character). / 上下に移動（全角1文字分＝1.0）
- **傾き (Skew)** — extra slant added to the overall skew. / 全体の傾きに足す傾き
- **サイズ (Size)** — multiplied by the kind's size. / 文字種のサイズに掛け算
- **次の文字との間 (Kerning)** — space to the next character. / 次の文字との間隔

Adjusted characters are marked with `•` and listed below; × resets one, the trash button resets all.
調整済みの文字には `•` が付き、下に一覧が出ます。× で1文字、ゴミ箱で全部を元に戻せます。

### Send a normal text object / 普通のテキストから送る

Select a normal text object to show two buttons. Text, font, size, shear, alignment, line spacing, origin offset, transform, parent, materials, extrude/bevel, modifiers and outline are carried over. The original text is hidden, not deleted.
普通のテキストを選ぶと2つのボタンが出ます。文字・フォント・サイズ・傾き・揃え・行間・原点のずらし・位置/回転/拡大・親・マテリアル・押し出し/ベベル・モディファイア・アウトラインを引き継ぎます。元のテキストは削除せず非表示にします。

- **かなスケールへ送る** — convert to Kana Scale text. / かなスケールに変換
- **バラ文字へ送る** — convert and split at once. / 変換して、そのままバラします

### Split into characters / 1文字ずつバラす

**1文字ずつバラす** puts each character into its own object.
「1文字ずつバラす」で、1文字ずつ別のオブジェクトにします。

- A new collection `{text}_split` holds an empty and the characters (children of the empty). / 新しいコレクション `{テキスト}_split` に、エンプティと各文字（エンプティの子）が入ります
- The empty sits at the center of all characters, with the source's rotation and scale. / エンプティは文字全体の中心。向きと拡大は元のテキストと同じ
- Each character's origin is its own center; names are `{text}_01_ラ`, `{text}_02_イ` … / 各文字の原点は文字の中心。名前は `{テキスト}_01_ラ` のように付きます
- Characters do not move. Modifiers (e.g. a path) and outlines are carried over. / 文字の位置は変わりません。モディファイア（パスなど）とアウトラインも引き継ぎます
- The source is hidden, not deleted: fix it and split again if needed. / 元のテキストは非表示で残るので、直してバラし直せます

### Outline / アウトライン

**アウトラインを追加** adds a stroke-only object (no fill, like AE "Stroke only") as a child of the text. Works on Kana Scale text and normal text objects.
「アウトラインを追加」で、輪郭の線だけのオブジェクト（塗りなし。AEの「線のみ」と同じ）を、テキストの子として作ります。かなスケールにも普通のテキストにも使えます。

- **線の太さ (Width)** — relative to the character size (0.1 = 10%). The line is centered on the contour. / 文字サイズに対する割合（0.1＝10%）。線は輪郭の真ん中に乗ります
- **色 (Color)** / **奥へずらす (Depth)** — color, and distance behind the text. / 色と、文字の後ろに置く距離
- Follows text, font, adjustments and modifiers automatically. / 文字・フォント・調整・モディファイアの変更に自動で追従
- For normal text, changes apply after leaving Edit Mode (Tab). / 普通のテキストは、編集モード(Tab)を抜けたときに反映
- Hide the text or the outline to render them separately for AE. / 文字とフチを片方ずつ非表示にすれば、AE用に別々にレンダーできます

### Font Preview / フォントプレビュー

Type any text and browse installed fonts as thumbnails.
好きな文字を入れて、インストール済みのフォントをサムネイルで一覧できます。

- **Font name button (✓)** — apply to the selected texts (normal and Kana Scale). / フォント名のボタン(✓)で、選択中のテキストに適用（普通・かなスケール両方）
- **＋** — new text object with the preview text and that font, named `{text}_text`. / プレビューの文字とそのフォントで新しいテキスト（名前は `{テキスト}_text`）
- **★** — favorite. / お気に入り
- **選択テキストに反映** — put the preview text into the selected texts. / プレビューの文字を、選択中のテキストの中身にする
- **Eyedropper** — take the text from the active object. / スポイトで、選択中のテキストの文字を取り込み
- Filter by category (Japanese / Gothic-Sans / Mincho-Serif / Brush-Script / Display / Mono), Japanese-only toggle and search. / カテゴリ（日本語・ゴシック・明朝・筆・装飾・等幅）、「日本語」ボタン、名前検索で絞り込み
- Missing characters are not faked with a fallback font; they are listed in red (`未対応:`). / フォントにない文字は代わりのフォントで補わず、赤字で「未対応:」と表示
- Only the current page is rendered (12 by default) to stay light. / 軽くするため、表示中のページ分（初期値12個）だけ描画

## Naming / 名前の付け方

| Created by / 作り方 | Name / 名前 |
|---|---|
| Font Preview ＋ | `{text}_text` |
| Kana Scale add / send / かなスケールの追加・送る | `{text}_kana` |
| Split / バラす | `{text}_split`, `{text}_01_会` … |
| Outline / アウトライン | `{name}_outline` |

Kana Scale names follow the text until you rename them yourself. Line breaks become spaces; long names are cut at Blender's 63-byte limit.
かなスケールの名前は、自分で変えるまで文字に合わせて変わります。改行は空白になり、長い名前はBlenderの上限（63バイト）で切ります。

## Data / データ

Font Preview keeps its cache and favorites in Blender's config folder: `<config>/c7_font_preview/` (`font_cache.json`, `favorites.json`).
フォントプレビューのキャッシュとお気に入りは、Blenderの設定フォルダ `<config>/c7_font_preview/` に保存します。

## Notes / 補足

- Fonts: `C:\Windows\Fonts` and the user font folder. Adobe Fonts activated via Creative Cloud are not listed. / 対象フォントは `C:\Windows\Fonts` とユーザーフォント。Creative Cloud でアクティベートした Adobe Fonts は出ません
- Kana Scale text is a curve, so it cannot be typed in Edit Mode (Tab). / かなスケールはカーブなので、編集モード(Tab)での直接入力はできません
- Split characters do not follow later edits of the source. / バラした文字は、元テキストの後からの修正には追従しません
- Kana Scale outlines are flat (no extrude). / かなスケールのフチには厚みが付きません
- Tests: see [`tests/`](../tests/). / テストは [`tests/`](../tests/) を参照

## Changelog / 更新履歴

- **0.8.4** — Merged C7 Kana Scale and C7 Font Preview into one add-on. / C7 Kana Scale と C7 Font Preview を統合
  - Per-character rise / skew / size, overall skew. / 1文字ずつの高さ・傾き・サイズ、全体の傾き
  - Stroke-only outline that follows the text. / 文字に追従する、線だけのアウトライン
  - Split into per-character objects (empty at the center, collection). / 1文字ずつバラす（中心にエンプティ、コレクションにまとめる）
  - Send normal text objects to Kana Scale / split. / 普通のテキストからかなスケール・バラ文字へ送る
  - Font Preview: apply preview text, new text from a font. / フォントプレビュー：文字の反映、フォントから新規テキスト
  - Text-based object names. / 文字ベースのオブジェクト名
- C7 Kana Scale 0.2.0 / C7 Font Preview 1.0.1 — previous separate add-ons. / 以前の個別アドオン

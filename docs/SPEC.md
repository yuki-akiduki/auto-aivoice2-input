# AIVoice2 テキスト自動入力ツール — 仕様書

## 概要

AIVoice2 Editor（A.I.VOICE2、Flutter製Windows TTS アプリ）に、台本ファイルからテキストとキャラクター設定を自動入力するデスクトップツール。

## 技術スタック

| 項目 | 技術 |
|------|------|
| 言語 | Python 3.10+ |
| GUI | pywebview（HTML/CSS/JSをネイティブウィンドウで表示） |
| UI自動化 | pyautogui（クリック・キーボード）+ pyperclip（クリップボード）|
| Win32 API | ctypes（SetForegroundWindow, EnumWindows, GetWindowRect, PrintWindow等）|
| フォント | Sora + Zen Kaku Gothic New + IBM Plex Mono |

## ファイル構成

```
E:\_dev\auto-aivoice2-input\
├── auto_aivoice2/
│   ├── __init__.py
│   ├── __main__.py          # エントリポイント（python -m auto_aivoice2）
│   ├── automation.py        # UI自動化ロジック（★核心）
│   ├── gui.py               # pywebview GUI + JS API ブリッジ
│   └── web/
│       └── index.html       # フロントエンド（HTML/CSS/JS 単一ファイル）
├── docs/
│   ├── DESIGN.md            # 設計書
│   ├── DESIGN_v2.md         # v2追加機能設計
│   ├── TASK.md              # タスクリスト
│   ├── HANDOFF.md           # 引き継ぎ資料（未解決バグの詳細）
│   └── SPEC.md              # この仕様書
├── sample/
│   ├── 台本サンプル_96行.txt
│   └── 台本サンプル_96行_names.txt  # 短縮名版（葵、茜 等）
├── user/
│   └── 2.0/
│       └── characters.vpcx  # AIVoice2キャラクター設定エクスポート（JSON）
├── calibration.json         # キャリブレーション保存データ
├── start.vbs                # ダブルクリック起動（黒窓なし）
├── run_automation.py        # CLIスタンドアロン版（安定動作する参照実装）
└── debug/                   # デバッグ用スクショ保存先
```

## AIVoice2 Editor について

- **開発元**: エーアイ社
- **アプリ種別**: Flutter製 Windows デスクトップアプリ
- **ウィンドウクラス**: `FLUTTER_RUNNER_WIN32_WINDOW`
- **ウィンドウタイトル**: `A.I.VOICE2 Editor - (プロジェクト名)`
- **UIA（UI Automation）**: Flutterのため pywinauto のUIA バックエンドはハングする。使用不可。
- **制御方法**: pyautogui によるマウスクリック + キーボード操作のみ

### AIVoice2 の UI 構成

```
┌──────────────────────────────────────────────────┐
│ タイトルバー / メニューバー                       │
├──────────┬───────────────────────┬────────────────┤
│ サイドバー │ テキストリスト         │ キャラ画像     │
│ ┌────────┐│ ┌───────────────────┐│                │
│ │検索ボックス││ │エントリ1          ││                │
│ ├────────┤│ │ キャラ名           ││                │
│ │キャラ一覧 ││ │ テキスト           ││                │
│ │ 葵_普通  ││ ├───────────────────┤│                │
│ │ 茜_普通  ││ │エントリ2          ││                │
│ │ 詞音_普通││ │ ...               ││                │
│ └────────┘│ └───────────────────┘│                │
├──────────┴───────────────────────┴────────────────┤
│ 再生/書き出しボタン / アクセント編集               │
└──────────────────────────────────────────────────┘
```

## 台本ファイル形式

```
キャラ名：セリフ
```

- 区切り: 全角コロン`：`または半角コロン`:`
- 空行・`#`で始まる行はスキップ
- キャラ名はVPCXのキャラ名と完全一致、または前方一致でマッピング
  - 完全一致: `葵_普通：こんにちは` → そのまま
  - 前方一致: `葵：こんにちは` → `葵_普通` にマッピング（VPCXで`葵`で始まるキャラの先頭）
  - 不一致: GUI上で手動マッピングまたはスキップ

## VPCXファイル（characters.vpcx）

AIVoice2からエクスポートしたキャラクター設定ファイル。JSON形式。

```json
{
  "version": "2.0",
  "characters": [
    {
      "name": "葵_普通",
      "voice": "KotonohaAoi_ns_48",
      "userCustom": true,
      "tuning": { "volume": 1.25, "speed": 1.15, ... },
      ...
    }
  ]
}
```

- `userCustom: true` — ユーザーが作成したボイスプリセット
- `userCustom: false` — 標準ボイス
- GUI上で「標準ボイスを含める」チェックボックスで切替可能

## キャリブレーション

AIVoice2のUI要素の位置をユーザーが手動で記録する機能。

### 記録する位置（4箇所）
1. **search_box** — サイドバーの検索ボックス
2. **first_result** — 検索結果の1番目のキャラクター
3. **add_button** — ツールバーの「+」ボタン
4. **text_entry** — 1番目のテキスト入力エリア

### 記録方法
- GUI上で各ステップの「記録」ボタンをクリック
- 5秒カウントダウン後にマウス位置を記録
- AIVoice2ウィンドウ左上からの相対オフセット（ピクセル）として保存
- `calibration.json` に保存

## 自動化フロー（process_line）

### 1行あたりの操作手順

```
[初回のみ]
  テキストエリアクリック → テキストペースト → Ctrl+Q

[2行目以降]
  検索ボックスクリック → Ctrl+A → キャラ名ペースト → 0.35s待ち
  → 検索結果クリック → 0.2s待ち
  → 「+」クリック → 0.35s待ち
  → テキストペースト → 0.2s待ち
  → Ctrl+Q → 0.2s待ち

[同キャラ連続の場合]
  検索・選択・Ctrl+Qをスキップ（「+」→テキストのみ）
```

### Ctrl+Q の役割
- サイドバーで選択中のキャラクターを、テキストリストのアクティブエントリに適用する
- AIVoice2固有のショートカットキー

### 順序が重要
- **成功する順序**: 検索 → 選択 → 「+」 → テキスト → Ctrl+Q
- **失敗する順序**: 「+」 → 検索 → 選択 → Ctrl+Q → テキスト（Ctrl+Q後にフォーカスがずれてテキストが入らない）

## GUI 機能一覧

### メインページ
1. **ファイル選択** — 台本ファイル + VPCXファイルの参照ダイアログ
2. **標準ボイス切替** — チェックボックスでユーザーボイス/全ボイス切替
3. **キャラボイス設定** — 台本キャラ名とVPCXキャラ名のマッピング
   - 完全一致: 緑タグ
   - 前方一致（候補あり）: オレンジタグ + ドロップダウン
   - 不一致: 赤タグ + ドロップダウン
   - 各キャラに「⏭ スキップ」オプションあり
4. **ボイスプレビュー** — インラインテーブル + モーダル拡大表示
   - 列: #, 元キャラ, 割当ボイス, セリフ
   - 行単位でボイスバリエーション変更可能（プルダウン）
   - スキップ行はグレーアウト
5. **コントロール** — 開始 / 停止 / 再スタート(途中再開) ボタン
6. **進捗表示** — 進捗テキスト + 経過時間 + 残り時間 + プログレスバー
7. **ログ** — リアルタイムログ（OK/INFO/MAP/ERROR色分け）
8. **キャリブレーション** — 4箇所の位置記録UI
9. **ステータスバー** — AIVoice2接続状態（5秒ごと自動チェック）

### JS → Python API（pywebview js_api）

| メソッド | 説明 |
|---------|------|
| `load_script()` | ファイルダイアログ→台本パース→マッチング |
| `load_vpcx()` | ファイルダイアログ→VPCX読み込み→マッチング |
| `set_include_standard(bool)` | 標準ボイス表示切替 |
| `check_status()` | AIVoice2検出状態 |
| `has_calibration()` | キャリブレーション済みか |
| `get_calibration()` | キャリブレーションデータ取得 |
| `get_mouse_offset()` | 現在のマウス位置（AIVoice2相対） |
| `save_calibration(positions)` | キャリブレーション保存 |
| `get_voice_variants(name)` | キャラのボイスバリエーション一覧 |
| `start(mapping, overrides)` | 自動入力開始 |
| `stop()` | 自動入力停止 |
| `resume(mapping, overrides)` | 途中再開 |
| `get_messages()` | 進捗メッセージ取得（150msポーリング） |

### メッセージ型（msg_queue → get_messages）

| type | 説明 |
|------|------|
| `info` | 情報メッセージ |
| `ok` | 行処理完了 |
| `map` | キャラマッピング適用 |
| `error` | エラー |
| `progress` | 進捗更新（current, total, elapsed, line_index等） |
| `done` | 完了/停止（success, stopped_at, total_time等） |

## スレッド構成

```
メインスレッド: pywebview（WinForms メッセージポンプ）
├── JSブリッジスレッド: get_messages() 等のAPI呼び出し（150msごとに新規生成）
├── ワーカースレッド: run_automation()（自動化処理）
├── ESC監視スレッド: _esc_monitor()（ESCキー検出）
└── ステータスチェック: check_status()（5秒ごと）
```

## 既知の問題

### ★ pywebview フォーカス競合問題（未解決）

**症状**: pywebview GUI経由で自動化実行時、intermittentにキャラ検索・テキスト入力が失敗

**原因**: pywebviewのJSブリッジが150msごとに新Pythonスレッドを生成→ WinFormsの`Invoke()`→ メッセージポンプ→ pywebviewにフォーカスが一時的に奪われる→ Ctrl+AやCtrl+VがAIVoice2ではなくpywebviewに送られる

**ワークアラウンド**: `_take_screenshot()`（PrintWindow + PIL Image保存）をprocess_lineの最後に入れると安定（ファイルI/Oの約300msがブリッジスレッド完了の待ち時間として機能）

**詳細**: `docs/HANDOFF.md` 参照

### 解決候補（優先度順）
1. **自動化中はJSポーリングを停止** — `pollMessages()`の`setTimeout`を止める。進捗表示はなくなるが最も確実
2. **pywebviewウィンドウを最小化** — 自動化中は最小化して物理的にフォーカス競合を排除
3. **ポーリング間隔を延長** — 150ms→2000ms等に変更（頻度を下げる）
4. **tkinterに戻す** — WinFormsメッセージポンプを使わないため競合しない可能性
5. **Win32 SendMessageで直接送信** — pyautogui（フォアグラウンドウィンドウ依存）をやめ、hwnd直接指定でキー送信。Flutterで動くか未検証

## CLI版（参照実装）

`run_automation.py` — pywebviewなしで動作する安定版。96行テストで100%成功。

```bash
cd E:\_dev\auto-aivoice2-input
python run_automation.py sample/台本サンプル_96行_names.txt
```

※ このCLI版はキャリブレーション非対応（ハードコード座標）、キャラマッピング非対応

## 依存パッケージ

```
pyautogui
pyperclip
pywebview
pywin32
pythonnet
Pillow
```

# AIVoice2 テキスト自動入力ツール — 設計書

## 概要

台本ファイル（`キャラ名：セリフ` 形式）を読み込み、AIVoice2 Editorへの自動入力を行うWebベースGUIツール。

## アーキテクチャ

```
auto_aivoice2/
├── __init__.py
├── __main__.py          # エントリポイント（サーバー起動 + ブラウザオープン）
├── automation.py        # 自動化ロジック（run_automation.pyから移植）
├── server.py            # Flask HTTPサーバー + API
└── web/
    └── index.html       # GUI画面（HTML/CSS/JS単一ファイル）
start.vbs                # ダブルクリック起動（黒窓なし）
```

## 技術スタック

- **バックエンド**: Flask（Python）
- **フロントエンド**: HTML/CSS/JS（フレームワークなし）
- **UI自動化**: pyautogui + pyperclip + ctypes（Win32 API）
- **通信**: REST API + Server-Sent Events（SSE）

## API設計

| メソッド | パス | 説明 |
|---------|------|------|
| GET | / | index.html配信 |
| POST | /api/load-script | 台本ファイル読み込み（ファイルダイアログ表示） |
| POST | /api/load-vpcx | VPCXファイル読み込み（ファイルダイアログ表示） |
| GET | /api/status | AIVoice2接続状態確認 |
| POST | /api/start | 自動入力開始（マッピング情報を受け取る） |
| POST | /api/stop | 自動入力停止 |
| GET | /api/events | SSE（進捗・ログのリアルタイム通知） |

## 自動化フロー（1行あたり）

1. 検索ボックスクリック → Ctrl+A → キャラ名ペースト
2. 検索結果の1番目をクリック
3. 「+」ボタンクリック
4. テキストペースト
5. Ctrl+Q でキャラ確定

## キャラクターマッチング

1. VPCXからキャラ一覧を取得
2. 台本のキャラ名をVPCXと照合:
   - **完全一致**: そのまま使用（緑）
   - **部分一致**: 前方一致する候補を提示（オレンジ）例: `詞音` → `詞音_普通`
   - **不一致**: 手動でマッピング（赤）
3. ユーザーがGUIでマッピングを確認・修正してから実行

## スレッド構成

- メインスレッド: Flask HTTPサーバー
- ワーカースレッド: 自動化処理（process_line ループ）
- threading.Event: 停止通知
- queue.Queue: ワーカー → SSE メッセージ

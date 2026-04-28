# 実装タスクリスト

## Task 1: automation.py — ロジック抽出
- [x] run_automation.py から関数を移植
  - find_aivoice2, get_window_pos, click, paste, process_line, parse_script, POS
  - DPI対応コード
- [ ] VPCXファイル読み込み関数 (load_vpcx)
- [ ] キャラクターマッチング関数 (match_characters)
- [ ] stop_event 対応（各行処理前にチェック）
- [ ] コールバック/キュー対応（進捗通知）

## Task 2: server.py — HTTPサーバー + API
- [ ] Flask アプリ作成
- [ ] GET / — index.html配信
- [ ] POST /api/load-script — ファイルダイアログ + パース + レスポンス
- [ ] POST /api/load-vpcx — ファイルダイアログ + パース + レスポンス
- [ ] GET /api/status — AIVoice2検出状態
- [ ] POST /api/start — ワーカースレッド起動（マッピング情報受取）
- [ ] POST /api/stop — 停止フラグ設定
- [ ] GET /api/events — SSEストリーム

## Task 3: web/index.html — フロントエンド接続
- [ ] 参照ボタン → /api/load-script, /api/load-vpcx 呼び出し
- [ ] レスポンスで台本テーブル・キャラタグ・マッピングUI動的生成
- [ ] 開始ボタン → /api/start（マッピング情報送信）
- [ ] 停止ボタン → /api/stop
- [ ] SSE受信 → 進捗バー・ログ・テーブルハイライト更新
- [ ] AIVoice2接続状態の定期チェック

## Task 4: エントリポイント + 起動スクリプト
- [ ] __init__.py
- [ ] __main__.py（サーバー起動 + ブラウザ自動オープン）
- [ ] start.vbs（pythonw経由、黒窓なし）

## Task 5: 検証
- [ ] start.vbs ダブルクリック → ブラウザ表示
- [ ] 台本読み込み → プレビュー表示
- [ ] VPCX読み込み → キャラ検証 + マッピング表示
- [ ] 3行テスト → 進捗リアルタイム表示
- [ ] 停止ボタンで途中停止
- [ ] 96行完走テスト

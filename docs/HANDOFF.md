# 引き継ぎ資料 — AIVoice2 テキスト自動入力ツール

## 現状のステータス

### 動くもの
- **CLIから直接実行（pywebviewなし）**: 96行テスト完走、100%成功。`run_automation.py`がオリジナル。
- **pywebview GUI**: ファイル選択、キャラマッピング、ボイスプレビュー等のUI機能は動作
- **`_take_screenshot()`をprocess_lineの最後に入れた場合**: pywebview GUI経由でも安定動作（95行完走確認済み）

### 未解決の問題
**pywebview GUI経由で自動化を実行すると、intermittentにキャラ検索とテキスト入力が失敗する。**

具体的な症状:
1. 検索ボックスに前のキャラ名が残り、新しいキャラ名が結合される（例: "茜_普通詞音_普通"）
2. テキストが入力されない（空のエントリができる）
3. キャラが間違って割り当てられる

## 根本原因（分析済み）

**pywebviewのJSブリッジスレッドとの競合。**

- JSの`pollMessages()`が150msごとに`api().get_messages()`を呼ぶ
- pywebviewはこの呼び出しごとに**新しいPythonスレッド**を生成する
- そのスレッドが`evaluate_js()`→ WinFormsの`Invoke()`を呼ぶ
- `Invoke()`がWindowsメッセージポンプを動かし、**pywebviewウィンドウにフォーカスが一時的に奪われる**
- その瞬間にCtrl+AやCtrl+Vが送られるとAIVoice2ではなくpywebviewに行く

### なぜ`_take_screenshot()`で安定するか
- `img.save()`のファイルI/Oに約200-300msかかる
- この間、自動化スレッドはI/Oで待機し、キーボード/クリップボード操作をしない
- pywebviewのブリッジスレッドが完了してフォーカスが安定する時間ができる

### 試したが効果がなかった対策
1. `time.sleep(0.3)` — 単純なスリープだけでは不十分
2. `_touch_window()` — PrintWindow API + GetBitmapBitsだけでは不十分（ファイルI/Oがない）
3. 各操作前に`SetForegroundWindow(hwnd)` — pywebviewがすぐフォーカスを奪い返す
4. `Home + Shift+End`でのテキスト選択 — Ctrl+Aの代替、効果なし
5. 検索ボックスのCtrl+C読み返し検証 — クリップボードが前回のcopyの内容のまま（偽陽性）
6. Ctrl+A 2回送信 — 効果なし
7. 検索ボックス2回クリック — 効果なし

## ファイル構成

```
auto_aivoice2/
├── __init__.py
├── __main__.py          # エントリポイント
├── automation.py        # 自動化ロジック（問題はここ）
├── gui.py               # pywebview GUI + API
└── web/
    └── index.html       # HTML/CSS/JS フロントエンド
```

## 自動化フロー（process_line）

```
1. キャラ検索: 検索ボックスクリック → Ctrl+A → キャラ名ペースト → 0.35s待ち
2. 検索結果クリック → 0.2s待ち
3. 「+」で追加 → 0.35s待ち
4. テキストペースト → 0.2s待ち
5. Ctrl+Q → 0.2s待ち
```

## 解決候補（未実装）

### 案1: 自動化中はポーリングを停止
JSの`pollMessages()`を自動化中は一時停止する。進捗表示はできなくなるが、ブリッジスレッドの競合がなくなる。

### 案2: pywebviewウィンドウを最小化
自動化開始時にpywebviewを最小化し、完了後に復元。フォーカス競合を物理的に排除。

### 案3: pywebviewをやめてtkinterに戻す
tkinterはWinFormsメッセージポンプを使わないため、フォーカス競合が発生しない可能性。ただしUI品質が下がる。

### 案4: FlaskベースでブラウザTab化
`http://localhost:5000`をブラウザで開く形式にする。ブラウザタブはデスクトップアプリと違いフォーカス競合しにくい。

### 案5: ポーリングをWebSocketに変更
150msごとのAPI呼び出し（スレッド生成）をやめ、サーバープッシュ型にする。

## キャリブレーション

AIVoice2のUI座標をユーザーが手動記録する機能。`calibration.json`に保存。
- search_box: 検索ボックス
- first_result: 検索結果の1番目
- add_button: ツールバーの「+」
- text_entry: 1番目のテキスト入力エリア

## 台本形式

```
キャラ名：セリフ
```
全角コロン(：)または半角コロン(:)で区切り。キャラ名はVPCXファイルのキャラ名と一致または前方一致でマッピング。

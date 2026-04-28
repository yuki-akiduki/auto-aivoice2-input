"""AIVoice2 自動入力 — 自動化ロジック"""
import json
import time
import ctypes
import ctypes.wintypes
import pyautogui
import pyperclip
import threading
import queue
from pathlib import Path

# DPIスケーリング対応（run_automation内で呼ぶ）
_dpi_set = False

def _ensure_dpi():
    global _dpi_set
    if _dpi_set:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    _dpi_set = True

# Win32 API
EnumWindows = ctypes.windll.user32.EnumWindows
GetWindowTextW = ctypes.windll.user32.GetWindowTextW
IsWindowVisible = ctypes.windll.user32.IsWindowVisible
GetWindowRect = ctypes.windll.user32.GetWindowRect
SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
WNDENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
)

# キャリブレーションファイルパス
CALIBRATION_FILE = Path(__file__).parent.parent / "calibration.json"

# デフォルトのUI座標オフセット
DEFAULT_POS = {
    "search_box":   [143, 134],
    "first_result": [160, 247],
    "add_button":   [362, 137],
    "text_entry":   [500, 200],
}


def load_calibration():
    """キャリブレーションファイルを読み込む。なければデフォルトを返す"""
    if CALIBRATION_FILE.exists():
        with open(CALIBRATION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("positions", DEFAULT_POS)
    return DEFAULT_POS.copy()


def save_calibration(positions):
    """キャリブレーションデータを保存"""
    data = {"positions": positions}
    with open(CALIBRATION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def has_calibration():
    """キャリブレーション済みかどうか"""
    return CALIBRATION_FILE.exists()


# ─── AIVoice2 ウィンドウ操作 ───

def find_aivoice2():
    """AIVoice2 Editorのウィンドウハンドルとタイトルを返す"""
    result = []
    def callback(hwnd, _):
        if IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            GetWindowTextW(hwnd, buf, 512)
            if "A.I.VOICE2 Editor" in buf.value:
                result.append((hwnd, buf.value))
        return True
    EnumWindows(WNDENUMPROC(callback), 0)
    return result[0] if result else (None, None)


def get_window_pos(hwnd):
    """ウィンドウの左上座標を返す"""
    rect = ctypes.wintypes.RECT()
    GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top


def click_pos(name, wl, wt, positions):
    """名前付きUI位置をクリック"""
    ox, oy = positions[name]
    pyautogui.click(wl + ox, wt + oy)


def paste(text):
    """クリップボード経由でテキストをペースト"""
    pyperclip.copy(text)
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "v")


# ─── 台本パース ───

def parse_script(filepath):
    """台本ファイルをパースして [(character, text), ...] を返す"""
    lines = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for delim in ["：", ":"]:
                if delim in line:
                    char, text = line.split(delim, 1)
                    lines.append((char.strip(), text.strip()))
                    break
    return lines


# ─── VPCX読み込み ───

def load_vpcx(filepath):
    """VPCXファイルを読み込んでキャラクター情報を返す

    Returns:
        {
            "all": [{"name": "葵_普通", "userCustom": True}, ...],
            "user": ["葵_普通", ...],
            "standard": ["琴葉 茜(NV)", ...],
        }
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    chars = data.get("characters", [])
    return {
        "all": [{"name": c["name"], "userCustom": c.get("userCustom", False)} for c in chars],
        "user": [c["name"] for c in chars if c.get("userCustom", False)],
        "standard": [c["name"] for c in chars if not c.get("userCustom", False)],
    }


# ─── キャラクターマッチング ───

def match_characters(script_lines, vpcx_characters):
    """台本のキャラ名をVPCXのキャラ名と照合する"""
    script_chars = list(dict.fromkeys(char for char, _ in script_lines))
    vpcx_set = set(vpcx_characters)

    exact = []
    partial = {}
    unmatched = []
    auto_mapping = {}

    for sc in script_chars:
        if sc in vpcx_set:
            exact.append(sc)
        else:
            candidates = [vc for vc in vpcx_characters if vc.startswith(sc)]
            if candidates:
                partial[sc] = candidates
                auto_mapping[sc] = candidates[0]
            else:
                unmatched.append(sc)

    return {
        "exact": exact,
        "partial": partial,
        "unmatched": unmatched,
        "auto_mapping": auto_mapping,
    }


SKIP = "__SKIP__"


def get_voice_variants(base_name, vpcx_characters):
    """キャラのベース名からボイスバリエーション一覧を返す"""
    return [vc for vc in vpcx_characters if vc.startswith(base_name.split("_")[0])]


DEBUG_DIR = Path(__file__).parent.parent / "debug"
PrintWindow = ctypes.windll.user32.PrintWindow


def _touch_window(hwnd):
    """PrintWindow + ビットマップ読み込みでウィンドウを安定させる（保存なし）"""
    try:
        import win32gui
        import win32ui
        rect = ctypes.wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect))
        w = max(rect.right - rect.left, 1)
        h = max(rect.bottom - rect.top, 1)
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(bmp)
        PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
        # ビットマップデータを読み込む（スクショ保存時と同じ処理量を確保）
        bmp.GetBitmapBits(True)
        win32gui.DeleteObject(bmp.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
    except Exception:
        pass


def _take_screenshot(hwnd, label):
    """AIVoice2ウィンドウのスクリーンショットを撮って保存（PrintWindow API、マルチモニター対応）"""
    try:
        import datetime
        import win32gui
        import win32ui
        from PIL import Image

        rect = ctypes.wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(saveBitMap)

        PrintWindow = ctypes.windll.user32.PrintWindow
        PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)

        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)
        img = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
                               bmpstr, "raw", "BGRX", 0, 1)

        # ファイル名をASCII安全に
        safe_label = label.replace("/", "_").replace("\\", "_")
        ts = datetime.datetime.now().strftime("%H%M%S_%f")[:13]
        path = DEBUG_DIR / f"{ts}_{safe_label}.png"
        img.save(str(path))

        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)

        return str(path)
    except Exception as e:
        return f"スクショ失敗: {e}"


# ─── 自動入力処理 ───

def process_line(character, text, hwnd, positions, is_first=False, same_as_prev=False):
    """AIVoice2に1行を入力する。

    正しい操作順序:
      初回: 検索 → 選択 → Ctrl+Q → テキスト
      2行目以降: 「+」 → 検索クリア(BS) → 検索 → 選択 → Ctrl+Q → テキスト
    """
    wl, wt = get_window_pos(hwnd)

    # 1. 「+」で新エントリ追加（初回はスキップ — 既存の空エントリを使う）
    if not is_first:
        click_pos("add_button", wl, wt, positions)
        time.sleep(0.3)

    # 2. キャラ検索・選択・確定（同キャラ連続はスキップ）
    if not same_as_prev:
        # 検索ボックスをクリック
        click_pos("search_box", wl, wt, positions)
        time.sleep(0.2)

        # Ctrl+A で全選択 → Backspace で消去
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)
        pyautogui.press("backspace")
        time.sleep(0.1)

        # キャラ名をペースト
        paste(character)
        time.sleep(0.3)

        # 検索結果の1番目をクリック（キャラ選択）
        click_pos("first_result", wl, wt, positions)
        time.sleep(0.2)

    # 3. Ctrl+Q でキャラをエントリに適用
    pyautogui.hotkey("ctrl", "q")
    time.sleep(0.2)

    # 4. テキストをペースト
    paste(text)
    time.sleep(0.2)

    return True


def _esc_monitor(stop_event):
    """ESCキーを監視するバックグラウンドスレッド"""
    GetAsyncKeyState = ctypes.windll.user32.GetAsyncKeyState
    VK_ESCAPE = 0x1B
    while not stop_event.is_set():
        if GetAsyncKeyState(VK_ESCAPE) & 0x8000:
            stop_event.set()
            return
        time.sleep(0.1)


MAX_LINES = None  # テスト用: 数値を設定すると行数制限（Noneで無制限）


def run_automation(script_lines, char_mapping, msg_queue, stop_event, overrides=None, start_from=0):
    """自動入力を実行する（別プロセスから呼ばれる前提）"""
    overrides = overrides or {}
    _ensure_dpi()
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05

    # キャリブレーション読み込み
    positions = load_calibration()

    hwnd, title = find_aivoice2()
    if not hwnd:
        msg_queue.put({"type": "error", "message": "A.I.VOICE2 が見つかりません"})
        msg_queue.put({"type": "done", "success": False})
        return

    total = len(script_lines)
    active_count = 0
    for i, (character, _) in enumerate(script_lines):
        if i < start_from:
            continue
        if i in overrides:
            resolved = overrides[i]
        else:
            resolved = char_mapping.get(character, character)
        if resolved and resolved != SKIP:
            active_count += 1

    if start_from > 0:
        msg_queue.put({"type": "info", "message": f"{start_from+1}行目から再開します ({active_count}行, {total - start_from - active_count}スキップ)"})
    else:
        msg_queue.put({"type": "info", "message": f"自動入力を開始します ({active_count}行, {total - active_count}スキップ)"})

    # カウントダウン
    for i in range(3, 0, -1):
        if stop_event.is_set():
            msg_queue.put({"type": "info", "message": "中止されました"})
            msg_queue.put({"type": "done", "success": False, "stopped_at": start_from})
            return
        msg_queue.put({"type": "info", "message": f"{i}秒後に開始..."})
        time.sleep(1)

    # AIVoice2をフォアグラウンドにする（1回だけ、CLI版と同じ）
    SetForegroundWindow(hwnd)
    time.sleep(0.5)

    start_time = time.time()
    processed = 0
    prev_character = None

    for i, (character, text) in enumerate(script_lines):
        if i < start_from:
            continue

        # MAX_LINES制限（テスト用）
        if MAX_LINES is not None and processed >= MAX_LINES:
            msg_queue.put({"type": "info", "message": f"テスト制限: {MAX_LINES}行で停止"})
            break

        if stop_event.is_set():
            elapsed = time.time() - start_time
            msg_queue.put({"type": "info", "message": f"停止しました ({processed}/{active_count}行完了, {elapsed:.1f}秒)"})
            msg_queue.put({"type": "done", "success": False, "completed": processed, "stopped_at": i})
            return

        if i in overrides:
            resolved_char = overrides[i]
        else:
            resolved_char = char_mapping.get(character, character)

        if resolved_char == SKIP or not resolved_char:
            msg_queue.put({"type": "info", "message": f"{i+1}/{total} ⏭ スキップ: {character}：{text[:20]}"})
            continue

        if resolved_char != character:
            msg_queue.put({"type": "map", "message": f"{i+1}/{total} {character} → {resolved_char}"})

        processed += 1
        elapsed = time.time() - start_time

        # 同一キャラ連続の場合、検索・選択・Ctrl+Qをスキップ
        same_as_prev = (prev_character is not None and resolved_char == prev_character)

        msg_queue.put({
            "type": "progress",
            "current": processed,
            "total": active_count,
            "elapsed": elapsed,
            "character": resolved_char,
            "text": text,
            "line_index": i,
        })

        process_line(resolved_char, text, hwnd, positions,
                     is_first=(processed == 1 and start_from == 0),
                     same_as_prev=same_as_prev)
        prev_character = resolved_char
        msg_queue.put({"type": "ok", "message": f"{processed}/{active_count} {resolved_char}：{text}"})

    total_time = time.time() - start_time
    per_line = total_time / processed if processed else 0
    msg_queue.put({
        "type": "info",
        "message": f"完了！ {processed}行 / {total_time:.1f}秒 / 1行あたり{per_line:.2f}秒"
    })
    msg_queue.put({"type": "done", "success": True, "total_time": total_time})

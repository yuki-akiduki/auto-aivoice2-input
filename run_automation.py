"""AIVoice2 自動入力 — 台本ファイルを読み込んで全行を自動入力する"""
import time
import sys
import ctypes
import ctypes.wintypes
import pyautogui
import pyperclip

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

EnumWindows = ctypes.windll.user32.EnumWindows
GetWindowTextW = ctypes.windll.user32.GetWindowTextW
IsWindowVisible = ctypes.windll.user32.IsWindowVisible
GetWindowRect = ctypes.windll.user32.GetWindowRect
SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
WNDENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
)

POS = {
    "search_box":   (143, 134),
    "first_result": (160, 247),
    "add_button":   (362, 137),
}


def find_aivoice2():
    result = []
    def callback(hwnd, _):
        if IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            GetWindowTextW(hwnd, buf, 512)
            if "A.I.VOICE2" in buf.value:
                result.append(hwnd)
        return True
    EnumWindows(WNDENUMPROC(callback), 0)
    return result[0] if result else None


def get_window_pos(hwnd):
    rect = ctypes.wintypes.RECT()
    GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top


def click(name, wl, wt):
    ox, oy = POS[name]
    pyautogui.click(wl + ox, wt + oy)


def paste(text):
    pyperclip.copy(text)
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "v")


def process_line(character, text, wl, wt):
    # 1. 検索ボックスでキャラ検索
    click("search_box", wl, wt)
    time.sleep(0.3)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    paste(character)
    time.sleep(0.5)

    # 2. 検索結果クリック
    click("first_result", wl, wt)
    time.sleep(0.3)

    # 3. 「+」で追加
    click("add_button", wl, wt)
    time.sleep(0.5)

    # 4. テキスト入力
    paste(text)
    time.sleep(0.3)

    # 5. Ctrl+Q でキャラ確定
    pyautogui.hotkey("ctrl", "q")
    time.sleep(0.3)


def parse_script(filepath):
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


def main():
    script_file = sys.argv[1] if len(sys.argv) > 1 else "script_large.txt"
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05

    lines = parse_script(script_file)
    total = len(lines)
    print(f"台本: {script_file} ({total}行)")

    hwnd = find_aivoice2()
    if not hwnd:
        print("A.I.VOICE2 が見つかりません")
        return

    print(f"5秒後に開始します。マウスを触らないでください。")
    print(f"緊急停止: マウスを画面左上隅に移動")
    for i in range(5, 0, -1):
        print(f"  {i}...")
        time.sleep(1)

    SetForegroundWindow(hwnd)
    time.sleep(0.5)
    wl, wt = get_window_pos(hwnd)

    start_time = time.time()

    for i, (character, text) in enumerate(lines):
        elapsed = time.time() - start_time
        print(f"[{i+1}/{total}] {character}：{text[:20]}... ({elapsed:.1f}s)")
        process_line(character, text, wl, wt)

    total_time = time.time() - start_time
    print(f"{'='*50}")
    print(f"完了！")
    print(f"  処理行数: {total}行")
    print(f"  合計時間: {total_time:.1f}秒 ({total_time/60:.1f}分)")
    print(f"  1行あたり: {total_time/total:.2f}秒")


if __name__ == "__main__":
    main()

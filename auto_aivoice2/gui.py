"""AIVoice2 テキスト自動入力 — pywebview GUI"""
import sys
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path

sys.setrecursionlimit(10000)

WEB_DIR = Path(__file__).parent / "web"
WORKER_MODULE = "auto_aivoice2.worker"


class Api:
    """pywebview の JS から呼び出せる Python API"""

    def __init__(self):
        self._window = None
        self.script_lines = []
        self.vpcx_chars = []
        self.vpcx_data = None
        self.match_result = None
        self.msg_queue = queue.Queue()
        self.running = False
        self._lock = threading.Lock()
        self.last_stopped_at = 0
        self._proc = None
        self._stop_path = None
        self._tmpdir = None

    def set_window(self, window):
        self._window = window

    # ─── ファイル読み込み ───

    def load_script(self):
        import webview
        from . import automation
        paths = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            directory=os.getcwd(),
            allow_multiple=False,
            file_types=("テキストファイル (*.txt)",),
        )
        if not paths:
            return {"error": "cancelled"}

        filepath = paths[0]
        self.script_lines = automation.parse_script(filepath)
        result = self._do_match()

        return {
            "path": filepath,
            "lines": [{"character": c, "text": t} for c, t in self.script_lines],
            "total": len(self.script_lines),
            "match": result,
        }

    def load_vpcx(self):
        import webview
        from . import automation
        paths = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            directory=os.getcwd(),
            allow_multiple=False,
            file_types=("VPCXファイル (*.vpcx;*.json)",),
        )
        if not paths:
            return {"error": "cancelled"}

        filepath = paths[0]
        self.vpcx_data = automation.load_vpcx(filepath)
        self.vpcx_chars = self.vpcx_data["user"]
        result = self._do_match()

        return {
            "path": filepath,
            "vpcx_data": self.vpcx_data,
            "characters": self.vpcx_chars,
            "total": len(self.vpcx_chars),
            "match": result,
        }

    def set_include_standard(self, include):
        """標準ボイスの表示切り替え"""
        if self.vpcx_data is None:
            return {"error": "VPCXが読み込まれていません"}
        if include:
            self.vpcx_chars = [c["name"] for c in self.vpcx_data["all"]]
        else:
            self.vpcx_chars = self.vpcx_data["user"]
        result = self._do_match()
        return {"characters": self.vpcx_chars, "match": result}

    def _do_match(self):
        from . import automation
        if self.script_lines and self.vpcx_chars:
            self.match_result = automation.match_characters(
                self.script_lines, self.vpcx_chars
            )
            return self.match_result
        return None

    # ─── キャリブレーション ───

    def has_calibration(self):
        from . import automation
        return automation.has_calibration()

    def get_calibration(self):
        from . import automation
        return automation.load_calibration()

    def get_mouse_offset(self):
        """現在のマウス位置をAIVoice2ウィンドウからのオフセットで返す"""
        from . import automation
        import pyautogui
        hwnd, _ = automation.find_aivoice2()
        if not hwnd:
            return {"error": "A.I.VOICE2 Editorが見つかりません"}
        mx, my = pyautogui.position()
        wl, wt = automation.get_window_pos(hwnd)
        return {"offset": [mx - wl, my - wt], "abs": [mx, my]}

    def save_calibration(self, positions):
        from . import automation
        automation.save_calibration(positions)
        return {"status": "saved"}

    # ─── ステータス ───

    def check_status(self):
        from . import automation
        hwnd, title = automation.find_aivoice2()
        return {"connected": hwnd is not None, "title": title or ""}

    # ─── ボイスバリエーション ───

    def get_voice_variants(self, base_name):
        from . import automation
        return automation.get_voice_variants(base_name, self.vpcx_chars)

    # ─── 自動入力（子プロセス方式） ───

    def _launch_worker(self, script_lines, char_mapping, int_overrides, start_from=0):
        """子プロセスでワーカーを起動し、進捗読み取りスレッドを開始する"""
        # debug/ ディレクトリに固定パスで保存（Claude側から読み取り可能）
        self._tmpdir = str(Path(__file__).parent.parent / "debug")
        os.makedirs(self._tmpdir, exist_ok=True)
        config_path = os.path.join(self._tmpdir, "config.json")
        progress_path = os.path.join(self._tmpdir, "progress.jsonl")
        self._stop_path = os.path.join(self._tmpdir, "stop")

        # 設定ファイル書き出し
        config = {
            "script_lines": script_lines,
            "char_mapping": char_mapping,
            "overrides": {str(k): v for k, v in int_overrides.items()},
            "start_from": start_from,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False)

        # 進捗ファイルを先に作成（reader が待機できるように）
        Path(progress_path).touch()

        # 子プロセス起動
        self._proc = subprocess.Popen(
            [sys.executable, "-m", WORKER_MODULE, config_path, progress_path, self._stop_path],
            cwd=str(Path(__file__).parent.parent),
        )

        # 進捗読み取りスレッド起動
        t = threading.Thread(
            target=self._progress_reader,
            args=(progress_path, self._proc),
            daemon=True,
        )
        t.start()

    def _progress_reader(self, progress_path, proc):
        """子プロセスの progress.jsonl を tail -f 方式で読み、msg_queue に投入する"""
        try:
            with open(progress_path, "r", encoding="utf-8") as f:
                while True:
                    line = f.readline()
                    if line:
                        line = line.strip()
                        if line:
                            try:
                                msg = json.loads(line)
                                self.msg_queue.put(msg)
                            except json.JSONDecodeError:
                                pass
                    else:
                        # ファイル末尾 — プロセスが終了していたら完了
                        if proc.poll() is not None:
                            # 残りの行を読み切る
                            for remaining in f:
                                remaining = remaining.strip()
                                if remaining:
                                    try:
                                        msg = json.loads(remaining)
                                        self.msg_queue.put(msg)
                                    except json.JSONDecodeError:
                                        pass
                            break
                        time.sleep(0.05)
        except Exception as e:
            self.msg_queue.put({"type": "error", "message": f"進捗読み取りエラー: {e}"})
        finally:
            with self._lock:
                self.running = False
                self._proc = None
            # doneメッセージが無い場合（ワーカー異常終了時）に強制投入
            has_done = any(
                isinstance(m, dict) and m.get("type") == "done"
                for m in list(self.msg_queue.queue)
            )
            if not has_done:
                self.msg_queue.put({"type": "done", "success": False})
            # 一時ファイル削除
            if self._tmpdir:
                for f in ("config.json", "progress.jsonl", "stop"):
                    try:
                        p = os.path.join(self._tmpdir, f)
                        if os.path.exists(p):
                            os.remove(p)
                    except OSError:
                        pass
                self._tmpdir = None
            # 自動化完了をJS側に通知（ブリッジ呼び出しはここだけ、自動化終了後なので安全）
            try:
                if self._window:
                    self._window.evaluate_js('onAutomationDone()')
            except Exception:
                pass

    def start(self, user_mapping=None, overrides=None):
        with self._lock:
            if self.running:
                return {"error": "既に実行中です"}
            if not self.script_lines:
                return {"error": "台本が読み込まれていません"}

            char_mapping = {}
            if self.match_result:
                char_mapping.update(self.match_result.get("auto_mapping", {}))
            if user_mapping:
                char_mapping.update(user_mapping)

            int_overrides = {}
            if overrides:
                for k, v in overrides.items():
                    int_overrides[int(k)] = v

            while not self.msg_queue.empty():
                try:
                    self.msg_queue.get_nowait()
                except queue.Empty:
                    break

            self.running = True

        self._launch_worker(
            [(c, t) for c, t in self.script_lines],
            char_mapping, int_overrides,
        )

        return {"status": "started", "total": len(self.script_lines)}

    def stop(self):
        if not self.running:
            return {"error": "実行中ではありません"}
        # 停止シグナルファイル作成
        if self._stop_path:
            try:
                Path(self._stop_path).touch()
            except OSError:
                pass
        return {"status": "stopping"}

    def get_messages(self):
        messages = []
        while not self.msg_queue.empty():
            try:
                msg = self.msg_queue.get_nowait()
                if msg.get("type") == "done" and "stopped_at" in msg:
                    self.last_stopped_at = msg["stopped_at"]
                elif msg.get("type") == "done" and msg.get("success"):
                    self.last_stopped_at = 0
                messages.append(msg)
            except queue.Empty:
                break
        return messages

    def resume(self, user_mapping=None, overrides=None):
        """中断した行から自動入力を再開する"""
        with self._lock:
            if self.running:
                return {"error": "既に実行中です"}
            if not self.script_lines:
                return {"error": "台本が読み込まれていません"}
            if self.last_stopped_at <= 0:
                return {"error": "再開する位置がありません"}

            char_mapping = {}
            if self.match_result:
                char_mapping.update(self.match_result.get("auto_mapping", {}))
            if user_mapping:
                char_mapping.update(user_mapping)

            int_overrides = {}
            if overrides:
                for k, v in overrides.items():
                    int_overrides[int(k)] = v

            start_from = self.last_stopped_at

            while not self.msg_queue.empty():
                try:
                    self.msg_queue.get_nowait()
                except queue.Empty:
                    break

            self.running = True

        self._launch_worker(
            [(c, t) for c, t in self.script_lines],
            char_mapping, int_overrides, start_from,
        )

        return {"status": "resumed", "start_from": start_from, "total": len(self.script_lines)}


def main():
    import webview

    api_instance = Api()

    html_content = (WEB_DIR / "index.html").read_text(encoding="utf-8")

    window = webview.create_window(
        "A.I.VOICE2 テキスト自動入力",
        html=html_content,
        js_api=api_instance,
        width=900,
        height=820,
        min_size=(700, 600),
    )
    api_instance.set_window(window)

    webview.start()

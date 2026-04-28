"""AIVoice2 自動入力 — 子プロセスワーカー

GUI プロセスとは別プロセスで自動化を実行し、フォアグラウンド競合を回避する。

使い方:
    python -m auto_aivoice2.worker <config.json> <progress.jsonl> <stop_file>
"""
import sys
import json
import threading
import queue
from pathlib import Path


class FileQueueAdapter:
    """queue.Queue 互換インターフェースで JSONL ファイルに書き出すアダプタ"""

    def __init__(self, path):
        self._path = path
        self._f = open(path, "w", encoding="utf-8", buffering=1)  # line-buffered

    def put(self, msg):
        self._f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self._f.flush()

    def close(self):
        self._f.close()


class FileStopEvent:
    """threading.Event 互換インターフェースでファイル存在をチェックする停止シグナル"""

    def __init__(self, path):
        self._path = Path(path)
        self._stopped = False

    def is_set(self):
        if self._stopped:
            return True
        if self._path.exists():
            self._stopped = True
            try:
                self._path.unlink()
            except OSError:
                pass
            return True
        return False

    def set(self):
        self._stopped = True


def main():
    if len(sys.argv) < 4:
        print("Usage: python -m auto_aivoice2.worker <config.json> <progress.jsonl> <stop_file>")
        sys.exit(1)

    config_path = sys.argv[1]
    progress_path = sys.argv[2]
    stop_path = sys.argv[3]

    # 設定読み込み
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    script_lines = [(c, t) for c, t in config["script_lines"]]
    char_mapping = config.get("char_mapping", {})
    overrides = {int(k): v for k, v in config.get("overrides", {}).items()}
    start_from = config.get("start_from", 0)

    # アダプタ作成
    msg_queue = FileQueueAdapter(progress_path)
    stop_event = FileStopEvent(stop_path)

    # ESC キー監視（ワーカープロセス内で動作）
    from auto_aivoice2.automation import _esc_monitor
    esc_thread = threading.Thread(target=_esc_monitor, args=(stop_event,), daemon=True)
    esc_thread.start()

    # 自動化実行
    from auto_aivoice2.automation import run_automation
    try:
        run_automation(script_lines, char_mapping, msg_queue, stop_event,
                       overrides=overrides, start_from=start_from)
    except Exception as e:
        msg_queue.put({"type": "error", "message": f"ワーカーエラー: {e}"})
        msg_queue.put({"type": "done", "success": False})
    finally:
        msg_queue.close()
        pass


if __name__ == "__main__":
    main()

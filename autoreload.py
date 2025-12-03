import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess

SCRIPT = "main.py"  # ganti dengan nama file utama kamu

class RestartOnChange(FileSystemEventHandler):
    def __init__(self):
        self.process = None
        self.start_process()

    def start_process(self):
        print(f"🚀 Menjalankan {SCRIPT} ...")
        self.process = subprocess.Popen(["python", SCRIPT])

    def restart_process(self):
        print("🔄 Deteksi perubahan! Merestart bot...")
        if self.process:
            self.process.terminate()
            self.process.wait()
        self.start_process()

    def on_modified(self, event):
        if event.src_path.endswith(SCRIPT):
            self.restart_process()

if __name__ == "__main__":
    event_handler = RestartOnChange()
    observer = Observer()
    observer.schedule(event_handler, ".", recursive=False)
    observer.start()
    print("👀 Auto-reloader aktif. Perubahan akan otomatis merestart bot.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        if event_handler.process:
            event_handler.process.terminate()
    observer.join()

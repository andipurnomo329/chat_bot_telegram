import os
import subprocess
import sys
import time

BOT_MODULE = ["-m", "bot.report_kcln_job_notif_2"]
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(PROJECT_ROOT, "supervisor.log")


def log_message(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [SUPERVISOR] {msg}\n"
    print(formatted, end="", flush=True)

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted)
    except Exception:
        pass


def run_bot():
    log_message("=== SUPERVISOR STARTED ===")

    while True:
        log_message("Memulai modul Bot ETL KCLN...")

        # Buka file log dan alirkan stdout + stderr bot ke dalamnya
        with open(LOG_FILE, "a", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                [sys.executable, "-u"] + BOT_MODULE,
                cwd=PROJECT_ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,  # Error bot juga masuk ke log
            )
            process.wait()

        log_message(
            f"ALERT: Bot terhenti dengan code {process.returncode}. Restart dalam 5 detik..."
        )
        time.sleep(5)


if __name__ == "__main__":
    run_bot()
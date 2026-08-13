@echo off
cd /d "D:\CCR1\reportpython\chat_bot_telegram"

:: 1. Catat bahwa .bat mulai
echo [%DATE% %TIME%] 1. .bat mulai dieksekusi. >> scheduler_execution.log

:: 2. Cek apakah file supervisor.py ada di folder ini
if not exist "run_kcln_jobntf_supervisor.py" (
    echo [%DATE% %TIME%] ERROR: File supervisor.py tidak ditemukan di folder ini! >> scheduler_execution.log
    goto END
)

:: 3. Langsung jalankan supervisor tanpa jeda tasklist yang sering error di background
echo [%DATE% %TIME%] 2. Mencoba mengeksekusi pythonw supervisor.py... >> scheduler_execution.log
start "" pythonw.exe run_kcln_jobntf_supervisor.py

if errorlevel 1 (
    echo [%DATE% %TIME%] 3. ERROR: Gagal memanggil pythonw.exe! >> scheduler_execution.log
) else (
    echo [%DATE% %TIME%] 3. SUCCESS: Perintah pythonw berhasil dipicu. >> scheduler_execution.log
)

:END
echo [%DATE% %TIME%] 4. .bat selesai berjalan. >> scheduler_execution.log
echo ------------------------------------------------------- >> scheduler_execution.log

:: Monitoring real-time di layar jika dibuka manual
powershell -Command "Get-Content -Path 'supervisor.log' -Wait -Tail 20"
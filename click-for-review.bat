@echo off
title Storyboard review - click for review
cd /d "%~dp0"
set PORT=8765
rem 1) stop an older review server (python only) so the port is free
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if ($p -and $p.ProcessName -like 'python*') { Stop-Process -Id $p.Id -Force } }"
rem 2) start the server in its own minimized window (it closes itself about 90 seconds after the browser page is closed)
start "Storyboard review server" /min python tools\serve.py
rem 3) open the page in the default browser
ping -n 3 127.0.0.1 >nul
start "" http://127.0.0.1:%PORT%/review.html

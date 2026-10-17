@echo off
chcp 65001 >nul
title MusicVideoStudio — Web Server (http://127.0.0.1:8765)
cd /d "%~dp0"
start "" "http://127.0.0.1:8765"
python web_app.py
pause

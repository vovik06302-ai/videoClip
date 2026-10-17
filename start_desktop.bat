@echo off
chcp 65001 >nul
title MusicVideoStudio — Desktop GUI
cd /d "%~dp0"
python app.py
pause

@echo off
chcp 65001 >nul
title 赛博女友 - AI伴侣
echo ========================================
echo    赛博女友 - AI伴侣
echo ========================================
echo.
echo 正在检查依赖...
pip install -r requirements.txt --quiet 2>nul
echo.
echo 正在启动服务器...
echo 访问地址: http://localhost:5000
echo.
echo 请确保 Ollama 已启动:
echo   ollama serve
echo.
python app.py
pause

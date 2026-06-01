@echo off
chcp 65001 >nul
title 赛博女友 - AI伴侣
echo ========================================
echo    赛博女友 - AI伴侣
echo ========================================
echo.

:: ============================================================
:: 语音模型路径配置
:: ============================================================
:: SenseVoiceSmall 语音识别模型 (ModelScope 缓存路径)
set SENSEVOICE_MODEL_PATH=C:\Users\15123\.cache\modelscope\hub\models\iic\SenseVoiceSmall

:: VoxCPM2 文本转语音模型 (HuggingFace 缓存路径)
set VOXCPM2_MODEL_PATH=C:\Users\15123\.cache\huggingface\hub\models--openbmb--VoxCPM2

:: 可选：VoxCPM2 参考音频（用于音色克隆）
:: set VOXCPM2_REF_AUDIO=C:\path\to\voice_ref.wav
:: set VOXCPM2_REF_TEXT=参考音频对应文本内容

echo 正在检查依赖...
pip install -r requirements.txt --quiet 2>nul
echo.
echo 正在启动服务器...
echo 访问地址: http://localhost:5000
echo.
echo 请确保 Ollama 已启动:
echo   ollama serve
echo.
echo 语音模型路径:
echo   ASR: %SENSEVOICE_MODEL_PATH%
echo   TTS: %VOXCPM2_MODEL_PATH%
echo.
python app.py
pause

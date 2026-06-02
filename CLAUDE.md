# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

**痞老板的凯伦** — 基于 Ollama 本地大模型的 AI 伴侣聊天应用。前端是纯聊天窗口 + 右侧滑入设置面板，后端是 Flask API + WebSocket 实时语音，支持通过截图/文本学习说话风格。

> 制作目标：质疑痞老板，理解痞老板，成为痞老板

## 技术栈

- **后端:** Python Flask + flask-cors + flask-sock (WebSocket)
- **LLM:** Ollama (`qwen2.5:7b-instruct`)，默认连接 `http://localhost:11434/api`
- **ASR:** SenseVoiceSmall (FunASR)，语音识别转文字
- **TTS:** 双模式 —
  - 云端：阿里云 CosyVoice v3-flash (dashscope SDK)，默认音色 `longxing_v3` (龙星御姐音)
  - 本地：VoxCPM2，自动 fallback
- **OCR:** EasyOCR（中英文混合识别）
- **图片处理:** Pillow（头像缩略图）
- **前端:** 纯 HTML/CSS/JS，无框架。SSE 流式 + WebSocket 实时语音
- **存储:** 本地 JSON (`data/profiles.json`, `data/settings.json`, `data/chat_history.json`)

## 常用命令

```bash
# 启动（Windows）
start.bat

# 或手动启动
python app.py
# 访问 http://localhost:5000
# WebSocket: ws://localhost:5000/ws/voice

# 安装依赖
pip install -r requirements.txt

# 确保 Ollama 运行并已拉取模型
ollama serve
ollama pull qwen2.5:7b-instruct

# JS 语法检查
node -c static/js/main.js

# 测试 CosyVoice TTS（独立运行，不依赖 Flask）
python test.py

# 环境变量（可选）
set DASHSCOPE_API_KEY=sk-xxx          # 启用 CosyVoice 云端 TTS
set COSYVOICE_VOICE=longxing_v3       # CosyVoice 音色（龙星御姐音）
set COSYVOICE_MODEL=cosyvoice-v3-flash
set COSYVOICE_FORMAT=mp3               # 输出格式：mp3 或 wav
set COSYVOICE_VOLUME=50                # 音量 0-100
set COSYVOICE_SPEECH_RATE=1.0          # 语速 0.5-2.0
set COSYVOICE_PITCH_RATE=1.0           # 音调 0.5-2.0
set VOXCPM2_REF_AUDIO=C:\path\to\voice_ref.wav   # VoxCPM2 音色克隆参考音频
set VOXCPM2_REF_TEXT=参考音频对应的文本            # 参考音频的文字内容
set FORCE_CPU=1                       # 强制 CPU 模式（调试用）
```

## 核心架构

### 前端布局

```
┌──────────────────────────────────────────┐
│  Chat Header  [📞 语音] [⚙️ 设置]        │
├──────────────────────────────────────────┤
│                                          │
│  聊天消息区域（纯聊天窗口）               │
│                                          │
├──────────────────────────────────────────┤
│  [语音状态栏]                             │
│  [输入框........................][发送]   │
└──────────────────────────────────────────┘

点击 ⚙️ → 右侧滑入设置面板（4个标签页）：
  👤 头像 | 🧠 风格学习 | 🎭 人物风格 | 🔧 模型配置
```

### 文本对话流程

```
浏览器 ──SSE stream──> /api/chat/stream ──POST──> Ollama /api/chat
```

### 语音通话流程 (WebSocket 实时流式)

```
浏览器 ──getUserMedia──> 录音 (WebM, echoCancellation+noiseSuppression)
   │
   ├── VAD 静音检测 (AnalyserNode, 2s 阈值)
   │     │
   │     └── onstop: WebM → WAV (16kHz)
   │           │
   │           └── WebSocket ws://localhost:5000/ws/voice
   │                  │
   │                  ├── {type: "audio", data: base64}
   │                  │     │
   │                  │     ├── SenseVoiceSmall ASR (<100ms)
   │                  │     ├── Ollama 流式 LLM
   │                  │     │     └── 逐句切割（。！？\n）
   │                  │     ├── CosyVoice/VoxCPM2 流式 TTS
   │                  │     └── 逐句回传 {type: "tts_audio", data: base64}
   │                  │
   │                  ├── 前端音频队列顺序播放
   │                  │     ├── AI 说话时显示 [打断] 按钮
   │                  │     └── 用户说话 → {type: "interrupt"} → 停止生成
   │                  │
   │                  └── {type: "done"} → 恢复监听
   │
   └── 挂断 → 关闭 WebSocket + 音频流
```

**支持随时打断（barge-in）：** AI 正在说话时用户开口 → 浏览器 VAD 检测到声音 → 发送打断信号 → 停止 TTS 播放 + LLM 生成 → 立即开始新录音。

**TTS 调度策略：** `tts_synthesize()` 统一入口，优先使用 CosyVoice 云端，失败自动 fallback 到 VoxCPM2 本地。

### 风格学习流程

1. 用户上传截图 (EasyOCR) 或粘贴文本
2. `_parse_chat_lines()` 解析 `昵称: 消息` 格式
3. `analyze_speaking_style()` 调用 LLM 分析风格
4. 结果保存到 `profiles.json` → 注入 system prompt

### 关键设计决策

- **WebSocket 优先，HTTP 降级：** 语音默认走 WebSocket，连接失败自动降级到 HTTP SSE
- **设置持久化：** 模型配置单独存 `data/settings.json`，运行时可通过 `/api/settings` 读写
- **use_reloader=False：** 防止 Flask 双进程导致 CUDA 上下文冲突
- **聊天历史限制：** 每次请求只发送最近 20 条对话
- **学习文本上限：** 最多保留 10 次学习记录
- **设置 5 秒缓存：** `get_settings()` 有 5 秒内存缓存（`_settings_cache`），`save_settings()` 默认会清除。但 `set_cosyvoice_config()` 直接修改模块级全局变量，不走缓存——运行时切换 TTS 配置及时生效。
- **TTS 调度：** `tts_synthesize()` 统一入口 → CosyVoice 云端优先 → 失败自动 fallback VoxCPM2 本地

### VoxCPM2 模型加载策略

`voice.py` 的 `_init_tts()` 按优先级尝试 4 种加载方式：

1. `voxcpm.VoxCPM(voxcpm_model_path=...)` — 专用包直接加载（推荐，GPU 优化）
2. `VoxCPM.from_pretrained(hf_model_id="openbmb/VoxCPM2", local_files_only=True)` — 从 HF 缓存加载
3. `CosyVoice2(model_path, ...)` — CosyVoice 兼容加载
4. `CosyVoice(model_path)` — 旧版 CosyVoice 兼容

任一成功即停止。全部失败则 TTS 不可用，但文字聊天仍正常。

### 文件存储结构

```
data/
  profiles.json       # {name, style_analysis, avatar_ai, avatar_user, learned_texts[], ...}
  settings.json       # {ollama_url, model_name, tts_provider, cosyvoice_api_key, ...}
  chat_history.json   # [{user, ai, timestamp}, ...]

static/uploads/
  avatars/            # default_ai.png, default_user.png, avatar_ai.png, avatar_user.png
  screenshot_*.png    # 用户上传的聊天截图
```

### API 路由总览

| 路径 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 主页面 |
| `/api/chat` | POST | 同步聊天 |
| `/api/chat/stream` | POST | SSE 流式聊天 |
| `/ws/voice` | WS | WebSocket 实时语音 |
| `/api/voice/asr` | POST | 语音识别 |
| `/api/voice/tts` | POST | 语音合成 |
| `/api/voice/tts-stream` | POST | 流式 TTS (SSE) |
| `/api/voice/chat` | POST | 语音对话 HTTP 版（全量返回文字+音频） |
| `/api/voice/chat-stream` | POST | 语音对话 HTTP 流式版（SSE 逐句推送文字+音频） |
| `/api/voice/status` | GET | 语音模块状态 |
| `/api/settings` | GET/POST | 设置读写 |
| `/api/profile` | GET/POST | 个人资料 |
| `/api/upload-screenshot` | POST | 上传截图学习 |
| `/api/upload-raw-text` | POST | 粘贴文本学习 |
| `/api/upload-avatar` | POST | 上传头像 |
| `/api/remove-avatar` | POST | 移除头像 |
| `/api/reset` | POST | 重置全部数据 |
| `/api/chat-history` | GET/DELETE | 聊天历史 |

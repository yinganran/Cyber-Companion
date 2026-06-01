# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

赛博女友 (Cyber GF) — 基于 Ollama 本地大模型的 AI 伴侣聊天应用。前端是赛博朋克风格的 SPA，后端是 Flask API，支持通过截图/文本学习目标人物的说话风格来定制 AI 性格。

## 技术栈

- **后端:** Python Flask + flask-cors
- **LLM:** Ollama (`qwen2.5:7b-instruct`)，默认连接 `http://localhost:11434/api`
- **ASR:** SenseVoiceSmall (FunASR)，语音识别转文字
- **TTS:** VoxCPM2 (CosyVoice/ModelScope)，文字转语音
- **OCR:** EasyOCR（中英文混合识别，用于从聊天截图中提取文本）
- **图片处理:** Pillow（头像缩略图）
- **前端:** 纯 HTML/CSS/JS，无框架。SSE 流式响应。Web Audio API 录音
- **存储:** 本地 JSON 文件 (`data/profiles.json`, `data/chat_history.json`)

## 常用命令

```bash
# 启动（Windows）
start.bat

# 或手动启动
python app.py
# 访问 http://localhost:5000

# 安装依赖
pip install -r requirements.txt

# 确保 Ollama 运行并已拉取模型
ollama serve
ollama pull qwen2.5:7b-instruct

# JavaScript 语法检查（修改 main.js 后必须做）
node -e "$(cat static/js/main.js)"   # 只关注 SyntaxError，ReferenceError (document) 可忽略
```

## 核心架构

### 数据流

```
浏览器 ──SSE stream──> /api/chat/stream ──POST──> Ollama /api/chat
   │                        │
   │                        ├── _build_chat_context():
   │                        │     读取 profiles.json (风格分析 + AI名字)
   │                        │     读取 chat_history.json (最近20条对话)
   │                        │     构建 system prompt + messages
   │                        │
   │                        └── 响应后保存到 chat_history.json
   │
   ├── 上传截图 ──> /api/upload-screenshot
   │                 EasyOCR 识别 → 解析聊天格式 → LLM分析风格 → 保存到 profiles.json
   │
   └── 头像管理 ──> /api/upload-avatar, /api/remove-avatar
                     Pillow 缩略图 256x256 → static/uploads/avatars/
```

### 风格学习流程

1. 用户上传聊天截图或粘贴文本
2. `_parse_chat_lines()` 用正则 `^(.+?)[:：]\s*(.+)` 解析 `昵称: 消息` 格式
3. `analyze_speaking_style()` 调用 Ollama 分析说话风格（语气、口头禅、表情习惯等）
4. `build_system_prompt()` 将风格分析注入 system prompt，之后的每次对话都携带此 prompt
5. 学习结果保存在 `profiles.json` 的 `style_analysis` 字段

### 语音通话流程

```
浏览器 ──点击电话按钮──> getUserMedia 获取麦克风
   │
   ├── MediaRecorder 录音 (WebM)
   │      │
   │      ├── 静音检测：AnalyserNode 监测音量
   │      │    持续2秒低于阈值 → 自动停止录音
   │      │
   │      └── onstop: 转换 WebM → WAV (16kHz 单声道 PCM)
   │             │
   │             └── POST /api/voice/chat-stream (FormData + WAV Blob)
   │                    │
   │                    ├── voice.transcribe_audio() → SenseVoiceSmall ASR (<100ms)
   │                    ├── call_ollama(stream=True) → LLM 流式输出
   │                    │     └── 逐句切割（。！？\n）→ 每句立即 TTS
   │                    ├── voice.synthesize_speech(sentence, timesteps=3, max_len=512)
   │                    │     └── 优化参数：扩散步数 3，最大长度 512（单句 ~1.5s）
   │                    └── SSE 逐句推送 {type:"sentence", text, audio(base64)}
   │                           │
   │                           ├── 前端逐句接收 → 文本更新气泡
   │                           ├── 音频入队 → 顺序播放（首句延迟 ~2s）
   │                           └── done 事件 → 异步保存历史 → 恢复监听
   │
   └── 点击挂断 → 停止录音 + 关闭音频流
```

**旧接口 `/api/voice/chat`（全量返回）** 保留兼容，但语音通话默认使用新流式接口。

**延迟对比：**
- 旧流程：全链路串行等待，TTS 全文合成 ~5.5s + LLM ~3s = 总延迟 8s+
- 新流程：ASR <100ms + 首句 LLM ~500ms + 首句 TTS ~1.5s = 首句延迟 ~2s

### 前端状态管理

`main.js` 中 `state` 对象管理全局状态：`aiName`, `aiAvatar`, `userAvatar`, `isStreaming`, `sidebarOpen`。所有 DOM 元素引用集中在 `dom` 对象。`loadProfile()` 在页面初始化时从 `/api/profile` 加载配置覆盖默认值。

### 关键设计决策

- **SSE 流式响应：** `/api/chat/stream` 使用 Server-Sent Events，前端用 `ReadableStream` 逐块读取。注意：**修改 JS 字符串中的 `'\n'` 时要确保转义正确，文字换行会导致语法错误**。
- **Ollama 懒加载：** EasyOCR Reader 是模块级单例，首次使用时加载模型到内存。
- **头像默认值：** 默认头像放在 `static/uploads/avatars/default_ai.png` 和 `default_user.png`，重置和移除操作回退到默认头像而非空值。
- **聊天历史限制：** 每次请求只发送最近 20 条对话给 LLM（控制 token 消耗）。
- **学习文本上限：** 最多保留 10 次学习记录（`learned_texts[-10:]`）。

### 文件存储结构

```
data/
  profiles.json      # {name, style_analysis, avatar_ai, avatar_user, learned_texts[], ...}
  chat_history.json  # [{user, ai, timestamp}, ...]

static/uploads/
  avatars/           # default_ai.png, default_user.png, avatar_ai.png, avatar_user.png
  screenshot_*.png   # 用户上传的聊天截图
```

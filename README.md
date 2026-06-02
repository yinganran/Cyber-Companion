# 🤖 痞老板的凯伦

> 质疑痞老板，理解痞老板，成为痞老板

基于 Ollama 本地大模型的 AI 伴侣聊天应用，支持语音通话、风格学习、角色定制。

## ✨ 功能

- 💬 **流式对话** — 基于 Ollama + Qwen2.5，SSE 逐字流式输出
- 🎙️ **实时语音通话** — WebSocket 实时语音对话，支持随时打断（barge-in）
- 🗣️ **双 TTS 引擎** — 阿里云 CosyVoice v3-flash 云端（龙星御姐音）+ VoxCPM2 本地，自动 fallback
- 🎤 **语音识别** — SenseVoiceSmall 端到端 ASR，GPU 加速 <100ms
- 🧠 **风格学习** — 上传微信/QQ 聊天截图或粘贴文本，AI 自动分析并模仿说话风格
- 🎨 **赛博朋克 UI** — 霓虹渐变色、暗黑主题、响应式布局
- ⚙️ **设置面板** — 右侧滑入 4 标签页（头像 / 风格学习 / 人物风格 / 模型配置）
- 👤 **自定义头像** — 上传你和 AI 的头像，自动缩略图处理

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动 Ollama

```bash
ollama serve
ollama pull qwen2.5:7b-instruct
```

### 3. 启动应用

```bash
python app.py
# 或双击 start.bat (Windows)
```

浏览器打开 `http://localhost:5000`，WebSocket 地址 `ws://localhost:5000/ws/voice`

## 🛠 技术栈

- **后端:** Python Flask + flask-cors + flask-sock (WebSocket)
- **LLM:** Ollama (`qwen2.5:7b-instruct`)，默认连接 `http://localhost:11434/api`
- **ASR:** SenseVoiceSmall (FunASR)，VAD 语音活动检测
- **TTS:** 双模式 —
  - 云端：阿里云 CosyVoice v3-flash (dashscope SDK)，默认音色 `longxing_v3`（龙星御姐音）
  - 本地：VoxCPM2，自动 fallback
- **OCR:** EasyOCR（中英文混合识别）
- **图片处理:** Pillow（头像缩略图）
- **前端:** 纯 HTML/CSS/JS，SSE 流式 + WebSocket 实时语音
- **存储:** 本地 JSON (`data/profiles.json`, `data/settings.json`, `data/chat_history.json`)

## 🎙️ 语音配置

### 环境变量

```bash
# Windows (start.bat 中已预配置)
set SENSEVOICE_MODEL_PATH=C:\Users\###\.cache\modelscope\hub\models\iic\SenseVoiceSmall
set VOXCPM2_MODEL_PATH=C:\Users\###\.cache\huggingface\hub\models--openbmb--VoxCPM2

# CosyVoice 云端 TTS（可选，不设置则使用本地 VoxCPM2）
set DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx
set COSYVOICE_VOICE=longxing_v3          # 音色选择
set COSYVOICE_MODEL=cosyvoice-v3-flash
set COSYVOICE_FORMAT=mp3                 # 输出格式：mp3 或 wav
set COSYVOICE_VOLUME=50                  # 音量 0-100
set COSYVOICE_SPEECH_RATE=1.0            # 语速 0.5-2.0
set COSYVOICE_PITCH_RATE=1.0             # 音调 0.5-2.0

# 可选：VoxCPM2 音色克隆参考音频
set VOXCPM2_REF_AUDIO=D:\models\voice_ref.wav
set VOXCPM2_REF_TEXT=参考音频对应的文本
```

启动时会自动预加载所有语音模型，加载完成后即可直接使用语音通话功能。点击聊天界面右上角 📞 电话按钮开始语音通话。

### 语音通话流程

```
浏览器录音 (WebM, 降噪+回声消除)
  → VAD 静音检测 (AnalyserNode)
  → WebSocket → SenseVoiceSmall ASR → Ollama 流式 LLM
  → 逐句切割 → CosyVoice/VoxCPM2 流式 TTS
  → 逐句回传前端音频队列顺序播放
  → 支持随时打断 (用户开口即中断 AI)
```

## 📁 项目结构

```
├── app.py                  # Flask 后端主程序（17 个 API 路由）
├── voice.py                # 语音模块（ASR + VoxCPM2 TTS + CosyVoice 云端 TTS）
├── test.py                 # CosyVoice TTS 独立测试脚本
├── requirements.txt        # Python 依赖
├── start.bat               # Windows 启动脚本（含环境变量预配置）
├── templates/
│   └── index.html          # 前端页面
├── static/
│   ├── css/style.css       # 赛博朋克风格样式
│   ├── js/main.js          # 前端逻辑（SSE + WebSocket）
│   └── uploads/            # 上传文件目录
│       └── avatars/        # 头像文件（自动生成）
└── data/                   # 本地数据存储（自动生成）
    ├── profiles.json       # 人设、风格分析、学习文本
    ├── settings.json       # 模型配置、TTS 参数
    └── chat_history.json   # 对话历史
```

## 🔌 API 路由

| 路径 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 主页面 |
| `/api/chat` | POST | 同步聊天 |
| `/api/chat/stream` | POST | SSE 流式聊天 |
| `/ws/voice` | WS | WebSocket 实时语音通话 |
| `/api/voice/asr` | POST | 语音识别 |
| `/api/voice/tts` | POST | 语音合成 |
| `/api/voice/tts-stream` | POST | 流式 TTS (SSE) |
| `/api/voice/tts/test` | POST | TTS 音色试听 |
| `/api/voice/chat` | POST | 语音对话 HTTP 版 |
| `/api/voice/chat-stream` | POST | 语音对话流式版 (SSE) |
| `/api/voice/status` | GET | 语音模块状态 |
| `/api/settings` | GET/POST | 设置读写 |
| `/api/profile` | GET/POST | 个人资料 |
| `/api/upload-screenshot` | POST | 上传截图学习风格 |
| `/api/upload-raw-text` | POST | 粘贴文本学习风格 |
| `/api/upload-avatar` | POST | 上传头像 |
| `/api/remove-avatar` | POST | 移除头像 |
| `/api/reset` | POST | 重置全部数据 |
| `/api/chat-history` | GET/DELETE | 聊天历史 |

## 📝 使用说明

1. **文字聊天** — 底部输入框打字，Enter 发送，AI 流式逐字回复
2. **语音通话** — 点击右上角 📞 按钮开始语音对话，AI 说话时可随时打断
3. **风格学习** — 点击 ⚙️ 打开设置面板 → 🧠 风格学习标签 → 上传截图或粘贴文本
4. **角色定制** — 🎭 人物风格标签 → 修改 AI 名字和性格描述
5. **模型配置** — 🔧 模型配置标签 → 切换 Ollama 地址/模型/TTS 提供商
6. **头像管理** — 👤 头像标签 → 上传你和 AI 的自定义头像

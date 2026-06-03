# 🤖 痞老板的凯伦

> 质疑痞老板，理解痞老板，成为痞老板

基于 Ollama 本地大模型的 AI 伴侣聊天应用，支持实时语音通话、文字+语音混合回复、风格学习、角色定制。手机端可访问。

## ✨ 功能

### 文字对话
- 💬 **流式对话** — 基于 Ollama + Qwen2.5，SSE 逐字流式输出
- 🔊 **语音回复模式** — 文字输入，AI 以语音气泡回复，右键可转文字
- 🧠 **风格学习** — 上传微信/QQ 聊天截图或粘贴文本，AI 自动分析并模仿说话风格

### 语音通话
- 🎙️ **WebSocket 实时通话** — 全屏通话界面，低延迟流式对话
- 🛑 **随时打断** — AI 说话时开口即可中断（barge-in）
- 🫁 **头像呼吸动画** — 4 态联动（正在说 / 正在听 / 你说 / 思考中）
- 🤫 **VAD 静音检测** — 自动检测用户说完，无需手动结束

### 语音引擎
- 🗣️ **双 TTS 引擎** — CosyVoice v3-flash 云端（6 种音色）+ VoxCPM2 本地
- 🎤 **ASR 语音识别** — SenseVoiceSmall，GPU 加速 <100ms

### 界面
- 🎨 **赛博朋克 UI** — 霓虹渐变色、暗黑主题
- 📱 **手机端适配** — 响应式布局，iPhone 安全区，防缩放
- ⚙️ **设置面板** — 4 标签页（头像 / 风格学习 / 人物风格 / 模型配置）
- 📋 **app.log 日志** — 全流程记录（LLM/TTS/ASR 耗时、前端操作），5MB 自动轮转

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

### 3. 配置在线 TTS（推荐）

在 `data/settings.json` 中配置（启动即生效，无需每次前端填写）：

```json
{
  "tts_provider": "cosyvoice",
  "cosyvoice_api_key": "sk-xxxxxxxxxxxxxxxx",
  "cosyvoice_api_url": "https://dashscope.aliyuncs.com/api/v1",
  "cosyvoice_model": "cosyvoice-v3-flash",
  "cosyvoice_voice": "longxing_v3"
}
```

可用音色：`longxing_v3`(御姐) `longxiaochun_v3`(活泼) `longxiaoxia_v3`(温柔) `longyue_v3`(甜美) `longmiao_v3`(软萌)

### 4. 启动应用

```bash
python app.py
```

浏览器打开 `http://localhost:5000`，或手机端同一 WiFi 下访问 `http://局域网IP:5000`。

> ⚠️ 手机端语音通话需 HTTPS（`getUserMedia` 限制），本地局域网可正常文字聊天 + TTS 语音回复。

## 🛠 技术栈

| 层 | 技术 |
|---|---|
| **后端** | Python Flask + flask-cors + flask-sock (WebSocket) |
| **LLM** | Ollama (`qwen2.5:7b-instruct`) |
| **ASR** | SenseVoiceSmall (FunASR) + VAD |
| **TTS** | CosyVoice v3-flash (阿里云云端) / VoxCPM2 (本地) |
| **OCR** | EasyOCR（中英文混合） |
| **前端** | 原生 HTML/CSS/JS，SSE 流式 + WebSocket 实时语音 |
| **日志** | Python logging → `app.log`，RotatingFileHandler 5MB 轮转 |
| **存储** | 本地 JSON（profiles / settings / chat_history） |

## 📁 项目结构

```
├── app.py                  # Flask 后端主程序（路由、WebSocket、日志系统）
├── voice.py                # 语音模块（ASR + TTS + CosyVoice 云端）
├── requirements.txt        # Python 依赖
├── app.log                 # 运行日志（5MB 轮转，自动生成）
├── templates/
│   └── index.html          # 前端页面
├── static/
│   ├── css/style.css       # 赛博朋克风格 + 手机适配
│   ├── js/main.js          # 前端逻辑（SSE 流式 + WebSocket + 语音回复 + VAD）
│   └── uploads/
│       └── avatars/        # 头像文件
└── data/
    ├── profiles.json       # 人设 / 风格分析 / 学习文本
    ├── settings.json       # 模型 & TTS 配置（重启自动加载）
    └── chat_history.json   # 对话历史
```

## 🔌 API 路由

| 路径 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 主页面 |
| `/api/chat` | POST | 同步聊天 |
| `/api/chat/stream` | POST | SSE 流式聊天 |
| `/api/log` | POST | 前端日志收集 |
| `/ws/voice` | WS | WebSocket 实时语音通话 |
| `/api/voice/asr` | POST | 语音识别 |
| `/api/voice/tts` | POST | 语音合成（文字→WAV） |
| `/api/voice/tts/test` | POST | TTS 音色试听 |
| `/api/voice/chat` | POST | 语音对话 HTTP 版（ASR→LLM→TTS 全流程） |
| `/api/voice/chat-stream` | POST | 语音对话流式版（SSE） |
| `/api/voice/status` | GET | 语音模块加载状态 |
| `/api/settings` | GET/POST | 设置读写 |
| `/api/profile` | GET/POST | 个人资料 |
| `/api/upload-screenshot` | POST | 上传聊天截图学习风格 |
| `/api/upload-raw-text` | POST | 粘贴文本学习风格 |
| `/api/upload-avatar` | POST | 上传头像 |
| `/api/remove-avatar` | POST | 移除头像 |
| `/api/reset` | POST | 重置全部数据 |
| `/api/chat-history` | GET/DELETE | 聊天历史管理 |

## 📝 使用说明

### 基础操作
1. **文字聊天** — 输入框打字，Enter 发送，AI 流式逐字回复
2. **🔊 语音回复** — 点击头部 🔈 按钮开启，依然打字输入，AI 用语音气泡回复，右键气泡 → 转文字
3. **📞 语音通话** — 点击头部 📞 进入全屏通话，开口即聊，说完自动识别
4. **🧠 风格学习** — ⚙️ → 风格学习 → 上传聊天截图或粘贴文本
5. **⚙️ 模型配置** — 切换 Ollama 地址 / 模型 / TTS 引擎 / 音色

### 通话状态说明
| 显示 | 光环 | 含义 |
|---|---|---|
| 正在听... | 青色缓慢呼吸 | 等待你说话 |
| 你说... | 暖红中速呼吸 | 检测到你在说话 |
| 识别中... | 灰色静止 | 语音识别中 |
| 思考中... | 灰色静止 | LLM 生成回复中 |
| 正在说... | 粉色快速跳动 | AI 正在说话 |

### 日志调试
遇到问题时查看 `app.log`，记录完整流程：
```
[WS] 🎤 第1轮 收到音频 | size=94780 chars
[WS] 第1轮 ASR 完成 | 耗时=0.23s | text=「你好」
[LLM] 调用 Ollama | model=qwen2.5:7b-instruct | user=「你好」
[WS] 第1轮 第1句 TTS完成 | 耗时=1.5s | text=「你好啊...」
[WS] 第1轮 完成 | 总耗时=3.2s | 总句数=3
```

# 🤖 赛博伴侣 (Cyber GF)

基于本地大模型的 AI 伴侣聊天应用，支持通过聊天截图学习说话风格。

## ✨ 功能

- 💬 **流式对话** — 基于 Ollama + Qwen2.5，秒回消息
- 🧠 **风格学习** — 上传微信/QQ 聊天截图，AI 自动分析并模仿说话风格
- 🎨 **赛博朋克 UI** — 霓虹渐变色、暗黑主题、响应式布局
- 👤 **自定义头像** — 上传你和 AI 的头像
- 📝 **文本学习** — 直接粘贴聊天记录学习风格

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

浏览器打开 `http://localhost:5000`

## 🛠 技术栈

- **后端:** Python Flask
- **LLM:** Ollama + Qwen2.5 7B
- **OCR:** EasyOCR（中英文）
- **前端:** 原生 HTML/CSS/JS + SSE 流式传输
- **存储:** 本地 JSON 文件

## 📁 项目结构

```
├── app.py              # Flask 后端主程序
├── requirements.txt    # Python 依赖
├── start.bat           # Windows 启动脚本
├── templates/
│   └── index.html      # 前端页面
├── static/
│   ├── css/style.css   # 赛博朋克风格样式
│   ├── js/main.js      # 前端逻辑
│   └── uploads/        # 上传文件目录
└── data/               # 本地数据存储（自动生成）
```

## 📝 使用说明

1. **聊天** — 在底部输入框打字，按 Enter 发送
2. **学习风格** — 点击左侧"上传聊天截图"，选择微信聊天截图，AI 自动识别并学习
3. **粘贴文本** — 点击"粘贴聊天文本"，按 `昵称: 消息` 格式粘贴
4. **自定义** — 修改 AI 名字和头像

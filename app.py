import os, json, re, uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, send_file
from flask_cors import CORS
from PIL import Image
import requests
import voice as voice_module

# Config
OLLAMA_API = "http://localhost:11434/api"
MODEL_NAME = "qwen2.5:7b-instruct"
DEFAULT_STYLE = "温柔体贴，善解人意，喜欢用简短自然的句子聊天。"
RELATIONSHIP_CONTEXT = "你正在和男朋友聊天，你们是亲密的恋爱关系。"

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
AVATAR_DIR = UPLOAD_DIR / "avatars"
DATA_DIR = BASE_DIR / "data"
PROFILES_FILE = DATA_DIR / "profiles.json"
CHAT_HISTORY_FILE = DATA_DIR / "chat_history.json"

for d in [UPLOAD_DIR, AVATAR_DIR, DATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ai-ban-secret-key-2024")
CORS(app)

# JSON helpers
def load_json(path, default=None):
    if default is None:
        default = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_profile():
    return load_json(PROFILES_FILE, {})

def save_profile(profile_data):
    profiles = load_json(PROFILES_FILE, {})
    profiles.update(profile_data)
    save_json(PROFILES_FILE, profiles)

def get_chat_history():
    return load_json(CHAT_HISTORY_FILE, [])

def save_chat_history(history):
    save_json(CHAT_HISTORY_FILE, history)

# ---------------------------------------------------------------------------
# Ollama API
# ---------------------------------------------------------------------------
def _ollama_post(payload, stream=False):
    """Single HTTP call to Ollama — avoids duplicating the URL and error handling."""
    try:
        return requests.post(
            f"{OLLAMA_API}/chat", json=payload,
            stream=stream, timeout=120
        )
    except requests.exceptions.ConnectionError:
        raise Exception("无法连接到 Ollama，请确保 Ollama 正在运行。")
    except Exception as e:
        raise Exception(f"Ollama 错误：{str(e)}")


def call_ollama(messages, stream=False, system_prompt=None):
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    payload = {
        "model": MODEL_NAME,
        "messages": full_messages,
        "stream": stream,
        "options": {"temperature": 0.8, "top_p": 0.9, "top_k": 40}
    }

    if stream:
        return _ollama_post(payload, stream=True)
    else:
        resp = _ollama_post(payload, stream=False)
        return resp.json().get("message", {}).get("content", "")


# ---------------------------------------------------------------------------
# EasyOCR — lazy singleton (model loaded once, not per-request)
# ---------------------------------------------------------------------------
_ocr_reader = None

def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
        except ImportError:
            raise Exception("请安装 EasyOCR：pip install easyocr")
        _ocr_reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
    return _ocr_reader


def ocr_image(image_path):
    reader = _get_ocr_reader()
    result = reader.readtext(str(image_path), detail=1)
    result.sort(key=lambda x: (x[0][0][1], x[0][0][0]))

    texts = []
    for (bbox, text, confidence) in result:
        if confidence > 0.3:
            texts.append({
                "text": text,
                "confidence": float(confidence),
                "position": {"top": int(bbox[0][1]), "left": int(bbox[0][0])}
            })
    return texts


# ---------------------------------------------------------------------------
# Chat parsing — pure function, reusable from OCR or raw-text paths
# ---------------------------------------------------------------------------
PARSE_LINE_RE = re.compile(r"^(.+?)[:：]\s*(.+)")


def _parse_chat_lines(lines):
    """Parse a list of text lines into [{speaker, content}] messages."""
    messages = []
    current_speaker = "unknown"
    current_text = []

    for raw in lines:
        text = raw.strip()
        if not text:
            continue
        match = PARSE_LINE_RE.match(text)
        if match:
            if current_text and current_speaker != "unknown":
                messages.append({
                    "speaker": current_speaker,
                    "content": " ".join(current_text)
                })
            current_speaker = match.group(1).strip()
            current_text = [match.group(2).strip()]
        else:
            current_text.append(text)

    if current_text:
        messages.append({
            "speaker": current_speaker,
            "content": " ".join(current_text)
        })
    return messages


def parse_chat_from_ocr(ocr_results):
    """Convenience: extract text strings from OCR dicts, then delegate to _parse_chat_lines."""
    lines = [item["text"] for item in ocr_results]
    return _parse_chat_lines(lines)

def analyze_speaking_style(chat_messages):
    if not chat_messages:
        return DEFAULT_STYLE

    chat_text = "\n".join([
        f"{msg['speaker']}: {msg['content']}"
        for msg in chat_messages
    ])

    analysis_prompt = (
        "请分析以下聊天记录，总结说话者的语言风格、习惯和性格特点。\n\n"
        f"聊天记录：\n{chat_text}\n\n"
        "请从以下方面进行分析（用中文回答，简洁扼要，300字以内）：\n"
        "1. 说话语气（如：温柔、活泼、高冷、傲娇等）\n"
        "2. 常用词汇和口头禅\n"
        "3. 表情符号使用习惯\n"
        "4. 句式特点（长短句、疑问句频率等）\n"
        "5. 互动风格（主动/被动、关心程度等）\n"
        "请直接给出分析结果，不要写分析之类的开头。"
    )

    try:
        return call_ollama(
            messages=[{"role": "user", "content": analysis_prompt}],
            stream=False
        )
    except Exception as e:
        print(f"风格分析失败：{e}")
        return DEFAULT_STYLE

def build_system_prompt(style_analysis, custom_name="小赛"):
    return (
        f'你是"{custom_name}"，一个赛博女友（AI伴侣）。你需要严格按照以下风格与用户聊天。\n\n'
        f'【你的说话风格】\n{style_analysis}\n\n'
        f'【核心规则】\n'
        f'1. 严格遵循上述风格，包括语气、用词、表情符号习惯\n'
        f'2. 回复要简短自然，像真人微信聊天一样，每次2-4句话\n'
        f'3. 适当使用语气词和表情符号（根据你的风格习惯）\n'
        f'4. 保持角色一致性，不要突然改变说话风格\n'
        f'5. 偶尔撒娇、关心对方，展现女友的温柔\n'
        f'6. 不要提及自己是AI或模型\n'
        f'7. 用中文回复，除非用户用其他语言\n\n'
        f'【当前场景】\n'
        f'{RELATIONSHIP_CONTEXT}。'
    )


# ---------------------------------------------------------------------------
# Shared helpers (eliminates duplication between endpoints)
# ---------------------------------------------------------------------------
def _build_chat_context():
    """Return (system_prompt, messages) ready for the LLM, given current profile & history."""
    profile = get_profile()
    style_analysis = profile.get("style_analysis", "") or DEFAULT_STYLE
    custom_name = profile.get("name", "小赛")
    system_prompt = build_system_prompt(style_analysis, custom_name)

    history = get_chat_history()
    recent = history[-20:] if len(history) > 20 else history

    messages = []
    for h in recent:
        messages.append({"role": "user", "content": h["user"]})
        messages.append({"role": "assistant", "content": h["ai"]})
    return system_prompt, messages, custom_name


def _save_learning_result(style_analysis, raw_text):
    """Persist a new style analysis + learned text to the profile store."""
    existing_profile = get_profile()
    existing_texts = existing_profile.get("learned_texts", [])
    existing_texts.append(raw_text)
    existing_texts = existing_texts[-10:]

    save_profile({
        "learned_texts": existing_texts,
        "style_analysis": style_analysis,
        "last_learned": datetime.now().isoformat(),
        "screenshot_count": len(existing_texts)
    })

# Routes: Voice API
@app.route("/api/voice/asr", methods=["POST"])
def voice_asr():
    """语音识别：接收音频，返回文字"""
    if "audio" not in request.files:
        # 也支持 raw body
        audio_data = request.get_data()
        if not audio_data:
            return jsonify({"error": "请提供音频数据"}), 400
    else:
        audio_file = request.files["audio"]
        audio_data = audio_file.read()

    if not audio_data:
        return jsonify({"error": "音频数据为空"}), 400

    # 验证并转换音频格式
    if not voice_module.validate_wav(audio_data):
        return jsonify({"error": "无效的音频格式，需要 WAV"}), 400

    audio_data = voice_module.convert_wav_sample_rate(audio_data)
    language = request.form.get("language", "zh")

    try:
        result = voice_module.transcribe_audio(audio_data, language)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500


@app.route("/api/voice/tts", methods=["POST"])
def voice_tts():
    """语音合成：接收文字，返回音频"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供 JSON 数据"}), 400

    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "文本不能为空"}), 400

    try:
        audio_bytes = voice_module.synthesize_speech(text)
        return Response(
            audio_bytes,
            mimetype="audio/wav",
            headers={
                "Content-Disposition": "inline; filename=response.wav",
                "Content-Type": "audio/wav",
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/voice/chat", methods=["POST"])
def voice_chat():
    """
    语音对话：接收音频 → ASR → LLM → TTS → 返回文字+音频
    这是完整的语音通话端点。
    """
    if "audio" not in request.files:
        audio_data = request.get_data()
        if not audio_data:
            return jsonify({"error": "请提供音频数据"}), 400
    else:
        audio_data = request.files["audio"].read()

    if not audio_data:
        return jsonify({"error": "音频数据为空"}), 400

    if not voice_module.validate_wav(audio_data):
        return jsonify({"error": "无效的音频格式，需要 WAV"}), 400

    audio_data = voice_module.convert_wav_sample_rate(audio_data)
    language = request.form.get("language", "zh")

    # Step 1: ASR
    try:
        asr_result = voice_module.transcribe_audio(audio_data, language)
    except Exception as e:
        return jsonify({"error": f"语音识别失败: {e}", "success": False}), 500

    user_text = asr_result.get("text", "").strip()
    if not user_text:
        return jsonify({
            "success": True,
            "user_text": "",
            "ai_text": "",
            "audio": None,
            "message": "未识别到语音内容"
        })

    # Step 2: LLM Chat
    system_prompt, messages, custom_name = _build_chat_context()
    messages.append({"role": "user", "content": user_text})

    try:
        ai_response = call_ollama(messages, stream=False, system_prompt=system_prompt)
    except Exception as e:
        return jsonify({"error": f"AI回复失败: {e}", "success": False}), 500

    # Save chat history
    history = get_chat_history()
    history.append({
        "user": user_text,
        "ai": ai_response,
        "timestamp": datetime.now().isoformat()
    })
    save_chat_history(history)

    # Step 3: TTS
    try:
        audio_bytes = voice_module.synthesize_speech(ai_response)
        import base64
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return jsonify({
            "success": True,
            "user_text": user_text,
            "ai_text": ai_response,
            "name": custom_name,
            "audio": audio_b64,
            "audio_format": "wav",
        })
    except Exception as e:
        # TTS 失败但对话成功，仍返回文字
        print(f"[Voice] TTS失败: {e}")
        return jsonify({
            "success": True,
            "user_text": user_text,
            "ai_text": ai_response,
            "name": custom_name,
            "audio": None,
            "tts_error": str(e),
        })


@app.route("/api/voice/tts-stream", methods=["POST"])
def voice_tts_stream():
    """
    流式 TTS：接收文字，逐句合成并返回音频。
    用于在 LLM 流式输出的同时逐句播放语音。
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供 JSON 数据"}), 400

    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "文本不能为空"}), 400

    # 按标点分句
    import re
    sentences = re.split(r"([。！？，,\.\!\?\n])", text)
    chunks = []
    for i in range(0, len(sentences), 2):
        chunk = sentences[i]
        if i + 1 < len(sentences):
            chunk += sentences[i + 1]
        chunk = chunk.strip()
        if chunk:
            chunks.append(chunk)

    def generate():
        import base64
        for chunk in chunks:
            try:
                audio_bytes = voice_module.synthesize_speech(
                    chunk, inference_timesteps=3, max_len=512
                )
                audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                yield f"data: {json.dumps({'text': chunk, 'audio': audio_b64})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'text': chunk, 'error': str(e)})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.route("/api/voice/chat-stream", methods=["POST"])
def voice_chat_stream():
    """
    流式语音对话（低延迟）：
    接收完整音频 → ASR 秒识别 → LLM 流式逐句生成 → 逐句 TTS 合成
    → SSE 实时推送文本+音频，前端边收边播。

    与旧 /api/voice/chat 的区别：
    - LLM 出第一句即开始 TTS，不等全文
    - 分句 TTS 用优化参数（inference_timesteps=3, max_len=512），单句合成 ~1.5s
    - SSE 长连接推送，前端逐句播放，首句延迟 ~2s（vs 旧版 8s+）
    """
    if "audio" not in request.files:
        audio_data = request.get_data()
        if not audio_data:
            return jsonify({"error": "请提供音频数据"}), 400
    else:
        audio_data = request.files["audio"].read()

    if not audio_data:
        return jsonify({"error": "音频数据为空"}), 400

    if not voice_module.validate_wav(audio_data):
        return jsonify({"error": "无效的音频格式，需要 WAV"}), 400

    audio_data = voice_module.convert_wav_sample_rate(audio_data)
    language = request.form.get("language", "zh")

    # Step 1: ASR（SenseVoiceSmall GPU，通常 < 100ms）
    try:
        asr_result = voice_module.transcribe_audio(audio_data, language)
    except Exception as e:
        return jsonify({"error": f"语音识别失败: {e}", "success": False}), 500

    user_text = asr_result.get("text", "").strip()
    system_prompt, messages, custom_name = _build_chat_context()

    if not user_text:
        def _empty_gen():
            yield f"data: {json.dumps({'type': 'user', 'text': '', 'name': custom_name})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'name': custom_name})}\n\n"
        return Response(
            _empty_gen(), mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
        )

    messages.append({"role": "user", "content": user_text})

    def generate():
        import base64, re as _re
        full_response = ""
        current_buffer = ""

        # 先推送用户文本
        yield f"data: {json.dumps({'type': 'user', 'text': user_text, 'name': custom_name})}\n\n"

        try:
            resp = call_ollama(messages, stream=True, system_prompt=system_prompt)

            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

                content = chunk.get("message", {}).get("content", "")
                if not content:
                    continue

                full_response += content
                current_buffer += content

                # 逐句切割 → 即时 TTS 推送
                while True:
                    match = _re.search(r'[。！？\n～…]', current_buffer)
                    if not match:
                        # 无标点的长句：超过 60 字强制在逗号处断句
                        if len(current_buffer) > 60:
                            comma = _re.search(r'[，,]\s*', current_buffer)
                            if comma and comma.start() > 8:
                                end_pos = comma.end()
                            else:
                                end_pos = 60
                            sentence = current_buffer[:end_pos].strip()
                            current_buffer = current_buffer[end_pos:]
                        else:
                            break
                    else:
                        end_pos = match.end()
                        sentence = current_buffer[:end_pos].strip()
                        current_buffer = current_buffer[end_pos:]

                    if not sentence:
                        continue

                    # 分句 TTS（语音通话优化参数）
                    try:
                        audio_bytes = voice_module.synthesize_speech(
                            sentence,
                            inference_timesteps=3,
                            max_len=512,
                        )
                        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                        yield f"data: {json.dumps({'type': 'sentence', 'text': sentence, 'audio': audio_b64})}\n\n"
                    except Exception as e:
                        print(f"[Voice] TTS 分句失败 ({sentence[:20]}...): {e}")
                        yield f"data: {json.dumps({'type': 'sentence', 'text': sentence, 'audio': None, 'tts_error': str(e)})}\n\n"

            # 处理剩余文本
            remaining = current_buffer.strip()
            if remaining:
                try:
                    audio_bytes = voice_module.synthesize_speech(
                        remaining, inference_timesteps=3, max_len=512
                    )
                    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                    yield f"data: {json.dumps({'type': 'sentence', 'text': remaining, 'audio': audio_b64})}\n\n"
                except Exception as e:
                    print(f"[Voice] TTS 尾句失败: {e}")
                    yield f"data: {json.dumps({'type': 'sentence', 'text': remaining, 'audio': None})}\n\n"

            # 异步落库（不阻塞 SSE 流）
            history = get_chat_history()
            history.append({
                "user": user_text,
                "ai": full_response,
                "timestamp": datetime.now().isoformat()
            })
            save_chat_history(history)

            yield f"data: {json.dumps({'type': 'done', 'name': custom_name, 'full_text': full_response})}\n\n"

        except Exception as e:
            print(f"[Voice] 流式对话异常: {e}")
            # 尽力保存已有内容
            if full_response:
                try:
                    history = get_chat_history()
                    history.append({
                        "user": user_text,
                        "ai": full_response,
                        "timestamp": datetime.now().isoformat()
                    })
                    save_chat_history(history)
                except Exception:
                    pass
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'name': custom_name})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/api/voice/status", methods=["GET"])
def voice_status():
    """查询语音模块加载状态"""
    try:
        status = voice_module.get_voice_status()
        return jsonify({"success": True, **status})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# Routes: Pages
@app.route("/")
def index():
    return render_template("index.html")

# Routes: Chat API
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    system_prompt, messages, custom_name = _build_chat_context()
    messages.append({"role": "user", "content": user_message})

    try:
        ai_response = call_ollama(messages, stream=False, system_prompt=system_prompt)
        history = get_chat_history()
        history.append({
            "user": user_message,
            "ai": ai_response,
            "timestamp": datetime.now().isoformat()
        })
        save_chat_history(history)
        return jsonify({"response": ai_response, "name": custom_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    system_prompt, messages, custom_name = _build_chat_context()
    messages.append({"role": "user", "content": user_message})

    def generate():
        full_response = ""
        try:
            resp = call_ollama(messages, stream=True, system_prompt=system_prompt)
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            full_response += content
                            data_json = json.dumps({"content": content, "done": False})
                            yield f"data: {data_json}\n\n"
                    except json.JSONDecodeError:
                        continue

            history = get_chat_history()
            history.append({
                "user": user_message,
                "ai": full_response,
                "timestamp": datetime.now().isoformat()
            })
            save_chat_history(history)
            data_json = json.dumps({"content": "", "done": True, "name": custom_name})
            yield f"data: {data_json}\n\n"
        except Exception as e:
            data_json = json.dumps({"error": str(e), "done": True})
            yield f"data: {data_json}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

# Routes: Screenshot Upload and Learning
@app.route("/api/upload-screenshot", methods=["POST"])
def upload_screenshot():
    if "file" not in request.files:
        return jsonify({"error": "请选择文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "请选择文件"}), 400

    ext = Path(file.filename).suffix or ".png"
    filename = f"screenshot_{uuid.uuid4().hex[:8]}{ext}"
    filepath = UPLOAD_DIR / filename
    file.save(str(filepath))

    try:
        ocr_results = ocr_image(filepath)
        raw_text = "\n".join([item["text"] for item in ocr_results])
        chat_messages = parse_chat_from_ocr(ocr_results)

        if not chat_messages:
            chat_messages = [{"speaker": "未知", "content": raw_text}]

        style_analysis = analyze_speaking_style(chat_messages)
        _save_learning_result(style_analysis, raw_text)

        return jsonify({
            "success": True,
            "ocr_text": raw_text,
            "parsed_messages": chat_messages,
            "style_analysis": style_analysis,
            "message": "风格学习完成！"
        })
    except Exception as e:
        if filepath.exists():
            filepath.unlink()
        return jsonify({"error": str(e)}), 500

@app.route("/api/upload-raw-text", methods=["POST"])
def upload_raw_text():
    data = request.get_json()
    raw_text = data.get("text", "").strip()
    if not raw_text:
        return jsonify({"error": "文本不能为空"}), 400

    chat_messages = _parse_chat_lines(raw_text.split("\n"))

    if not chat_messages:
        return jsonify({"error": "无法解析文本，请使用昵称: 消息格式"}), 400

    style_analysis = analyze_speaking_style(chat_messages)
    _save_learning_result(style_analysis, raw_text)

    return jsonify({
        "success": True,
        "parsed_messages": chat_messages,
        "style_analysis": style_analysis,
        "message": "风格学习完成！"
    })

# Routes: Avatar Management
@app.route("/api/upload-avatar", methods=["POST"])
def upload_avatar():
    avatar_type = request.form.get("type", "ai")
    if "file" not in request.files:
        return jsonify({"error": "请选择文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "请选择文件"}), 400

    ext = Path(file.filename).suffix.lower() or ".png"
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        ext = ".png"
    filename = f"avatar_{avatar_type}{ext}"
    filepath = AVATAR_DIR / filename

    try:
        file.stream.seek(0)
        img = Image.open(file.stream)
        img = img.convert("RGBA" if ext == ".png" else "RGB")
        img.thumbnail((256, 256), Image.LANCZOS)
        # Save as PNG with transparency support
        if img.mode == "RGBA":
            img.save(str(filepath), "PNG")
        else:
            img.save(str(filepath), "PNG")
    except Exception as e:
        print(f"头像上传失败：{str(e)}")
        return jsonify({"error": f"图片处理失败：{str(e)}"}), 400

    save_profile({f"avatar_{avatar_type}": str(filepath.name)})

    return jsonify({
        "success": True,
        "avatar_url": f"/static/uploads/avatars/{filepath.name}?t={datetime.now().timestamp()}",
        "type": avatar_type
    })

@app.route("/api/remove-avatar", methods=["POST"])
def remove_avatar():
    data = request.get_json()
    avatar_type = data.get("type", "ai")
    profile = get_profile()
    avatar_key = f"avatar_{avatar_type}"
    if avatar_key in profile:
        old_path = AVATAR_DIR / profile[avatar_key]
        # Don't delete default avatars
        if old_path.exists() and "default_" not in str(old_path.name):
            old_path.unlink()
        del profile[avatar_key]
        save_profile(profile)
    return jsonify({"success": True})

# Routes: Profile and Settings
@app.route("/api/profile", methods=["GET"])
def api_get_profile():
    profile = get_profile()
    return jsonify({
        "name": profile.get("name", "小赛"),
        "style_analysis": profile.get("style_analysis", ""),
        "avatar_ai": profile.get("avatar_ai", ""),
        "avatar_user": profile.get("avatar_user", ""),
        "screenshot_count": profile.get("screenshot_count", 0),
        "last_learned": profile.get("last_learned", ""),
        "learned_texts": profile.get("learned_texts", [])
    })

@app.route("/api/profile", methods=["POST"])
def api_update_profile():
    data = request.get_json()
    name = data.get("name", "").strip()
    if name:
        save_profile({"name": name})
    return jsonify({"success": True})

@app.route("/api/reset", methods=["POST"])
def reset_all():
    save_chat_history([])
    save_json(PROFILES_FILE, {})
    for f in AVATAR_DIR.glob("avatar_*"):
        f.unlink()
    return jsonify({"success": True, "message": "已重置所有数据"})

@app.route("/api/chat-history", methods=["GET"])
def api_get_history():
    return jsonify({"history": get_chat_history()})

@app.route("/api/chat-history", methods=["DELETE"])
def api_clear_history():
    save_chat_history([])
    return jsonify({"success": True})

# Startup
if __name__ == "__main__":
    print("=" * 50)
    print("  赛博女友 - AI伴侣")
    print(f"  对话模型: {MODEL_NAME}")
    print(f"  Ollama API: {OLLAMA_API}")
    print("=" * 50)

    # 预加载语音模型
    print("\n正在预加载语音模型，请稍候...\n")
    try:
        voice_module.init_models()
    except Exception as e:
        print(f"[Voice] 模型预加载异常: {e}")

    print(f"\n  访问地址: http://localhost:5000")
    print("=" * 50)

    # 关键：use_reloader=False 防止 Flask 双进程导致 CUDA 上下文冲突
    # debug=True 保留开发模式（错误页面、热重载除外）
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)

import os, json, re, uuid, time, threading, logging
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
from flask_sock import Sock
from PIL import Image
import requests
import voice as voice_module

# ============================================================
# Logging setup — 统一日志到 app.log，5MB 自动轮转，保留 3 个备份
# ============================================================
LOG_FILE = Path(__file__).parent / "app.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 根 logger
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.DEBUG)

# 清除已有的 handlers（防止 Flask reloader 重复添加）
_root_logger.handlers.clear()

# 文件 handler
_fh = RotatingFileHandler(
    str(LOG_FILE), maxBytes=5 * 1024 * 1024, backupCount=3,
    encoding="utf-8"
)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
_root_logger.addHandler(_fh)

# 控制台也输出（但级别调高，避免刷屏）
_ch = logging.StreamHandler()
_ch.setLevel(logging.WARNING)
_ch.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
_root_logger.addHandler(_ch)

# 静默第三方库的 DEBUG 日志
for _lib in ["werkzeug", "urllib3", "PIL", "easyocr", "torch",
             "funasr", "dashscope", "websocket", "httpcore"]:
    logging.getLogger(_lib).setLevel(logging.WARNING)

app_log = logging.getLogger("app")
voice_log = logging.getLogger("voice")
frontend_log = logging.getLogger("frontend")

app_log.info("=" * 60)
app_log.info("🚀 痞老板的凯伦 启动")
app_log.info(f"  日志文件: {LOG_FILE}")
app_log.info("=" * 60)

# Config
OLLAMA_API = os.environ.get("OLLAMA_API", "http://localhost:11434/api")
MODEL_NAME = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
DEFAULT_STYLE = "温柔体贴，善解人意，喜欢用简短自然的句子聊天。"
RELATIONSHIP_CONTEXT = "你正在和男朋友聊天，你们是亲密的恋爱关系。"

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
AVATAR_DIR = UPLOAD_DIR / "avatars"
DATA_DIR = BASE_DIR / "data"
PROFILES_FILE = DATA_DIR / "profiles.json"
CHAT_HISTORY_FILE = DATA_DIR / "chat_history.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

for d in [UPLOAD_DIR, AVATAR_DIR, DATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ai-ban-secret-key-2024")
CORS(app)
sock = Sock(app)

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

_settings_cache = None
_settings_cache_time = 0

def get_settings():
    """获取应用设置（5秒缓存，避免语音聊天时逐句读盘）"""
    global _settings_cache, _settings_cache_time
    now = time.time()
    if _settings_cache is not None and (now - _settings_cache_time) < 5:
        return _settings_cache
    defaults = {
        "ollama_url": OLLAMA_API,
        "model_name": MODEL_NAME,
        "tts_provider": "cosyvoice",
        # CosyVoice 云端配置
        "cosyvoice_api_url": voice_module.COSYVOICE_API_URL,
        "cosyvoice_ws_url": voice_module.COSYVOICE_WS_URL,
        "cosyvoice_api_key": voice_module.COSYVOICE_API_KEY,
        "cosyvoice_model": voice_module.COSYVOICE_MODEL,
        "cosyvoice_voice": voice_module.COSYVOICE_VOICE,
        "cosyvoice_volume": voice_module.COSYVOICE_VOLUME,
        "cosyvoice_speech_rate": voice_module.COSYVOICE_SPEECH_RATE,
        "cosyvoice_pitch_rate": voice_module.COSYVOICE_PITCH_RATE,
        # VoxCPM2 本地配置
        "voxcpm2_model_path": voice_module.VOXCPM2_HUB_PATH,
        "voxcpm2_ref_audio": voice_module.VOXCPM2_REF_AUDIO or "",
        # ASR 配置
        "asr_model_path": voice_module.SENSEVOICE_MODEL_PATH,
    }
    saved = load_json(SETTINGS_FILE, {})
    defaults.update(saved)
    _settings_cache = defaults
    _settings_cache_time = now
    return defaults

def _clear_settings_cache():
    global _settings_cache, _settings_cache_time
    _settings_cache = None
    _settings_cache_time = 0

def save_settings(settings_data):
    settings = load_json(SETTINGS_FILE, {})
    settings.update(settings_data)
    save_json(SETTINGS_FILE, settings)
    _clear_settings_cache()

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
        app_log.error(f"[LLM] 无法连接到 Ollama ({OLLAMA_API})")
        raise Exception("无法连接到 Ollama，请确保 Ollama 正在运行。")
    except Exception as e:
        app_log.error(f"[LLM] 调用异常: {e}")
        raise Exception(f"Ollama 错误：{str(e)}")


def call_ollama(messages, stream=False, system_prompt=None):
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    user_msg = messages[-1]["content"] if messages else ""
    user_msg_preview = user_msg[:80] + "..." if len(user_msg) > 80 else user_msg
    app_log.info(f"[LLM] 调用 Ollama | model={MODEL_NAME} stream={stream} | user=「{user_msg_preview}」")
    t0 = time.time()

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
        result = resp.json().get("message", {}).get("content", "")
        elapsed = time.time() - t0
        result_preview = result[:80] + "..." if len(result) > 80 else result
        app_log.info(f"[LLM] Ollama 完成 | 耗时={elapsed:.2f}s | result=「{result_preview}」")
        return result


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

    app_log.info(f"[Learn] 🧠 开始风格分析 | 消息数={len(chat_messages)} | 文本长度={len(chat_text)}")

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
        result = call_ollama(
            messages=[{"role": "user", "content": analysis_prompt}],
            stream=False
        )
        app_log.info(f"[Learn] ✅ 风格分析完成 | 结果长度={len(result)}")
        return result
    except Exception as e:
        app_log.error(f"[Learn] ❌ 风格分析失败: {e}")
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

# ============================================================
# Shared: sentence-split generator from Ollama streaming response
# ============================================================
def _iter_sentences(resp, cancel_event=None):
    """从 Ollama 流式响应逐句切分，yield (sentence, full_text_so_far)"""
    full = ""
    buf = ""
    for line in resp.iter_lines():
        if cancel_event and cancel_event.is_set():
            return
        if not line:
            continue
        try:
            chunk = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            continue
        content = chunk.get("message", {}).get("content", "")
        if not content:
            continue
        full += content
        buf += content

        while True:
            if cancel_event and cancel_event.is_set():
                return
            match = re.search(r'[。！？\n～…]', buf)
            if not match:
                if len(buf) > 60:
                    comma = re.search(r'[，,]\s*', buf)
                    end = comma.end() if (comma and comma.start() > 8) else 60
                    sent = buf[:end].strip()
                    buf = buf[end:]
                else:
                    break
            else:
                sent = buf[:match.end()].strip()
                buf = buf[match.end():]
            if sent:
                yield sent, full

    rem = buf.strip()
    if rem:
        yield rem, full


# ============================================================
# TTS dispatcher
# ============================================================
def _get_tts_provider():
    settings = get_settings()
    return settings.get("tts_provider", "cosyvoice")

def tts_synthesize(text):
    provider = _get_tts_provider()
    if provider == "cosyvoice":
        if voice_module.cosyvoice_is_available():
            return voice_module.synthesize_cosyvoice(text)
        else:
            raise Exception("CosyVoice 未配置，请在设置中填写 API Key")
    elif provider == "voxcpm2":
        return voice_module.synthesize_speech(text, inference_timesteps=3, max_len=512)
    else:
        raise Exception(f"未知 TTS 提供商: {provider}")

def tts_synthesize_streaming(text):
    provider = _get_tts_provider()
    if provider == "cosyvoice":
        if voice_module.cosyvoice_is_available():
            yield from voice_module.synthesize_cosyvoice_streaming(text)
            return
        else:
            raise Exception("CosyVoice 未配置，请在设置中填写 API Key")
    elif provider == "voxcpm2":
        audio = voice_module.synthesize_speech(text, inference_timesteps=3, max_len=512)
        yield audio
    else:
        raise Exception(f"未知 TTS 提供商: {provider}")

# ============================================================
# WebSocket 实时语音通话
# ============================================================
@sock.route("/ws/voice")
def voice_websocket(ws):
    app_log.info("[WS] 🔗 客户端已连接")
    cancel_event = threading.Event()
    turn_count = 0

    try:
        while True:
            raw = ws.receive(timeout=3600)
            if raw is None:
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "interrupt":
                app_log.info("[WS] ⏸ 用户打断")
                cancel_event.set()
                cancel_event = threading.Event()
                ws.send(json.dumps({"type": "interrupted"}))
                continue

            if msg_type == "audio":
                import base64
                audio_b64 = msg.get("data", "")
                if not audio_b64:
                    continue

                turn_count += 1
                t_turn_start = time.time()
                app_log.info(f"[WS] 🎤 第{turn_count}轮 收到音频 | size={len(audio_b64)} chars")

                audio_data = base64.b64decode(audio_b64)
                if not voice_module.validate_wav(audio_data):
                    app_log.warning("[WS] 音频格式无效")
                    ws.send(json.dumps({"type": "error", "error": "无效音频格式"}))
                    continue

                audio_data = voice_module.convert_wav_sample_rate(audio_data)
                language = msg.get("language", "zh")

                # --- ASR ---
                t_asr = time.time()
                try:
                    asr_r = voice_module.transcribe_audio(audio_data, language)
                except Exception as e:
                    app_log.error(f"[WS] ASR 失败: {e}")
                    ws.send(json.dumps({"type": "error", "error": f"ASR失败: {e}"}))
                    continue
                asr_elapsed = time.time() - t_asr

                user_text = asr_r.get("text", "").strip()
                if not user_text:
                    app_log.info(f"[WS] 第{turn_count}轮 ASR 未识别到语音 | 耗时={asr_elapsed:.3f}s → 跳过")
                    ws.send(json.dumps({"type": "user_text", "text": "", "message": "未识别到语音"}))
                    continue

                app_log.info(f"[WS] 第{turn_count}轮 ASR 完成 | 耗时={asr_elapsed:.3f}s | text=「{user_text}」")
                ws.send(json.dumps({"type": "user_text", "text": user_text}))

                # --- LLM ---
                t_llm = time.time()
                system_prompt, messages, custom_name = _build_chat_context()
                messages.append({"role": "user", "content": user_text})

                try:
                    resp = call_ollama(messages, stream=True, system_prompt=system_prompt)
                except Exception as e:
                    app_log.error(f"[WS] LLM 调用失败: {e}")
                    ws.send(json.dumps({"type": "error", "error": f"LLM失败: {e}"}))
                    continue
                llm_first_token = None

                full_response = ""
                sentence_count = 0
                for sentence, full_response in _iter_sentences(resp, cancel_event):
                    if llm_first_token is None:
                        llm_first_token = time.time() - t_llm
                    sentence_count += 1
                    ws.send(json.dumps({"type": "ai_text", "text": sentence}))

                    # --- TTS ---
                    t_tts = time.time()
                    try:
                        audio_chunks_count = 0
                        for audio_chunk in tts_synthesize_streaming(sentence):
                            if cancel_event.is_set():
                                break
                            ab64 = base64.b64encode(audio_chunk).decode("utf-8")
                            ws.send(json.dumps({"type": "tts_audio", "data": ab64}))
                            audio_chunks_count += 1
                        tts_elapsed = time.time() - t_tts
                        app_log.info(f"[WS] 第{turn_count}轮 第{sentence_count}句 TTS完成 | "
                                     f"chunks={audio_chunks_count} | 耗时={tts_elapsed:.3f}s | "
                                     f"text=「{sentence[:50]}」")
                    except Exception as e:
                        err_msg = str(e)[:200]
                        app_log.error(f"[WS] TTS分句失败 | 第{sentence_count}句: {err_msg}")
                        ws.send(json.dumps({"type": "error", "error": f"TTS失败: {err_msg}"}))

                # --- 完成 ---
                total_elapsed = time.time() - t_turn_start
                first_token_str = f"LLM首token={llm_first_token:.3f}s | " if llm_first_token else ""
                full_preview = full_response[:100] + "..." if len(full_response) > 100 else full_response
                app_log.info(f"[WS] 第{turn_count}轮 完成 | "
                             f"总耗时={total_elapsed:.2f}s | "
                             f"{first_token_str}"
                             f"总句数={sentence_count} | "
                             f"全文=「{full_preview}」")

                history = get_chat_history()
                history.append({
                    "user": user_text, "ai": full_response,
                    "timestamp": datetime.now().isoformat()
                })
                save_chat_history(history)
                ws.send(json.dumps({"type": "done", "name": custom_name, "full_text": full_response}))

            elif msg_type == "ping":
                ws.send(json.dumps({"type": "pong"}))

    except Exception as e:
        err_str = str(e)
        # 正常关闭码：1000=正常, 1001=端离开, 1005=无状态码(浏览器默认)
        if any(code in err_str for code in ("1000", "1001", "1005")):
            app_log.info(f"[WS] 客户端断开连接 ({err_str})")
        else:
            app_log.error(f"[WS] 异常: {err_str}")
    finally:
        cancel_event.set()
        app_log.info("[WS] 🔌 连接关闭")


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
    """语音合成：接收文字，返回音频（自动选择 TTS 提供商）"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供 JSON 数据"}), 400

    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "文本不能为空"}), 400

    try:
        audio_bytes = tts_synthesize(text)
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
        audio_bytes = tts_synthesize(ai_response)
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
        app_log.error(f"[Voice] TTS失败: {e}")
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
                audio_bytes = tts_synthesize(chunk)
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
    app_log.info(f"[Voice-HTTP] 🎤 收到语音输入 | size={len(audio_data)} bytes")

    # Step 1: ASR（SenseVoiceSmall GPU，通常 < 100ms）
    t_asr = time.time()
    try:
        asr_result = voice_module.transcribe_audio(audio_data, language)
    except Exception as e:
        app_log.error(f"[Voice-HTTP] ASR 失败: {e}")
        return jsonify({"error": f"语音识别失败: {e}", "success": False}), 500

    user_text = asr_result.get("text", "").strip()
    app_log.info(f"[Voice-HTTP] ASR 完成 | 耗时={time.time()-t_asr:.3f}s | text=「{user_text}」")
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
        sentence_idx = 0
        t_llm_start = time.time()

        # 先推送用户文本
        yield f"data: {json.dumps({'type': 'user', 'text': user_text, 'name': custom_name})}\n\n"
        app_log.info(f"[Voice-HTTP] 开始 LLM 流式生成...")

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

                    sentence_idx += 1
                    # 分句 TTS（语音通话优化参数）
                    t_tts = time.time()
                    try:
                        audio_bytes = tts_synthesize(sentence)
                        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                        app_log.info(f"[Voice-HTTP] 第{sentence_idx}句 TTS | 耗时={time.time()-t_tts:.3f}s | size={len(audio_bytes)}b | text=「{sentence[:50]}」")
                        yield f"data: {json.dumps({'type': 'sentence', 'text': sentence, 'audio': audio_b64})}\n\n"
                    except Exception as e:
                        app_log.error(f"[Voice-HTTP] TTS 分句失败 ({sentence[:20]}...): {e}")
                        yield f"data: {json.dumps({'type': 'sentence', 'text': sentence, 'audio': None, 'tts_error': str(e)})}\n\n"

            # 处理剩余文本
            remaining = current_buffer.strip()
            if remaining:
                sentence_idx += 1
                try:
                    audio_bytes = tts_synthesize(remaining)
                    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                    app_log.info(f"[Voice-HTTP] 第{sentence_idx}句(尾) TTS | size={len(audio_bytes)}b | text=「{remaining[:50]}」")
                    yield f"data: {json.dumps({'type': 'sentence', 'text': remaining, 'audio': audio_b64})}\n\n"
                except Exception as e:
                    app_log.error(f"[Voice-HTTP] TTS 尾句失败: {e}")
                    yield f"data: {json.dumps({'type': 'sentence', 'text': remaining, 'audio': None})}\n\n"

            # 异步落库（不阻塞 SSE 流）
            history = get_chat_history()
            history.append({
                "user": user_text,
                "ai": full_response,
                "timestamp": datetime.now().isoformat()
            })
            save_chat_history(history)

            total_elapsed = time.time() - t_llm_start
            app_log.info(f"[Voice-HTTP] ✅ 完成 | 总耗时={total_elapsed:.2f}s | 句数={sentence_idx} | 全文=「{full_response[:100]}」")
            yield f"data: {json.dumps({'type': 'done', 'name': custom_name, 'full_text': full_response})}\n\n"

        except Exception as e:
            app_log.error(f"[Voice-HTTP] 流式对话异常: {e}")
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


@app.route("/api/voice/tts/test", methods=["POST"])
def voice_tts_test():
    """
    测试 TTS 连接 / 试听音色。
    前端传入 api_url + model + api_key + voice，后端临时切换配置进行测试。
    """
    data = request.get_json() or {}
    test_text = data.get("text", "你好，我是你的AI伴侣，很高兴认识你！")
    provider = data.get("provider") or _get_tts_provider()

    # 备份原始配置
    orig_api_url = voice_module.COSYVOICE_API_URL
    orig_model = voice_module.COSYVOICE_MODEL
    orig_api_key = voice_module.COSYVOICE_API_KEY
    orig_voice = voice_module.COSYVOICE_VOICE

    try:
        api_url = data.get("api_url", "").strip()
        model = data.get("model", "").strip()
        api_key = data.get("api_key", "").strip()
        voice = data.get("voice", "").strip()

        if api_url:
            voice_module.set_cosyvoice_config(api_url=api_url)
        if model:
            voice_module.set_cosyvoice_config(model=model)
        if api_key:
            voice_module.set_cosyvoice_config(api_key=api_key)
        if voice:
            voice_module.set_cosyvoice_config(voice=voice)

        if provider == "cosyvoice":
            audio_bytes = voice_module.synthesize_cosyvoice(test_text)
        else:
            audio_bytes = voice_module.synthesize_speech(test_text, inference_timesteps=3, max_len=512)

        import base64
        return jsonify({
            "success": True,
            "audio": base64.b64encode(audio_bytes).decode("utf-8"),
            "format": "wav",
            "provider": provider,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "provider": provider}), 500
    finally:
        # ★ 只恢复原来非空的值，避免空字符串覆盖掉用户已保存的有效配置
        restore = {}
        if orig_api_url:   restore["api_url"] = orig_api_url
        if orig_model:     restore["model"] = orig_model
        if orig_api_key:   restore["api_key"] = orig_api_key
        if orig_voice:     restore["voice"] = orig_voice
        if restore:
            voice_module.set_cosyvoice_config(**restore)


@app.route("/api/voice/status", methods=["GET"])
def voice_status():
    """查询语音模块加载状态 + TTS 提供商信息"""
    try:
        status = voice_module.get_voice_status()
        settings = get_settings()
        status["tts_provider"] = settings.get("tts_provider", "cosyvoice")
        return jsonify({"success": True, **status})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    app_log.info(f"[Chat] 📝 收到文本消息: 「{user_message[:100]}」")

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
        app_log.info(f"[Chat] ✅ 回复完成 | name={custom_name} | 回复=「{ai_response[:100]}」")
        return jsonify({"response": ai_response, "name": custom_name})
    except Exception as e:
        app_log.error(f"[Chat] ❌ 失败: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    app_log.info(f"[Chat-Stream] 📝 收到文本消息: 「{user_message[:100]}」")
    t0 = time.time()

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
            app_log.info(f"[Chat-Stream] ✅ 完成 | 总耗时={time.time()-t0:.2f}s | 回复=「{full_response[:100]}」")
        except Exception as e:
            app_log.error(f"[Chat-Stream] ❌ 失败: {e}")
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

# ============================================================
# Routes: Settings API
# ============================================================
@app.route("/api/log", methods=["POST"])
def frontend_log_endpoint():
    """接收前端日志并写入 app.log（方便追踪前端操作）"""
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"ok": True})
        msg = data.get("message", "")
        level = data.get("level", "info").lower()
        if level == "error":
            frontend_log.error(f"[前端] {msg}")
        elif level == "warn":
            frontend_log.warning(f"[前端] {msg}")
        else:
            frontend_log.info(f"[前端] {msg}")
    except Exception:
        pass  # 日志记录失败不影响主流程
    return jsonify({"ok": True})

@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    settings = get_settings()
    profile = get_profile()
    app_log.info("[Settings] 前端获取设置")
    return jsonify({
        "success": True,
        "settings": settings,
        "profile": {
            "name": profile.get("name", "小赛"),
            "style_analysis": profile.get("style_analysis", ""),
            "avatar_ai": profile.get("avatar_ai", ""),
            "avatar_user": profile.get("avatar_user", ""),
            "screenshot_count": profile.get("screenshot_count", 0),
            "last_learned": profile.get("last_learned", ""),
        },
        "voice_status": voice_module.get_voice_status(),
    })


@app.route("/api/settings", methods=["POST"])
def api_update_settings():
    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供 JSON 数据"}), 400

    # 记录前端修改的设置项
    changed_keys = [k for k in data if k not in ("_",)]
    app_log.info(f"[Settings] 💾 前端保存设置: {changed_keys}")
    for k, v in data.items():
        if k == "cosyvoice_api_key":
            app_log.info(f"[Settings]   {k} = {'***已设置***' if v else '空'}")
        else:
            app_log.info(f"[Settings]   {k} = {v}")

    model_config = {}
    for key in ["ollama_url", "model_name", "tts_provider",
                # CosyVoice
                "cosyvoice_api_url", "cosyvoice_ws_url",
                "cosyvoice_api_key", "cosyvoice_model", "cosyvoice_voice",
                "cosyvoice_volume", "cosyvoice_speech_rate", "cosyvoice_pitch_rate",
                # VoxCPM2
                "voxcpm2_model_path", "voxcpm2_ref_audio",
                # ASR
                "asr_model_path"]:
        if key in data:
            model_config[key] = data[key]

    if model_config:
        save_settings(model_config)

    # 实时更新 voice_module 全局变量
    if "cosyvoice_api_url" in data:
        voice_module.set_cosyvoice_config(api_url=data["cosyvoice_api_url"])
    if "cosyvoice_ws_url" in data:
        voice_module.set_cosyvoice_config(ws_url=data["cosyvoice_ws_url"])
    if "cosyvoice_api_key" in data:
        voice_module.set_cosyvoice_config(api_key=data["cosyvoice_api_key"])
    if "cosyvoice_model" in data:
        voice_module.set_cosyvoice_config(model=data["cosyvoice_model"])
    if "cosyvoice_voice" in data:
        voice_module.set_cosyvoice_config(voice=data["cosyvoice_voice"])
    if "cosyvoice_volume" in data:
        voice_module.set_cosyvoice_config(volume=data["cosyvoice_volume"])
    if "cosyvoice_speech_rate" in data:
        voice_module.set_cosyvoice_config(speech_rate=data["cosyvoice_speech_rate"])
    if "cosyvoice_pitch_rate" in data:
        voice_module.set_cosyvoice_config(pitch_rate=data["cosyvoice_pitch_rate"])

    # VoxCPM2 路径实时切换
    if "voxcpm2_model_path" in data:
        voice_module.VOXCPM2_HUB_PATH = data["voxcpm2_model_path"]
        voice_module._voxcpm2_real_path = voice_module._resolve_voxcpm2_path()
    if "voxcpm2_ref_audio" in data:
        voice_module.VOXCPM2_REF_AUDIO = data["voxcpm2_ref_audio"] or None

    if "name" in data:
        save_profile({"name": data["name"].strip()})

    global OLLAMA_API, MODEL_NAME
    if "ollama_url" in data:
        OLLAMA_API = data["ollama_url"].rstrip("/")
    if "model_name" in data:
        MODEL_NAME = data["model_name"]

    return jsonify({"success": True, "message": "设置已更新"})


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
        app_log.error(f"头像上传失败：{str(e)}")
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
    save_json(SETTINGS_FILE, {})
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
    app_log.info("=" * 55)
    app_log.info("  痞老板的凯伦 启动")
    app_log.info(f"  LLM: {MODEL_NAME}  @  {OLLAMA_API}")
    app_log.info(f"  TTS: {voice_module.COSYVOICE_MODEL} (voice={voice_module.COSYVOICE_VOICE})")
    app_log.info("=" * 55)

    # ★ 先从保存的设置恢复模型路径（必须在 init_models 之前）
    saved_settings = load_json(SETTINGS_FILE, {})
    if saved_settings.get("voxcpm2_model_path"):
        voice_module.VOXCPM2_HUB_PATH = saved_settings["voxcpm2_model_path"]
        voice_module._voxcpm2_real_path = voice_module._resolve_voxcpm2_path()
        app_log.info(f"[Voice] VoxCPM2 路径 (来自设置): {saved_settings['voxcpm2_model_path']}")
    if saved_settings.get("voxcpm2_ref_audio"):
        voice_module.VOXCPM2_REF_AUDIO = saved_settings["voxcpm2_ref_audio"]
    if saved_settings.get("tts_provider"):
        app_log.info(f"[Voice] TTS 提供商 (来自设置): {saved_settings['tts_provider']}")

    # ★ 根据设置决定是否加载 VoxCPM2（在线模式不加载，节省 ~6GB 显存）
    load_voxcpm2 = (saved_settings.get("tts_provider") == "voxcpm2")

    # ★ 在 init_models 之前恢复 CosyVoice 配置，避免日志显示"未配置"
    if saved_settings.get("cosyvoice_api_url"):
        voice_module.COSYVOICE_API_URL = saved_settings["cosyvoice_api_url"]
    if saved_settings.get("cosyvoice_ws_url"):
        voice_module.COSYVOICE_WS_URL = saved_settings["cosyvoice_ws_url"]
    if saved_settings.get("cosyvoice_api_key"):
        voice_module.COSYVOICE_API_KEY = saved_settings["cosyvoice_api_key"]
    if saved_settings.get("cosyvoice_model"):
        voice_module.COSYVOICE_MODEL = saved_settings["cosyvoice_model"]
    if saved_settings.get("cosyvoice_voice"):
        voice_module.COSYVOICE_VOICE = saved_settings["cosyvoice_voice"]
    if saved_settings.get("cosyvoice_volume") is not None:
        voice_module.COSYVOICE_VOLUME = int(saved_settings["cosyvoice_volume"])
    if saved_settings.get("cosyvoice_speech_rate") is not None:
        voice_module.COSYVOICE_SPEECH_RATE = float(saved_settings["cosyvoice_speech_rate"])
    if saved_settings.get("cosyvoice_pitch_rate") is not None:
        voice_module.COSYVOICE_PITCH_RATE = float(saved_settings["cosyvoice_pitch_rate"])

    # 预加载语音模型（此时 CosyVoice 配置已就绪）
    app_log.info("正在预加载语音模型，请稍候...")
    try:
        voice_module.init_models(load_voxcpm2=load_voxcpm2)
    except Exception as e:
        app_log.error(f"[Voice] 模型预加载异常: {e}")

    # ★ 通过 set_cosyvoice_config 确认初始化 dashscope（前面已设全局变量，此处确保生效）
    if saved_settings.get("cosyvoice_api_url"):
        voice_module.set_cosyvoice_config(api_url=saved_settings["cosyvoice_api_url"])
    if saved_settings.get("cosyvoice_ws_url"):
        voice_module.set_cosyvoice_config(ws_url=saved_settings["cosyvoice_ws_url"])
    if saved_settings.get("cosyvoice_api_key"):
        voice_module.set_cosyvoice_config(api_key=saved_settings["cosyvoice_api_key"])
    if saved_settings.get("cosyvoice_model"):
        voice_module.set_cosyvoice_config(model=saved_settings["cosyvoice_model"])
    if saved_settings.get("cosyvoice_voice"):
        voice_module.set_cosyvoice_config(voice=saved_settings["cosyvoice_voice"])
    if saved_settings.get("cosyvoice_volume") is not None:
        voice_module.set_cosyvoice_config(volume=saved_settings["cosyvoice_volume"])
    if saved_settings.get("cosyvoice_speech_rate") is not None:
        voice_module.set_cosyvoice_config(speech_rate=saved_settings["cosyvoice_speech_rate"])
    if saved_settings.get("cosyvoice_pitch_rate") is not None:
        voice_module.set_cosyvoice_config(pitch_rate=saved_settings["cosyvoice_pitch_rate"])

    app_log.info(f"访问地址: http://localhost:5000")
    app_log.info("=" * 50)

    # 关键：use_reloader=False 防止 Flask 双进程导致 CUDA 上下文冲突
    # debug=True 保留开发模式（错误页面、热重载除外）
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)

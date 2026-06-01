"""
语音模块 — SenseVoiceSmall (语音识别) + VoxCPM2 (语音合成)

启动时调用 init_models() 预加载所有模型，确保前端打开即可使用语音通话。
"""

import os, io, wave, tempfile, sys, json
import numpy as np
from pathlib import Path

# ============================================================
# 模型路径配置
# ============================================================
SENSEVOICE_MODEL_PATH = os.environ.get(
    "SENSEVOICE_MODEL_PATH",
    r"C:\Users\15123\.cache\modelscope\hub\models\iic\SenseVoiceSmall"
)
VOXCPM2_HUB_PATH = os.environ.get(
    "VOXCPM2_MODEL_PATH",
    r"C:\Users\15123\.cache\huggingface\hub\models--openbmb--VoxCPM2"
)
VOXCPM2_REF_AUDIO = os.environ.get("VOXCPM2_REF_AUDIO", None)
VOXCPM2_REF_TEXT = os.environ.get("VOXCPM2_REF_TEXT", "")
# ASR 要求 16kHz 单声道输入；VoxCPM2 输出 48kHz
ASR_SAMPLE_RATE = 16000
TTS_SAMPLE_RATE = 48000

# ============================================================
# 模型实例（init_models() 中填充）
# ============================================================
_sense_voice_model = None      # FunASR AutoModel 实例
_voxcpm2_model = None          # voxcpm.VoxCPM 实例
_voxcpm2_real_path = None      # 解析后的 VoxCPM2 实际路径
_voxcpm2_has_gpu = False       # VoxCPM2 是否使用 GPU


def _cuda_available():
    """检测 PyTorch CUDA 是否可用（可通过 FORCE_CPU=1 环境变量强制 CPU）"""
    if os.environ.get("FORCE_CPU", "").strip() == "1":
        return False
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def _get_torch_version():
    try:
        import torch
        version = torch.__version__
        if "+cpu" in version:
            return f"{version} (CPU-only)"
        return version
    except ImportError:
        return "未安装"


# ============================================================
# 路径解析
# ============================================================
def _resolve_voxcpm2_path():
    """解析 VoxCPM2 的真实模型路径（自动处理 HF 缓存 snapshots 结构）"""
    hub = Path(VOXCPM2_HUB_PATH)
    if not hub.exists():
        return VOXCPM2_HUB_PATH

    # 直接是模型目录（含 config.json）
    if (hub / "config.json").exists():
        return str(hub)

    # HF 缓存结构：snapshots/<hash>/
    snapshots_dir = hub / "snapshots"
    if snapshots_dir.exists():
        for snap in sorted(snapshots_dir.iterdir(), reverse=True):
            if snap.is_dir() and (snap / "config.json").exists():
                return str(snap)

    return VOXCPM2_HUB_PATH


# ============================================================
# 模型初始化（启动时调用，一次性加载完毕）
# ============================================================
def init_models():
    """
    预加载所有语音模型。在 app.py 启动时调用。
    加载完成后前端即可直接使用语音通话，无需等待。
    自动检测 GPU 并启用加速。
    """
    global _voxcpm2_real_path
    print("=" * 50)
    print("[Voice] 开始预加载语音模型...")
    print(f"[Voice] PyTorch: {_get_torch_version()}")

    # GPU 检测与优化设置
    import torch
    gpu_ok = _cuda_available()
    if gpu_ok:
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"[Voice] GPU: {gpu_name} ({gpu_mem:.1f} GB VRAM)")
        # 启用 cuDNN benchmark 优化固定尺寸输入的推理
        torch.backends.cudnn.benchmark = True
        # 允许 TF32 加速（Ampere+ 架构，RTX 5060 为 Blackwell，完全支持）
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    else:
        print("[Voice] GPU: 不可用（使用 CPU 模式）")

    print("=" * 50)

    # --- SenseVoiceSmall ---
    _init_asr()

    # --- VoxCPM2 ---
    _voxcpm2_real_path = _resolve_voxcpm2_path()
    _init_tts()

    # --- 状态汇总 ---
    print("=" * 50)
    asr_ok = _sense_voice_model is not None
    tts_ok = _voxcpm2_model is not None
    print(f"[Voice] ASR (SenseVoiceSmall): {'✓ 已加载' if asr_ok else '✗ 未加载'}  "
          f"设备: {'GPU' if gpu_ok else 'CPU'}")
    print(f"[Voice] TTS (VoxCPM2):       {'✓ 已加载' if tts_ok else '✗ 未加载（文字对话仍可用）'}  "
          f"设备: {'GPU' if _voxcpm2_has_gpu else 'CPU'}")
    if tts_ok and _voxcpm2_has_gpu:
        allocated = torch.cuda.memory_allocated(0) / 1024**3
        print(f"[Voice] GPU 显存占用: {allocated:.2f} GB")
    print("=" * 50)

    return asr_ok, tts_ok


def _init_asr():
    """加载 SenseVoiceSmall 模型（FunASR + GPU 加速）"""
    global _sense_voice_model
    try:
        from funasr import AutoModel
    except ImportError:
        print("[Voice] ✗ FunASR 未安装，ASR 不可用。pip install funasr")
        return

    model_path = SENSEVOICE_MODEL_PATH
    print(f"[Voice] 加载 ASR: {model_path}")

    if not Path(model_path).exists():
        print(f"[Voice] ✗ ASR 模型路径不存在: {model_path}")
        return

    gpu_available = _cuda_available()
    device = "cuda:0" if gpu_available else "cpu"
    try:
        _sense_voice_model = AutoModel(
            model=model_path,
            vad_model="fsmn-vad",
            vad_kwargs={"max_single_segment_time": 30000},
            device=device,
        )
        print(f"[Voice] ✓ SenseVoiceSmall 加载成功 (VAD, device={device}, "
              f"GPU={'Yes' if gpu_available else 'No'})")
    except Exception as e:
        print(f"[Voice] VAD 加载失败 ({e})，尝试无 VAD...")
        try:
            _sense_voice_model = AutoModel(model=model_path, device=device)
            print(f"[Voice] ✓ SenseVoiceSmall 加载成功 (无VAD, device={device})")
        except Exception as e2:
            print(f"[Voice] ✗ SenseVoiceSmall 加载失败: {e2}")


def _init_tts():
    """加载 VoxCPM2 模型（使用 voxcpm 专用包，GPU 加速）"""
    global _voxcpm2_model, _voxcpm2_has_gpu
    model_path = _voxcpm2_real_path

    if not model_path or not Path(model_path).exists():
        print(f"[Voice] ✗ VoxCPM2 模型路径不存在: {model_path}")
        return

    # 读取 config 确认模型类型
    config_path = Path(model_path) / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
        arch = config.get("architecture", "unknown")
        print(f"[Voice] VoxCPM2 架构: {arch}")
    else:
        print(f"[Voice] ✗ config.json 未找到: {config_path}")
        return

    # ---- 方式1: voxcpm 专用包（推荐，用户已安装且 CLI 可用）----
    try:
        from voxcpm import VoxCPM

        gpu_available = _cuda_available()
        device = "cuda" if gpu_available else "cpu"
        print(f"[Voice] 通过 voxcpm 包加载 (device={device}, optimize={gpu_available})...")

        _voxcpm2_model = VoxCPM(
            voxcpm_model_path=model_path,
            enable_denoiser=False,    # 语音通话场景不需要降噪
            optimize=gpu_available,   # GPU 时启用优化（融合算子、编译加速）
            device=device,
        )
        _voxcpm2_has_gpu = gpu_available
        print(f"[Voice] ✓ VoxCPM2 加载成功 (voxcpm 包, device={device}, "
              f"输出={TTS_SAMPLE_RATE}Hz)")
        return
    except ImportError:
        print("[Voice] voxcpm 包未安装")
    except Exception as e:
        print(f"[Voice] voxcpm 加载失败: {e}")

    # ---- 方式2: voxcpm.from_pretrained（从 HF 自动下载/使用缓存）----
    try:
        from voxcpm import VoxCPM
        gpu_available = _cuda_available()
        device = "cuda" if gpu_available else "cpu"
        print(f"[Voice] 尝试 from_pretrained (device={device})...")
        _voxcpm2_model = VoxCPM.from_pretrained(
            hf_model_id="openbmb/VoxCPM2",
            device=device,
            local_files_only=True,
            enable_denoiser=False,
            optimize=gpu_available,
        )
        _voxcpm2_has_gpu = gpu_available
        print(f"[Voice] ✓ VoxCPM2 加载成功 (from_pretrained, device={device})")
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"[Voice] from_pretrained 失败: {e}")

    # ---- 方式3: CosyVoice（备选）----
    try:
        from cosyvoice.cli.cosyvoice import CosyVoice2
        _voxcpm2_model = CosyVoice2(model_path, load_jit=False, load_trt=False)
        print("[Voice] ✓ VoxCPM2 通过 CosyVoice2 加载成功")
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"[Voice] CosyVoice2 失败: {e}")

    try:
        from cosyvoice.cli.cosyvoice import CosyVoice
        _voxcpm2_model = CosyVoice(model_path)
        print("[Voice] ✓ VoxCPM2 通过 CosyVoice 加载成功")
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"[Voice] CosyVoice 失败: {e}")

    # ---- 全部失败 ----
    print("[Voice] ✗ VoxCPM2 加载失败，TTS 不可用")
    print("[Voice] 提示: pip install voxcpm")


# ============================================================
# 懒加载 fallback（正常情况下 init_models 已加载，不会走到这里）
# ============================================================
def _get_sense_voice():
    global _sense_voice_model
    if _sense_voice_model is None:
        _init_asr()
    if _sense_voice_model is None:
        raise Exception("SenseVoiceSmall 模型未加载，语音识别不可用")
    return _sense_voice_model


def _get_voxcpm2():
    global _voxcpm2_model, _voxcpm2_real_path
    if _voxcpm2_model is None:
        if _voxcpm2_real_path is None:
            _voxcpm2_real_path = _resolve_voxcpm2_path()
        _init_tts()
    if _voxcpm2_model is None:
        raise Exception("VoxCPM2 模型未加载，语音合成不可用")
    return _voxcpm2_model


# ============================================================
# SenseVoiceSmall — 语音识别 (ASR)
# ============================================================
def transcribe_audio(audio_data, language="zh"):
    """将 WAV 音频转录为文字"""
    model = _get_sense_voice()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_data)
        tmp_path = f.name
    try:
        result = model.generate(
            input=tmp_path, cache={}, language=language,
            use_itn=True, batch_size_s=60,
        )
        text = ""
        if result and len(result) > 0:
            text = result[0].get("text", "")
            # SenseVoice 返回格式如 "<|zh|>你好" → 去掉语言标签
            if text and "|>" in text:
                text = text.split("|>")[-1]
        return {"text": text.strip(), "language": language, "success": True}
    except Exception as e:
        print(f"[Voice] ASR失败: {e}")
        return {"text": "", "language": language, "success": False, "error": str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ============================================================
# VoxCPM2 — 文本转语音 (TTS)
# ============================================================
def synthesize_speech(text, output_path=None, ref_audio=None, ref_text=None,
                      inference_timesteps=None, max_len=None, normalize=False):
    """
    将文本合成为语音，返回 WAV bytes (48kHz, float32 → int16)

    VoxCPM2 的 generate() 返回 numpy float32 数组 (48kHz)。
    我们将其转换为 16-bit PCM WAV 返回给前端播放。

    参数:
        inference_timesteps: 扩散步数，None=默认6，语音通话传3以加速
        max_len: 最大生成长度，None=默认2048，语音通话传512以加速
        normalize: 是否归一化，默认False
    """
    import torch
    model = _get_voxcpm2()
    ref_audio = ref_audio or VOXCPM2_REF_AUDIO
    ref_text = ref_text or VOXCPM2_REF_TEXT

    auto_clean = False
    if output_path is None:
        tmp_fd, output_path = tempfile.mkstemp(suffix=".wav")
        os.close(tmp_fd)
        auto_clean = True

    try:
        # voxcpm.VoxCPM.generate() 返回 numpy float32 数组 (48kHz)
        _ts = inference_timesteps if inference_timesteps is not None else 6
        _ml = max_len if max_len is not None else 2048
        kwargs = {
            "text": text,
            "inference_timesteps": _ts,
            "max_len": _ml,
            "normalize": normalize,
        }
        if ref_audio and ref_text:
            kwargs["reference_wav_path"] = ref_audio
            kwargs["prompt_wav_path"] = ref_audio
            kwargs["prompt_text"] = ref_text

        audio_array = model.generate(**kwargs)

        # audio_array: numpy float32, shape=(N,), 48kHz
        if isinstance(audio_array, np.ndarray):
            # 限制幅度防止削波
            peak = np.max(np.abs(audio_array))
            if peak > 0.99:
                audio_array = audio_array * (0.95 / peak)

            # float32 → int16
            int16_audio = (audio_array * 32767).astype(np.int16)
            _write_wav(output_path, int16_audio, TTS_SAMPLE_RATE)
        elif isinstance(audio_array, torch.Tensor):
            audio_array = audio_array.squeeze().cpu().numpy()
            peak = np.max(np.abs(audio_array))
            if peak > 0.99:
                audio_array = audio_array * (0.95 / peak)
            int16_audio = (audio_array * 32767).astype(np.int16)
            _write_wav(output_path, int16_audio, TTS_SAMPLE_RATE)
        else:
            raise Exception(f"VoxCPM2 返回了未知数据类型: {type(audio_array)}")

        with open(output_path, "rb") as f:
            audio_bytes = f.read()
        if auto_clean:
            os.unlink(output_path)
        return audio_bytes

    except Exception as e:
        if auto_clean and os.path.exists(output_path):
            os.unlink(output_path)
        raise Exception(f"TTS合成失败: {str(e)}")


def _write_wav(filepath, samples, sample_rate):
    """写入单声道 16-bit PCM WAV 文件"""
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())


# ============================================================
# 音频工具
# ============================================================
def validate_wav(audio_data):
    return len(audio_data) >= 44 and audio_data[:4] == b"RIFF" and audio_data[8:12] == b"WAVE"


def convert_wav_sample_rate(audio_data, target_rate=ASR_SAMPLE_RATE):
    """重采样 WAV 到目标采样率（16kHz，SenseVoiceSmall 要求）"""
    if not validate_wav(audio_data):
        return audio_data
    with wave.open(io.BytesIO(audio_data), "rb") as wf:
        if wf.getframerate() == target_rate:
            return audio_data
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
    dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
    dtype = dtype_map.get(sampwidth, np.int16)
    samples = np.frombuffer(raw, dtype=dtype)
    if nchannels > 1:
        samples = samples.reshape(-1, nchannels).mean(axis=1).astype(dtype)
    try:
        import scipy.signal
        num = int(len(samples) * target_rate / wf.getframerate())
        resampled = scipy.signal.resample(samples.astype(np.float64), num).astype(np.int16)
    except ImportError:
        return audio_data
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf2:
        wf2.setnchannels(1)
        wf2.setsampwidth(2)
        wf2.setframerate(target_rate)
        wf2.writeframes(resampled.tobytes())
    return buf.getvalue()


def get_voice_status():
    return {
        "asr_loaded": _sense_voice_model is not None,
        "asr_model": SENSEVOICE_MODEL_PATH,
        "tts_loaded": _voxcpm2_model is not None,
        "tts_model": VOXCPM2_HUB_PATH,
        "tts_real_path": _voxcpm2_real_path,
        "tts_device": "GPU" if _voxcpm2_has_gpu else "CPU",
        "ref_audio": bool(VOXCPM2_REF_AUDIO),
        "cuda_available": _cuda_available(),
        "torch_version": _get_torch_version(),
    }


// ============================================================
// Cyber GF - Main JavaScript
// ============================================================

// State
const state = {
    aiName: '小赛',
    aiAvatar: '/static/uploads/avatars/default_ai.png',
    userAvatar: '/static/uploads/avatars/default_user.png',
    isStreaming: false,
    sidebarOpen: true,
    // Voice state
    voiceActive: false,
    voiceListening: false,
    voiceSpeaking: false,
    mediaRecorder: null,
    audioChunks: [],
    audioContext: null,
};

// DOM Elements
const el = (sel) => document.querySelector(sel);
const els = (sel) => document.querySelectorAll(sel);

const dom = {
    chatMessages: el('.chat-messages'),
    messageInput: el('#messageInput'),
    sendBtn: el('#sendBtn'),
    typingIndicator: el('#typingIndicator'),
    typingAvatarImg: el('#typingAvatarImg'),
    sidebar: el('#sidebar'),
    sidebarToggle: el('#sidebarToggle'),
    menuBtn: el('#menuBtn'),
    headerName: el('#headerName'),
    headerAvatarImg: el('#headerAvatarImg'),
    aiAvatarImg: el('#aiAvatarImg'),
    aiAvatarInput: el('#aiAvatarInput'),
    userAvatarImg: el('#userAvatarImg'),
    userAvatarInput: el('#userAvatarInput'),
    removeAiAvatar: el('#removeAiAvatar'),
    removeUserAvatar: el('#removeUserAvatar'),
    aiNameInput: el('#aiNameInput'),
    saveNameBtn: el('#saveNameBtn'),
    screenshotInput: el('#screenshotInput'),
    pasteTextBtn: el('#pasteTextBtn'),
    learnStatus: el('#learnStatus'),
    styleProfileBox: el('#styleProfileBox'),
    resetBtn: el('#resetBtn'),
    clearChatBtn: el('#clearChatBtn'),
    pasteModal: el('#pasteModal'),
    pasteTextArea: el('#pasteTextArea'),
    confirmPasteBtn: el('#confirmPasteBtn'),
    closePasteModal: el('#closePasteModal'),
    cancelPasteBtn: el('#cancelPasteBtn'),
    learnResultModal: el('#learnResultModal'),
    learnOcrText: el('#learnOcrText'),
    learnStyleAnalysis: el('#learnStyleAnalysis'),
    closeLearnModal: el('#closeLearnModal'),
    closeLearnBtn: el('#closeLearnBtn'),
    // Voice
    voiceCallBtn: el('#voiceCallBtn'),
    voiceStatus: el('#voiceStatus'),
    voiceStatusText: el('#voiceStatusText'),
    voiceWave: el('.voice-wave'),
    voiceAudio: el('#voiceAudio'),
    endVoiceBtn: el('#endVoiceBtn'),
    inputContainer: el('#inputContainer'),
};

// ============================================================
// Initialization
// ============================================================
async function init() {
    await loadProfile();
    setupEventListeners();
    scrollToBottom();
}

async function loadProfile() {
    try {
        const resp = await fetch('/api/profile');
        const data = await resp.json();
        if (data.name) {
            state.aiName = data.name;
            dom.headerName.textContent = data.name;
            dom.aiNameInput.value = data.name;
        }
        if (data.style_analysis) {
            dom.styleProfileBox.textContent = data.style_analysis;
        }
        if (data.avatar_ai) {
            state.aiAvatar = '/static/uploads/avatars/' + data.avatar_ai;
            dom.aiAvatarImg.src = state.aiAvatar;
            dom.headerAvatarImg.src = state.aiAvatar;
            dom.typingAvatarImg.src = state.aiAvatar;
        }
        if (data.avatar_user) {
            state.userAvatar = '/static/uploads/avatars/' + data.avatar_user;
            dom.userAvatarImg.src = state.userAvatar;
        }
        if (data.screenshot_count > 0) {
            dom.learnStatus.textContent = '已从 ' + data.screenshot_count + ' 张截图学习';
            dom.learnStatus.className = 'learn-status success';
        }
    } catch (e) {
        console.error('加载配置失败：', e);
    }
}

// ============================================================
// Event Listeners
// ============================================================
function setupEventListeners() {
    dom.sendBtn.addEventListener('click', sendMessage);
    dom.messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    dom.messageInput.addEventListener('input', autoResizeTextarea);
    dom.sidebarToggle.addEventListener('click', toggleSidebar);
    dom.menuBtn.addEventListener('click', toggleSidebar);
    dom.aiAvatarInput.addEventListener('change', (e) => uploadAvatar(e, 'ai'));
    dom.userAvatarInput.addEventListener('change', (e) => uploadAvatar(e, 'user'));
    dom.removeAiAvatar.addEventListener('click', () => removeAvatar('ai'));
    dom.removeUserAvatar.addEventListener('click', () => removeAvatar('user'));
    dom.saveNameBtn.addEventListener('click', saveName);
    dom.screenshotInput.addEventListener('change', uploadScreenshot);
    dom.pasteTextBtn.addEventListener('click', openPasteModal);
    dom.closePasteModal.addEventListener('click', closePasteModal);
    dom.cancelPasteBtn.addEventListener('click', closePasteModal);
    dom.confirmPasteBtn.addEventListener('click', submitPasteText);
    dom.closeLearnModal.addEventListener('click', closeLearnModal);
    dom.closeLearnBtn.addEventListener('click', closeLearnModal);
    dom.resetBtn.addEventListener('click', resetAll);
    dom.clearChatBtn.addEventListener('click', clearChat);
    // Voice
    dom.voiceCallBtn.addEventListener('click', toggleVoiceCall);
    dom.endVoiceBtn.addEventListener('click', endVoiceCall);
    dom.voiceAudio.addEventListener('ended', onAudioPlaybackEnded);
}

// ============================================================
// Chat Functions
// ============================================================
async function sendMessage() {
    const message = dom.messageInput.value.trim();
    if (!message || state.isStreaming) return;

    // Clear input
    dom.messageInput.value = '';
    dom.messageInput.style.height = 'auto';
    dom.sendBtn.disabled = true;

    // Add user message
    addMessage('user', message);

    // Show typing indicator
    showTyping(true);
    state.isStreaming = true;

    try {
        // Use streaming API
        const resp = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });

        // Create AI message bubble
        const aiBubble = createMessageBubble('ai', '');
        dom.chatMessages.appendChild(aiBubble);

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.error) {
                            aiBubble.querySelector('.message-bubble').textContent = '错误：' + data.error;
                        } else if (!data.done) {
                            aiBubble.querySelector('.message-bubble').textContent += data.content;
                            scrollToBottom();
                        }
                        if (data.name) {
                            state.aiName = data.name;
                            dom.headerName.textContent = data.name;
                        }
                    } catch (e) {
                        // Skip invalid JSON
                    }
                }
            }
        }

        scrollToBottom();
    } catch (e) {
        addMessage('ai', '抱歉，连接错误：' + e.message);
    } finally {
        showTyping(false);
        state.isStreaming = false;
        dom.sendBtn.disabled = false;
        dom.messageInput.focus();
    }
}

function addMessage(role, content) {
    const row = createMessageBubble(role, content);
    dom.chatMessages.appendChild(row);
    scrollToBottom();
}

function createMessageBubble(role, content) {
    const row = document.createElement('div');
    row.className = 'message-row ' + role;

    // Avatar
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    const avatarImg = document.createElement('img');
    if (role === 'ai') {
        avatarImg.src = state.aiAvatar || '';
        avatarImg.alt = state.aiName;
    } else {
        avatarImg.src = state.userAvatar || '';
        avatarImg.alt = '我';
    }
    avatarImg.onerror = function() {
        this.style.display = 'none';
    };
    avatarDiv.appendChild(avatarImg);

    // Bubble
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = content;

    // Time
    const time = document.createElement('div');
    time.className = 'message-time';
    const now = new Date();
    time.textContent = now.getHours().toString().padStart(2, '0') + ':' +
                       now.getMinutes().toString().padStart(2, '0');

    row.appendChild(avatarDiv);
    row.appendChild(bubble);
    row.appendChild(time);

    // Remove welcome message
    const welcome = dom.chatMessages.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    return row;
}

function showTyping(show) {
    dom.typingIndicator.style.display = show ? 'flex' : 'none';
    if (show) scrollToBottom();
}

function scrollToBottom() {
    dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

function autoResizeTextarea() {
    dom.messageInput.style.height = 'auto';
    dom.messageInput.style.height = Math.min(dom.messageInput.scrollHeight, 120) + 'px';
}

// ============================================================
// Sidebar
// ============================================================
function toggleSidebar() {
    state.sidebarOpen = !state.sidebarOpen;
    if (state.sidebarOpen) {
        dom.sidebar.classList.remove('closed');
    } else {
        dom.sidebar.classList.add('closed');
    }
}

// ============================================================
// Avatar Functions
// ============================================================
async function uploadAvatar(event, type) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('type', type);

    try {
        const resp = await fetch('/api/upload-avatar', {
            method: 'POST',
            body: formData
        });
        const data = await resp.json();

        if (data.success) {
            const avatarUrl = data.avatar_url;
            if (type === 'ai') {
                state.aiAvatar = avatarUrl;
                dom.aiAvatarImg.src = avatarUrl;
                dom.headerAvatarImg.src = avatarUrl;
                dom.typingAvatarImg.src = avatarUrl;
            } else {
                state.userAvatar = avatarUrl;
                dom.userAvatarImg.src = avatarUrl;
            }
        } else {
            alert('上传失败：' + (data.error || '未知错误'));
        }
    } catch (e) {
        alert('上传错误：' + e.message);
    }
}

async function removeAvatar(type) {
    try {
        await fetch('/api/remove-avatar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: type })
        });
        if (type === 'ai') {
            state.aiAvatar = '/static/uploads/avatars/default_ai.png';
            dom.aiAvatarImg.src = state.aiAvatar;
            dom.headerAvatarImg.src = state.aiAvatar;
            dom.typingAvatarImg.src = state.aiAvatar;
        } else {
            state.userAvatar = '/static/uploads/avatars/default_user.png';
            dom.userAvatarImg.src = state.userAvatar;
        }
    } catch (e) {
        alert('移除失败：' + e.message);
    }
}

// ============================================================
// Name
// ============================================================
async function saveName() {
    const name = dom.aiNameInput.value.trim();
    if (!name) return;

    try {
        await fetch('/api/profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        });
        state.aiName = name;
        dom.headerName.textContent = name;
    } catch (e) {
        alert('保存失败：' + e.message);
    }
}

// ============================================================
// Learning Functions
// ============================================================
async function uploadScreenshot(event) {
    const file = event.target.files[0];
    if (!file) return;

    dom.learnStatus.textContent = '正在分析截图...';
    dom.learnStatus.className = 'learn-status loading';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch('/api/upload-screenshot', {
            method: 'POST',
            body: formData
        });
        const data = await resp.json();

        if (data.success) {
            dom.learnStatus.textContent = '风格学习完成！';
            dom.learnStatus.className = 'learn-status success';
            dom.styleProfileBox.textContent = data.style_analysis;

            // Show result modal
            dom.learnOcrText.textContent = data.ocr_text;
            dom.learnStyleAnalysis.textContent = data.style_analysis;
            dom.learnResultModal.style.display = 'flex';
        } else {
            dom.learnStatus.textContent = '失败：' + (data.error || '未知错误');
            dom.learnStatus.className = 'learn-status error';
        }
    } catch (e) {
        dom.learnStatus.textContent = '错误：' + e.message;
        dom.learnStatus.className = 'learn-status error';
    }

    // Reset file input
    event.target.value = '';
}

function openPasteModal() {
    dom.pasteModal.style.display = 'flex';
    dom.pasteTextArea.focus();
}

function closePasteModal() {
    dom.pasteModal.style.display = 'none';
    dom.pasteTextArea.value = '';
}

async function submitPasteText() {
    const text = dom.pasteTextArea.value.trim();
    if (!text) {
        alert('请先粘贴聊天文本！');
        return;
    }

    dom.learnStatus.textContent = '正在分析文本...';
    dom.learnStatus.className = 'learn-status loading';
    closePasteModal();

    try {
        const resp = await fetch('/api/upload-raw-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });
        const data = await resp.json();

        if (data.success) {
            dom.learnStatus.textContent = '风格学习完成！';
            dom.learnStatus.className = 'learn-status success';
            dom.styleProfileBox.textContent = data.style_analysis;

            // Show result modal
            dom.learnOcrText.textContent = text;
            dom.learnStyleAnalysis.textContent = data.style_analysis;
            dom.learnResultModal.style.display = 'flex';
        } else {
            dom.learnStatus.textContent = '失败：' + (data.error || '未知错误');
            dom.learnStatus.className = 'learn-status error';
        }
    } catch (e) {
        dom.learnStatus.textContent = '错误：' + e.message;
        dom.learnStatus.className = 'learn-status error';
    }
}

function closeLearnModal() {
    dom.learnResultModal.style.display = 'none';
}

// ============================================================
// Reset & Clear
// ============================================================
async function resetAll() {
    if (!confirm('确定要重置全部数据吗？\n这将清除所有数据、聊天记录和头像。')) return;

    try {
        await fetch('/api/reset', { method: 'POST' });
        dom.chatMessages.innerHTML = '<div class="welcome-message"><div class="welcome-icon">💕</div><h3>赛博女友</h3><p>你的 AI 伴侣，由 Ollama 驱动</p><p class="welcome-hint">开始聊天，或上传聊天截图让她学习你的说话风格！</p></div>';
        dom.styleProfileBox.innerHTML = '<span class="text-muted">暂无风格数据...</span>';
        dom.learnStatus.textContent = '';
        dom.learnStatus.className = 'learn-status';
        state.aiName = '小赛';
        state.aiAvatar = '/static/uploads/avatars/default_ai.png';
        state.userAvatar = '/static/uploads/avatars/default_user.png';
        dom.headerName.textContent = '小赛';
        dom.aiNameInput.value = '小赛';
        dom.aiAvatarImg.src = state.aiAvatar;
        dom.userAvatarImg.src = state.userAvatar;
        dom.headerAvatarImg.src = state.aiAvatar;
        dom.typingAvatarImg.src = state.aiAvatar;
        await loadProfile();
    } catch (e) {
        alert('重置失败：' + e.message);
    }
}

async function clearChat() {
    try {
        await fetch('/api/chat-history', { method: 'DELETE' });
        dom.chatMessages.innerHTML = '<div class="welcome-message"><div class="welcome-icon">💕</div><h3>赛博女友</h3><p>你的 AI 伴侣，由 Ollama 驱动</p><p class="welcome-hint">开始聊天，或上传聊天截图让她学习你的说话风格！</p></div>';
    } catch (e) {
        alert('清空失败：' + e.message);
    }
}

// ============================================================
// Voice Call Functions
// ============================================================

/**
 * 切换语音通话模式
 */
async function toggleVoiceCall() {
    if (state.voiceActive) {
        endVoiceCall();
        return;
    }

    // 请求麦克风权限
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        state.audioStream = stream;
        startVoiceCall();
    } catch (e) {
        if (e.name === 'NotAllowedError') {
            alert('需要麦克风权限才能使用语音通话功能，请在浏览器设置中允许麦克风访问。');
        } else if (e.name === 'NotFoundError') {
            alert('未检测到麦克风设备，请检查麦克风连接。');
        } else {
            alert('无法访问麦克风：' + e.message);
        }
    }
}

/**
 * 开始语音通话
 */
function startVoiceCall() {
    state.voiceActive = true;
    dom.voiceCallBtn.classList.add('active');
    dom.voiceStatus.style.display = 'flex';
    dom.inputContainer.style.opacity = '0.5';
    dom.messageInput.disabled = true;
    dom.sendBtn.disabled = true;

    updateVoiceStatus('listening', '正在听...');
    startListening();
}

/**
 * 结束语音通话
 */
function endVoiceCall() {
    state.voiceActive = false;
    stopListening();

    // 停止所有音频
    if (state.audioStream) {
        state.audioStream.getTracks().forEach(t => t.stop());
        state.audioStream = null;
    }
    dom.voiceAudio.pause();
    dom.voiceAudio.src = '';

    // 恢复 UI
    dom.voiceCallBtn.classList.remove('active', 'listening');
    dom.voiceStatus.style.display = 'none';
    dom.inputContainer.style.opacity = '1';
    dom.messageInput.disabled = false;
    dom.sendBtn.disabled = false;
    dom.messageInput.focus();
    dom.voiceWave.classList.remove('speaking');
}

/**
 * 开始录音
 */
function startListening() {
    if (!state.audioStream) return;

    state.voiceListening = true;
    state.audioChunks = [];

    // 检测支持的 MIME 类型
    let mimeType = 'audio/webm';
    if (!MediaRecorder.isTypeSupported('audio/webm')) {
        mimeType = 'audio/mp4';
        if (!MediaRecorder.isTypeSupported('audio/mp4')) {
            mimeType = 'audio/ogg';
            if (!MediaRecorder.isTypeSupported('audio/ogg')) {
                mimeType = '';
            }
        }
    }

    const options = mimeType ? { mimeType } : {};
    state.mediaRecorder = new MediaRecorder(state.audioStream, options);

    state.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
            state.audioChunks.push(event.data);
        }
    };

    state.mediaRecorder.onstop = async () => {
        if (!state.voiceActive) return;

        const audioBlob = new Blob(state.audioChunks, { type: mimeType || 'audio/webm' });

        // 转换为 WAV 格式
        try {
            const wavBlob = await convertToWav(audioBlob);
            await processVoiceInput(wavBlob);
        } catch (e) {
            console.error('音频转换失败：', e);
            // 如果转换失败，尝试直接发送原始格式
            await processVoiceInput(audioBlob);
        }
    };

    state.mediaRecorder.start();
    dom.voiceCallBtn.classList.add('listening');

    // 设置自动停止：检测静音 2 秒后自动停止
    startSilenceDetection();
}

/**
 * 停止录音
 */
function stopListening() {
    state.voiceListening = false;
    stopSilenceDetection();

    if (state.mediaRecorder && state.mediaRecorder.state === 'recording') {
        state.mediaRecorder.stop();
    }
    dom.voiceCallBtn.classList.remove('listening');
}

/**
 * 静音检测（基于音量）
 */
let _silenceTimer = null;
let _audioAnalyser = null;
let _analyserInterval = null;

function startSilenceDetection() {
    if (!state.audioStream) return;

    try {
        state.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = state.audioContext.createMediaStreamSource(state.audioStream);
        _audioAnalyser = state.audioContext.createAnalyser();
        _audioAnalyser.fftSize = 256;
        source.connect(_audioAnalyser);

        const bufferLength = _audioAnalyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        // 检测静音：如果音量持续低于阈值，自动停止录音
        const SILENCE_THRESHOLD = 25;
        const SILENCE_DURATION = 2000; // 2秒静音后自动发送

        _analyserInterval = setInterval(() => {
            if (!state.voiceListening) return;

            _audioAnalyser.getByteFrequencyData(dataArray);
            let sum = 0;
            for (let i = 0; i < bufferLength; i++) {
                sum += dataArray[i];
            }
            const avgVolume = sum / bufferLength;

            if (avgVolume < SILENCE_THRESHOLD) {
                if (!_silenceTimer) {
                    _silenceTimer = setTimeout(() => {
                        if (state.voiceListening && state.mediaRecorder.state === 'recording') {
                            console.log('[Voice] 检测到静音，自动停止录音');
                            stopListening();
                        }
                    }, SILENCE_DURATION);
                }
            } else {
                if (_silenceTimer) {
                    clearTimeout(_silenceTimer);
                    _silenceTimer = null;
                }
            }
        }, 200);
    } catch (e) {
        console.log('[Voice] 静音检测不可用：', e.message);
        // 不支持时，每 6 秒自动停止一次
        _silenceTimer = setTimeout(() => {
            if (state.voiceListening && state.mediaRecorder && state.mediaRecorder.state === 'recording') {
                stopListening();
            }
        }, 6000);
    }
}

function stopSilenceDetection() {
    if (_silenceTimer) {
        clearTimeout(_silenceTimer);
        _silenceTimer = null;
    }
    if (_analyserInterval) {
        clearInterval(_analyserInterval);
        _analyserInterval = null;
    }
    if (state.audioContext && state.audioContext.state !== 'closed') {
        state.audioContext.close().catch(() => {});
        state.audioContext = null;
    }
    _audioAnalyser = null;
}

/**
 * 将浏览器录音 Blob 转换为 WAV 格式
 */
async function convertToWav(audioBlob) {
    // 使用 AudioContext 解码并重新编码为 WAV
    const arrayBuffer = await audioBlob.arrayBuffer();
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);

    // 提取单声道数据并重采样到 16kHz
    const targetSampleRate = 16000;
    const offlineCtx = new OfflineAudioContext(
        1,
        Math.ceil(audioBuffer.duration * targetSampleRate),
        targetSampleRate
    );
    const source = offlineCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(offlineCtx.destination);
    source.start(0);

    const renderedBuffer = await offlineCtx.startRendering();
    const pcmData = renderedBuffer.getChannelData(0);

    // 编码为 WAV
    const wavBuffer = encodeWav(pcmData, targetSampleRate);
    audioCtx.close();
    return new Blob([wavBuffer], { type: 'audio/wav' });
}

/**
 * 将 PCM 数据编码为 WAV 格式
 */
function encodeWav(samples, sampleRate) {
    const numChannels = 1;
    const bitsPerSample = 16;
    const byteRate = sampleRate * numChannels * bitsPerSample / 8;
    const blockAlign = numChannels * bitsPerSample / 8;
    const dataSize = samples.length * blockAlign;
    const bufferSize = 44 + dataSize;

    const buffer = new ArrayBuffer(bufferSize);
    const view = new DataView(buffer);

    // RIFF header
    writeString(view, 0, 'RIFF');
    view.setUint32(4, bufferSize - 8, true);
    writeString(view, 8, 'WAVE');

    // fmt chunk
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);

    // data chunk
    writeString(view, 36, 'data');
    view.setUint32(40, dataSize, true);

    // Write samples
    let offset = 44;
    for (let i = 0; i < samples.length; i++) {
        const s = Math.max(-1, Math.min(1, samples[i]));
        const intSample = s < 0 ? s * 0x8000 : s * 0x7FFF;
        view.setInt16(offset, intSample, true);
        offset += 2;
    }

    return buffer;
}

function writeString(view, offset, str) {
    for (let i = 0; i < str.length; i++) {
        view.setUint8(offset + i, str.charCodeAt(i));
    }
}

/**
 * 处理语音输入：SSE 流式连接 /api/voice/chat-stream
 *
 * 新流程（低延迟）：
 *   上传音频 → ASR（<100ms）
 *   → LLM 流式输出 → 分句切割 → 逐句 TTS 合成
 *   → SSE 实时推送 {text + audio}，前端边收边播
 *
 * 首句延迟目标：~2s（vs 旧流程 8s+）
 */
async function processVoiceInput(audioBlob) {
    if (!state.voiceActive) return;

    updateVoiceStatus('processing', '识别中...');

    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.wav');
    formData.append('language', 'zh');

    // ---- 音频播放队列 ----
    const audioQueue = [];
    let isPlayingAudio = false;

    function playNextAudio() {
        if (audioQueue.length === 0) {
            isPlayingAudio = false;
            dom.voiceWave.classList.remove('speaking');
            dom.voiceStatusText.classList.remove('speaking');

            // 队列播完且 SSE 已结束 → 恢复监听
            if (state.voiceActive && _streamEnded) {
                updateVoiceStatus('listening', '正在听...');
                startListening();
            }
            return;
        }

        isPlayingAudio = true;
        dom.voiceWave.classList.add('speaking');
        dom.voiceStatusText.classList.add('speaking');
        updateVoiceStatus('speaking', '正在说...');

        const item = audioQueue.shift();
        const audioUrl = URL.createObjectURL(item.blob);

        dom.voiceAudio.src = audioUrl;
        dom.voiceAudio.onended = () => {
            URL.revokeObjectURL(audioUrl);
            playNextAudio();
        };
        dom.voiceAudio.onerror = () => {
            URL.revokeObjectURL(audioUrl);
            playNextAudio();
        };
        dom.voiceAudio.play().catch(() => {
            URL.revokeObjectURL(audioUrl);
            playNextAudio();
        });
    }

    // ---- SSE 流式读取 ----
    let aiBubble = null;
    let aiFullText = '';
    let userText = '';
    let _streamEnded = false;

    try {
        const resp = await fetch('/api/voice/chat-stream', {
            method: 'POST',
            body: formData,
        });

        if (!resp.ok) {
            let errMsg = '服务器错误';
            try {
                const errData = await resp.json();
                errMsg = errData.error || errMsg;
            } catch (_) { /* ignore */ }
            updateVoiceStatus('listening', '出错：' + errMsg);
            setTimeout(() => { if (state.voiceActive) startListening(); }, 2000);
            return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                let data = null;
                try {
                    data = JSON.parse(line.slice(6));
                } catch (_) { continue; }

                switch (data.type) {
                    case 'user':
                        // ASR 识别结果
                        userText = data.text || '';
                        if (userText) {
                            addMessage('user', userText);
                        }
                        updateVoiceStatus('processing', '思考中...');
                        break;

                    case 'sentence':
                        // AI 分句文本 + 可选音频
                        if (data.text) {
                            aiFullText += data.text;

                            if (!aiBubble) {
                                aiBubble = createMessageBubble('ai', '');
                                dom.chatMessages.appendChild(aiBubble);
                            }
                            aiBubble.querySelector('.message-bubble').textContent = aiFullText;
                            scrollToBottom();
                        }

                        if (data.audio) {
                            const audioBlob = base64ToBlob(data.audio, 'audio/wav');
                            audioQueue.push({ blob: audioBlob });
                            if (!isPlayingAudio) {
                                playNextAudio();
                            }
                        }
                        break;

                    case 'error':
                        console.error('[Voice] 流式错误：', data.error);
                        break;

                    case 'done':
                        _streamEnded = true;
                        if (data.name) state.aiName = data.name;
                        // 如果无音频且无文本，快速恢复监听
                        if (!isPlayingAudio && audioQueue.length === 0) {
                            if (state.voiceActive) {
                                updateVoiceStatus('listening', '正在听...');
                                startListening();
                            }
                        }
                        // 否则等待 playNextAudio 自然触发恢复
                        break;
                }
            }
        }

        // SSE 连接关闭但 done 可能未收到（网络波动）
        if (!_streamEnded) {
            _streamEnded = true;
            if (!isPlayingAudio && audioQueue.length === 0) {
                if (state.voiceActive) {
                    updateVoiceStatus('listening', '正在听...');
                    startListening();
                }
            }
        }

    } catch (e) {
        console.error('[Voice] SSE 连接失败：', e);
        _streamEnded = true;
        if (aiFullText && !aiBubble) {
            addMessage('ai', aiFullText);
        }
        if (!isPlayingAudio && audioQueue.length === 0) {
            updateVoiceStatus('listening', '连接中断');
            setTimeout(() => { if (state.voiceActive) startListening(); }, 2000);
        }
    }
}

/**
 * 音频播放结束回调
 */
function onAudioPlaybackEnded() {
    state.voiceSpeaking = false;
    dom.voiceWave.classList.remove('speaking');
    dom.voiceStatusText.classList.remove('speaking');

    // 清理 audio URL
    if (dom.voiceAudio.src) {
        URL.revokeObjectURL(dom.voiceAudio.src);
        dom.voiceAudio.src = '';
    }

    if (state.voiceActive) {
        updateVoiceStatus('listening', '正在听...');
        startListening();
    }
}

/**
 * 更新语音状态 UI
 */
function updateVoiceStatus(state_type, text) {
    dom.voiceStatusText.textContent = text;

    if (state_type === 'listening') {
        dom.voiceStatusText.className = 'voice-text';
        dom.voiceWave.classList.remove('speaking');
    } else if (state_type === 'speaking') {
        dom.voiceStatusText.className = 'voice-text speaking';
        dom.voiceWave.classList.add('speaking');
    } else if (state_type === 'processing') {
        dom.voiceStatusText.className = 'voice-text';
        dom.voiceWave.classList.remove('speaking');
    }
}

/**
 * Base64 转 Blob
 */
function base64ToBlob(base64, mimeType) {
    const byteChars = atob(base64);
    const byteArrays = [];
    for (let offset = 0; offset < byteChars.length; offset += 512) {
        const slice = byteChars.slice(offset, offset + 512);
        const byteNumbers = new Array(slice.length);
        for (let i = 0; i < slice.length; i++) {
            byteNumbers[i] = slice.charCodeAt(i);
        }
        byteArrays.push(new Uint8Array(byteNumbers));
    }
    return new Blob(byteArrays, { type: mimeType });
}

// ============================================================
// Startup
// ============================================================
document.addEventListener('DOMContentLoaded', init);

// ============================================================
// Cyber GF v2.0 — WebSocket 实时语音 + 设置面板
// ============================================================

// State
const state = {
    aiName: '小赛',
    aiAvatar: '/static/uploads/avatars/default_ai.png',
    userAvatar: '/static/uploads/avatars/default_user.png',
    isStreaming: false,
    settingsOpen: false,
    // Voice state
    voiceActive: false,
    voiceListening: false,
    voiceSpeaking: false,
    mediaRecorder: null,
    audioChunks: [],
    audioContext: null,
    // WebSocket
    ws: null,
    wsConnected: false,
    // Audio queue
    audioQueue: [],
    isPlayingAudio: false,
    currentAudio: null,
    interruptRequested: false,
    // Call UI
    callMinimized: false,
    callMuted: false,
    callStartTime: null,
    callTimerInterval: null,
};

// DOM Elements
const el = (sel) => document.querySelector(sel);

const dom = {
    // Chat
    chatMessages: el('#chatMessages'),
    messageInput: el('#messageInput'),
    sendBtn: el('#sendBtn'),
    typingIndicator: el('#typingIndicator'),
    typingAvatarImg: el('#typingAvatarImg'),
    headerName: el('#headerName'),
    headerAvatarImg: el('#headerAvatarImg'),
    // Settings
    settingsBtn: el('#settingsBtn'),
    settingsOverlay: el('#settingsOverlay'),
    settingsPanel: el('#settingsPanel'),
    settingsClose: el('#settingsClose'),
    settingsTabs: el('#settingsTabs'),
    // Avatar
    aiAvatarImg: el('#aiAvatarImg'),
    aiAvatarInput: el('#aiAvatarInput'),
    userAvatarImg: el('#userAvatarImg'),
    userAvatarInput: el('#userAvatarInput'),
    removeAiAvatar: el('#removeAiAvatar'),
    removeUserAvatar: el('#removeUserAvatar'),
    // Name & Style
    aiNameInput: el('#aiNameInput'),
    saveNameBtn: el('#saveNameBtn'),
    screenshotInput: el('#screenshotInput'),
    submitPasteBtn: el('#submitPasteBtn'),
    pasteTextArea: el('#pasteTextArea'),
    learnStatus: el('#learnStatus'),
    styleProfileBox: el('#styleProfileBox'),
    resetBtn: el('#resetBtn'),
    clearChatBtn: el('#clearChatBtn'),
    // Modal
    learnResultModal: el('#learnResultModal'),
    learnOcrText: el('#learnOcrText'),
    learnStyleAnalysis: el('#learnStyleAnalysis'),
    closeLearnModal: el('#closeLearnModal'),
    closeLearnBtn: el('#closeLearnBtn'),
    // Voice
    voiceCallBtn: el('#voiceCallBtn'),
    voiceStatus: el('#voiceStatus'),
    voiceStatusText: el('#voiceStatusText'),
    voiceWaveBar: el('#voiceWaveBar'),
    voiceAudio: el('#voiceAudio'),
    endVoiceBtn: el('#endVoiceBtn'),
    interruptBtn: el('#interruptBtn'),
    inputContainer: el('#inputContainer'),
    // Model Config
    cfgOllamaUrl: el('#cfgOllamaUrl'),
    cfgModelName: el('#cfgModelName'),
    cfgTtsProvider: el('#cfgTtsProvider'),
    cfgCosyvoiceKey: el('#cfgCosyvoiceKey'),
    cfgCosyvoiceVoice: el('#cfgCosyvoiceVoice'),
    ttsVoiceGrid: el('#ttsVoiceGrid'),
    cfgAsrEngine: el('#cfgAsrEngine'),
    saveSettingsBtn: el('#saveSettingsBtn'),
    settingsSaveStatus: el('#settingsSaveStatus'),
    cosyvoiceConfig: el('#cosyvoiceConfig'),
    testApiBtn: el('#testApiBtn'),
    apiTestStatus: el('#apiTestStatus'),
    // Voice Call UI
    callOverlay: el('#callOverlay'),
    callMinimizeBtn: el('#callMinimizeBtn'),
    callTimer: el('#callTimer'),
    callAvatarImg: el('#callAvatarImg'),
    callAvatarRing: el('#callAvatarRing'),
    callName: el('#callName'),
    callStatusLabel: el('#callStatusLabel'),
    callUserText: el('#callUserText'),
    callInterruptBtn: el('#callInterruptBtn'),
    callEndBtn: el('#callEndBtn'),
    callMuteBtn: el('#callMuteBtn'),
    callFloatBadge: el('#callFloatBadge'),
    callFloatTimer: el('#callFloatTimer'),
    callFloatEndBtn: el('#callFloatEndBtn'),
    callFloatAvatarImg: el('#callFloatAvatarImg'),
};

// ============================================================
// Initialization
// ============================================================
async function init() {
    await loadAllSettings();
    setupEventListeners();
    scrollToBottom();
}

async function loadAllSettings() {
    try {
        const resp = await fetch('/api/settings');
        const data = await resp.json();
        if (!data.success) return;

        // Profile
        const p = data.profile;
        if (p.name) {
            state.aiName = p.name;
            dom.headerName.textContent = p.name;
            dom.aiNameInput.value = p.name;
        }
        if (p.style_analysis) {
            dom.styleProfileBox.textContent = p.style_analysis;
        }
        if (p.avatar_ai) {
            state.aiAvatar = '/static/uploads/avatars/' + p.avatar_ai;
            dom.aiAvatarImg.src = state.aiAvatar;
            dom.headerAvatarImg.src = state.aiAvatar;
            dom.typingAvatarImg.src = state.aiAvatar;
        }
        if (p.avatar_user) {
            state.userAvatar = '/static/uploads/avatars/' + p.avatar_user;
            dom.userAvatarImg.src = state.userAvatar;
        }
        if (p.screenshot_count > 0) {
            dom.learnStatus.textContent = '已从 ' + p.screenshot_count + ' 次学习';
            dom.learnStatus.className = 'learn-status success';
        }

        // Model Settings
        const s = data.settings;
        if (s.ollama_url) dom.cfgOllamaUrl.value = s.ollama_url;
        if (s.model_name) {
            // 尝试匹配 select option，找不到则保留现有选择
            const opt = dom.cfgModelName.querySelector(`option[value="${s.model_name}"]`);
            if (opt) dom.cfgModelName.value = s.model_name;
        }
        if (s.tts_provider) dom.cfgTtsProvider.value = s.tts_provider;
        if (s.cosyvoice_api_key) dom.cfgCosyvoiceKey.value = s.cosyvoice_api_key;
        if (s.cosyvoice_voice) {
            dom.cfgCosyvoiceVoice.value = s.cosyvoice_voice;
            // 恢复语音卡片选中状态
            dom.ttsVoiceGrid.querySelectorAll('.tts-voice-card').forEach(c => {
                c.classList.toggle('selected', c.dataset.voice === s.cosyvoice_voice);
            });
        }

        updateTtsProviderUI();
    } catch (e) {
        console.error('加载设置失败：', e);
    }
}

function updateTtsProviderUI() {
    const provider = dom.cfgTtsProvider.value;
    dom.cosyvoiceConfig.style.display = provider === 'cosyvoice' ? 'block' : 'none';
}

// ============================================================
// Event Listeners
// ============================================================
function setupEventListeners() {
    // Chat
    dom.sendBtn.addEventListener('click', sendMessage);
    dom.messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    dom.messageInput.addEventListener('input', autoResizeTextarea);

    // Settings panel
    dom.settingsBtn.addEventListener('click', openSettings);
    dom.settingsClose.addEventListener('click', closeSettings);
    dom.settingsOverlay.addEventListener('click', (e) => {
        // 只有点击遮罩背景时才关闭，点击面板内部不关闭
        if (e.target === dom.settingsOverlay) closeSettings();
    });
    // 阻止面板内部点击冒泡到 overlay
    dom.settingsPanel.addEventListener('click', (e) => e.stopPropagation());
    dom.settingsTabs.addEventListener('click', (e) => {
        if (e.target.classList.contains('settings-tab')) {
            switchSettingsTab(e.target.dataset.tab);
        }
    });
    dom.cfgTtsProvider.addEventListener('change', updateTtsProviderUI);
    dom.saveSettingsBtn.addEventListener('click', saveModelSettings);

    // TTS voice card selection + preview
    dom.ttsVoiceGrid.addEventListener('click', (e) => {
        const card = e.target.closest('.tts-voice-card');
        if (!card) return;
        // 预览按钮
        if (e.target.closest('.voice-preview-btn')) {
            previewVoice(card.dataset.voice, e.target.closest('.voice-preview-btn'));
            return;
        }
        // 选择卡片
        dom.ttsVoiceGrid.querySelectorAll('.tts-voice-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        dom.cfgCosyvoiceVoice.value = card.dataset.voice;
    });

    // API 测试按钮
    dom.testApiBtn.addEventListener('click', testApiConnection);

    // 语音通话 UI
    dom.callMinimizeBtn.addEventListener('click', minimizeCall);
    dom.callEndBtn.addEventListener('click', endVoiceCall);
    dom.callFloatEndBtn.addEventListener('click', endVoiceCall);
    dom.callFloatBadge.addEventListener('click', restoreCall);
    dom.callInterruptBtn.addEventListener('click', interruptVoice);
    dom.callMuteBtn.addEventListener('click', toggleMute);

    // Avatar
    dom.aiAvatarInput.addEventListener('change', (e) => uploadAvatar(e, 'ai'));
    dom.userAvatarInput.addEventListener('change', (e) => uploadAvatar(e, 'user'));
    dom.removeAiAvatar.addEventListener('click', () => removeAvatar('ai'));
    dom.removeUserAvatar.addEventListener('click', () => removeAvatar('user'));

    // Name
    dom.saveNameBtn.addEventListener('click', saveName);

    // Learning
    dom.screenshotInput.addEventListener('change', uploadScreenshot);
    dom.submitPasteBtn.addEventListener('click', submitPasteText);

    // Modal
    dom.closeLearnModal.addEventListener('click', closeLearnModal);
    dom.closeLearnBtn.addEventListener('click', closeLearnModal);

    // Reset & Clear
    dom.resetBtn.addEventListener('click', resetAll);
    dom.clearChatBtn.addEventListener('click', clearChat);

    // Voice — WebSocket based
    dom.voiceCallBtn.addEventListener('click', toggleVoiceCall);
    dom.endVoiceBtn.addEventListener('click', endVoiceCall);
    dom.interruptBtn.addEventListener('click', interruptVoice);
    dom.voiceAudio.addEventListener('ended', onAudioPlaybackEnded);

    // Keyboard: Esc to close settings
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && state.settingsOpen) {
            closeSettings();
        }
    });
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
// Settings Panel
// ============================================================
function openSettings() {
    if (state.settingsOpen) return;
    state.settingsOpen = true;
    dom.settingsOverlay.style.display = 'flex';
    dom.settingsPanel.classList.remove('closing');
    dom.settingsOverlay.classList.remove('closing');
    loadAllSettings();
    document.body.style.overflow = 'hidden';
}

function closeSettings() {
    if (!state.settingsOpen) return;
    state.settingsOpen = false;
    dom.settingsPanel.classList.add('closing');
    dom.settingsOverlay.classList.add('closing');
    setTimeout(() => {
        dom.settingsOverlay.style.display = 'none';
        dom.settingsPanel.classList.remove('closing');
        dom.settingsOverlay.classList.remove('closing');
        document.body.style.overflow = '';
    }, 220);
}

function switchSettingsTab(tabId) {
    // Update tab buttons
    dom.settingsTabs.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
    dom.settingsTabs.querySelector(`[data-tab="${tabId}"]`).classList.add('active');
    // Update content
    document.querySelectorAll('.settings-tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
}

async function saveModelSettings() {
    const payload = {
        ollama_url: dom.cfgOllamaUrl.value.trim(),
        model_name: dom.cfgModelName.value.trim(),
        tts_provider: dom.cfgTtsProvider.value,
        cosyvoice_api_key: dom.cfgCosyvoiceKey.value.trim(),
        cosyvoice_voice: dom.cfgCosyvoiceVoice.value,
    };

    dom.settingsSaveStatus.textContent = '保存中...';
    dom.settingsSaveStatus.className = 'settings-save-status';

    try {
        const resp = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (data.success) {
            dom.settingsSaveStatus.textContent = '✓ 设置已保存';
            dom.settingsSaveStatus.className = 'settings-save-status success';
            setTimeout(() => {
                dom.settingsSaveStatus.textContent = '';
                dom.settingsSaveStatus.className = 'settings-save-status';
            }, 3000);
        } else {
            dom.settingsSaveStatus.textContent = '保存失败：' + (data.error || '未知错误');
            dom.settingsSaveStatus.className = 'settings-save-status error';
        }
    } catch (e) {
        dom.settingsSaveStatus.textContent = '保存错误：' + e.message;
        dom.settingsSaveStatus.className = 'settings-save-status error';
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

async function submitPasteText() {
    const text = dom.pasteTextArea.value.trim();
    if (!text) {
        alert('请先粘贴聊天文本！');
        return;
    }

    dom.learnStatus.textContent = '正在分析文本...';
    dom.learnStatus.className = 'learn-status loading';

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

            dom.learnOcrText.textContent = text;
            dom.learnStyleAnalysis.textContent = data.style_analysis;
            dom.learnResultModal.style.display = 'flex';
            dom.pasteTextArea.value = '';
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
        dom.chatMessages.innerHTML = '<div class="welcome-message"><div class="welcome-icon">💕</div><h3>痞老板的凯伦</h3><p>质疑痞老板，理解痞老板，成为痞老板</p><p class="welcome-hint">开始聊天吧！点击右上角 📞 开始语音通话</p></div>';
        dom.styleProfileBox.innerHTML = '<span class="text-muted">暂无风格数据，上传聊天记录让 AI 学习你的风格...</span>';
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
        // Reset model config fields
        dom.cfgOllamaUrl.value = 'http://localhost:11434/api';
        dom.cfgModelName.value = 'qwen2.5:7b-instruct';
        dom.cfgTtsProvider.value = 'cosyvoice';
        dom.cfgCosyvoiceKey.value = '';
        dom.cfgCosyvoiceVoice.value = 'longxing_v3';
        dom.ttsVoiceGrid.querySelectorAll('.tts-voice-card').forEach(c => {
            c.classList.toggle('selected', c.dataset.voice === 'longxing_v3');
        });
        updateTtsProviderUI();
        await loadAllSettings();
    } catch (e) {
        alert('重置失败：' + e.message);
    }
}

async function clearChat() {
    try {
        await fetch('/api/chat-history', { method: 'DELETE' });
        dom.chatMessages.innerHTML = '<div class="welcome-message"><div class="welcome-icon">💕</div><h3>痞老板的凯伦</h3><p>质疑痞老板，理解痞老板，成为痞老板</p><p class="welcome-hint">开始聊天吧！点击右上角 📞 开始语音通话</p></div>';
    } catch (e) {
        alert('清空失败：' + e.message);
    }
}

// ============================================================
// API Test & Voice Preview
// ============================================================
async function testApiConnection() {
    const key = dom.cfgCosyvoiceKey.value.trim();
    if (!key) { dom.apiTestStatus.textContent = '请先输入 API Key'; dom.apiTestStatus.className = 'test-status error'; return; }

    dom.apiTestStatus.textContent = '测试中...';
    dom.apiTestStatus.className = 'test-status loading';

    try {
        const resp = await fetch('/api/voice/tts/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: '测试连接',
                provider: 'cosyvoice',
                api_key: key,
                voice: dom.cfgCosyvoiceVoice.value
            })
        });
        const data = await resp.json();
        if (data.success) {
            dom.apiTestStatus.textContent = '✓ 连接成功！点击下方「保存设置」以持久化';
            dom.apiTestStatus.className = 'test-status success';
        } else {
            dom.apiTestStatus.textContent = '✗ 失败：' + (data.error || '未知错误');
            dom.apiTestStatus.className = 'test-status error';
        }
    } catch (e) {
        dom.apiTestStatus.textContent = '✗ 请求失败：' + e.message;
        dom.apiTestStatus.className = 'test-status error';
    }
}

let _previewAudio = null;
async function previewVoice(voiceName, btnEl) {
    if (_previewAudio) { _previewAudio.pause(); _previewAudio = null; }
    const playing = document.querySelector('.voice-preview-btn.playing');
    if (playing) playing.classList.remove('playing');

    btnEl.classList.add('playing');
    try {
        const resp = await fetch('/api/voice/tts/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: '你好呀，我是你的AI伴侣，很高兴能陪你聊天~',
                provider: 'cosyvoice',
                api_key: dom.cfgCosyvoiceKey.value.trim(),
                voice: voiceName
            })
        });
        const data = await resp.json();
        if (data.success && data.audio) {
            const blob = base64ToBlob(data.audio, 'audio/wav');
            const url = URL.createObjectURL(blob);
            _previewAudio = new Audio(url);
            _previewAudio.onended = () => { btnEl.classList.remove('playing'); URL.revokeObjectURL(url); _previewAudio = null; };
            _previewAudio.play();
        } else {
            btnEl.classList.remove('playing');
            alert('试听失败：' + (data.error || '未知错误'));
        }
    } catch (e) {
        btnEl.classList.remove('playing');
        alert('试听失败：' + e.message);
    }
}

// ============================================================
// Call UI (Fullscreen / Minimized)
// ============================================================
function showCallUI() {
    state.callMinimized = false;
    dom.callOverlay.style.display = 'flex';
    dom.callFloatBadge.style.display = 'none';
    dom.callAvatarImg.src = state.aiAvatar;
    dom.callFloatAvatarImg.src = state.aiAvatar;
    dom.callName.textContent = state.aiName;
    dom.callUserText.textContent = '';
    startCallTimer();
}

function hideCallUI() {
    dom.callOverlay.style.display = 'none';
    dom.callFloatBadge.style.display = 'none';
    stopCallTimer();
}

function minimizeCall() {
    state.callMinimized = true;
    document.querySelector('.call-screen').style.display = 'none';
    dom.callFloatBadge.style.display = 'flex';
    dom.callFloatAvatarImg.src = state.aiAvatar;
    updateCallFloatTimer();
    // 显示内联语音状态栏 + 恢复文字输入
    dom.voiceStatus.style.display = 'flex';
    dom.inputContainer.style.opacity = '1';
    dom.messageInput.disabled = false;
    dom.sendBtn.disabled = false;
}

function restoreCall() {
    state.callMinimized = false;
    document.querySelector('.call-screen').style.display = 'flex';
    dom.callFloatBadge.style.display = 'none';
    dom.voiceStatus.style.display = 'none';
}

function toggleMute() {
    state.callMuted = !state.callMuted;
    if (state.audioStream) {
        state.audioStream.getAudioTracks().forEach(t => { t.enabled = !state.callMuted; });
    }
    // 切换图标：显示/隐藏斜杠
    const onIcon = dom.callMuteBtn.querySelector('.mute-icon-on');
    const offIcon = dom.callMuteBtn.querySelector('.mute-icon-off');
    if (state.callMuted) {
        onIcon.style.display = 'none';
        offIcon.style.display = 'block';
        dom.callMuteBtn.style.color = 'var(--danger)';
    } else {
        onIcon.style.display = 'block';
        offIcon.style.display = 'none';
        dom.callMuteBtn.style.color = 'var(--text-secondary)';
    }
}

function startCallTimer() {
    state.callStartTime = Date.now();
    state.callTimerInterval = setInterval(updateCallTimer, 1000);
    updateCallTimer();
}

function stopCallTimer() {
    if (state.callTimerInterval) { clearInterval(state.callTimerInterval); state.callTimerInterval = null; }
    state.callStartTime = null;
}

function updateCallTimer() {
    if (!state.callStartTime) return;
    const elapsed = Math.floor((Date.now() - state.callStartTime) / 1000);
    const m = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const s = (elapsed % 60).toString().padStart(2, '0');
    dom.callTimer.textContent = m + ':' + s;
    updateCallFloatTimer();
}

function updateCallFloatTimer() {
    if (!state.callStartTime) return;
    const elapsed = Math.floor((Date.now() - state.callStartTime) / 1000);
    const m = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const s = (elapsed % 60).toString().padStart(2, '0');
    dom.callFloatTimer.textContent = m + ':' + s;
}

function updateCallStatus(statusType, text) {
    dom.callStatusLabel.textContent = text;
    dom.callStatusLabel.className = 'call-status-text ' + statusType;
    // Also update inline status
    updateVoiceStatus(statusType, text);
}

// ============================================================
// Voice Call Functions (WebSocket 实时流式)
// ============================================================

/**
 * 切换语音通话模式
 */
async function toggleVoiceCall() {
    if (state.voiceActive) {
        endVoiceCall();
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                sampleRate: 16000,
                channelCount: 1,
            }
        });
        state.audioStream = stream;
        startVoiceCall();
    } catch (e) {
        if (e.name === 'NotAllowedError') {
            alert('需要麦克风权限才能使用语音通话功能。');
        } else if (e.name === 'NotFoundError') {
            alert('未检测到麦克风设备。');
        } else {
            alert('无法访问麦克风：' + e.message);
        }
    }
}

/**
 * 开始语音通话 — WebSocket 模式 + 全屏通话界面
 */
function startVoiceCall() {
    state.voiceActive = true;
    state.interruptRequested = false;
    state.callMuted = false;
    dom.voiceCallBtn.classList.add('active');

    // 显示全屏通话界面，隐藏内联状态栏
    dom.voiceStatus.style.display = 'none';
    showCallUI();

    // 连接 WebSocket
    connectVoiceWebSocket();

    updateCallStatus('listening', '正在听...');
    startListening();
}

/**
 * 结束语音通话
 */
function endVoiceCall() {
    state.voiceActive = false;
    stopListening();
    disconnectVoiceWebSocket();

    if (state.audioStream) {
        state.audioStream.getTracks().forEach(t => t.stop());
        state.audioStream = null;
    }
    stopAllAudio();

    // 隐藏通话界面
    hideCallUI();

    // 恢复聊天 UI
    dom.voiceCallBtn.classList.remove('active', 'listening');
    dom.voiceStatus.style.display = 'none';
    dom.interruptBtn.style.display = 'none';
    dom.inputContainer.style.opacity = '1';
    dom.messageInput.disabled = false;
    dom.sendBtn.disabled = false;
    dom.messageInput.focus();
    dom.voiceWaveBar.classList.remove('speaking');
}

// ============================================================
// WebSocket 语音连接管理
// ============================================================
function connectVoiceWebSocket() {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) return;

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws/voice`;

    console.log('[WS] 连接中...', wsUrl);
    state.ws = new WebSocket(wsUrl);
    state.wsConnected = false;

    state.ws.onopen = () => {
        console.log('[WS] 已连接');
        state.wsConnected = true;
    };

    state.ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleWsMessage(msg);
        } catch (e) {
            console.error('[WS] 消息解析失败:', e);
        }
    };

    state.ws.onclose = () => {
        console.log('[WS] 连接关闭');
        state.wsConnected = false;
        // 自动重连
        if (state.voiceActive && !state.interruptRequested) {
            setTimeout(() => {
                if (state.voiceActive) {
                    console.log('[WS] 尝试重连...');
                    connectVoiceWebSocket();
                }
            }, 2000);
        }
    };

    state.ws.onerror = (e) => {
        console.error('[WS] 连接错误:', e);
    };
}

function disconnectVoiceWebSocket() {
    if (state.ws) {
        state.ws.onclose = null; // 阻止自动重连
        state.ws.close();
        state.ws = null;
    }
    state.wsConnected = false;
}

function sendWsMessage(data) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(data));
    } else {
        console.warn('[WS] 未连接，无法发送消息');
    }
}

/**
 * 处理 WebSocket 消息
 */
let _wsAiBubble = null;
let _wsAiFullText = '';

function handleWsMessage(msg) {
    switch (msg.type) {
        case 'user_text':
            if (msg.text) {
                addMessage('user', msg.text);
                // Show in call subtitle
                dom.callUserText.textContent = msg.text;
                _wsAiBubble = null;
                _wsAiFullText = '';
            }
            updateCallStatus('processing', '思考中...');
            state.interruptRequested = false;
            break;

        case 'ai_text':
            if (msg.text) {
                _wsAiFullText += msg.text;
                if (!_wsAiBubble) {
                    _wsAiBubble = createMessageBubble('ai', '');
                    dom.chatMessages.appendChild(_wsAiBubble);
                }
                _wsAiBubble.querySelector('.message-bubble').textContent = _wsAiFullText;
                scrollToBottom();
            }
            break;

        case 'tts_audio':
            if (msg.data) {
                const audioBlob = base64ToBlob(msg.data, 'audio/wav');
                state.audioQueue.push({ blob: audioBlob });
                if (!state.isPlayingAudio) {
                    playNextInQueue();
                }
                updateCallStatus('speaking', '正在说...');
            }
            break;

        case 'interrupted':
            stopAllAudio();
            state.audioQueue = [];
            state.isPlayingAudio = false;
            _wsAiBubble = null;
            _wsAiFullText = '';
            updateCallStatus('listening', '正在听...');
            dom.callUserText.textContent = '';
            startListening();
            break;

        case 'done':
            if (msg.name) state.aiName = msg.name;
            if (!state.isPlayingAudio && state.audioQueue.length === 0) {
                finishVoiceTurn();
            }
            break;

        case 'error':
            console.error('[WS] 服务端错误:', msg.error);
            updateCallStatus('listening', '出错：' + msg.error);
            setTimeout(() => {
                if (state.voiceActive) {
                    updateCallStatus('listening', '正在听...');
                    startListening();
                }
            }, 2000);
            break;

        case 'pong':
            break;
    }
}

function finishVoiceTurn() {
    dom.voiceWaveBar.classList.remove('speaking');
    dom.voiceStatusText.classList.remove('speaking');
    dom.callUserText.textContent = '';
    if (state.voiceActive) {
        updateCallStatus('listening', '正在听...');
        startListening();
    }
}

// ============================================================
// 音频播放队列
// ============================================================
function playNextInQueue() {
    if (state.audioQueue.length === 0) {
        state.isPlayingAudio = false;
        dom.voiceWaveBar.classList.remove('speaking');
        dom.voiceStatusText.classList.remove('speaking');
        return;
    }

    state.isPlayingAudio = true;
    const item = state.audioQueue.shift();
    const audioUrl = URL.createObjectURL(item.blob);

    state.currentAudio = audioUrl;
    dom.voiceAudio.src = audioUrl;
    dom.voiceAudio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        state.currentAudio = null;
        playNextInQueue();
    };
    dom.voiceAudio.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        state.currentAudio = null;
        playNextInQueue();
    };
    dom.voiceAudio.play().catch(() => {
        URL.revokeObjectURL(audioUrl);
        state.currentAudio = null;
        playNextInQueue();
    });
}

function stopAllAudio() {
    dom.voiceAudio.pause();
    if (dom.voiceAudio.src) {
        URL.revokeObjectURL(dom.voiceAudio.src);
        dom.voiceAudio.src = '';
    }
    state.audioQueue = [];
    state.isPlayingAudio = false;
    state.currentAudio = null;
}

/**
 * 打断：停止当前 TTS 播放 + LLM 生成，立即开始新录音
 */
function interruptVoice() {
    if (!state.voiceActive) return;

    console.log('[Voice] ⏸ 用户打断');
    state.interruptRequested = true;
    stopAllAudio();
    sendWsMessage({ type: 'interrupt' });
    updateCallStatus('listening', '正在听...');
    dom.callUserText.textContent = '';

    stopListening();
    setTimeout(() => {
        if (state.voiceActive) startListening();
    }, 300);
}

// ============================================================
// 录音 + VAD
// ============================================================
function startListening() {
    if (!state.audioStream) return;

    state.voiceListening = true;
    state.audioChunks = [];
    state.interruptRequested = false;
    dom.callUserText.textContent = '';

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

        try {
            const wavBlob = await convertToWav(audioBlob);
            await sendAudioToServer(wavBlob);
        } catch (e) {
            console.error('[Voice] 音频转换失败：', e);
            await sendAudioToServer(audioBlob);
        }
    };

    state.mediaRecorder.start();
    dom.voiceCallBtn.classList.add('listening');
    startSilenceDetection();
}

function stopListening() {
    state.voiceListening = false;
    stopSilenceDetection();

    if (state.mediaRecorder && state.mediaRecorder.state === 'recording') {
        state.mediaRecorder.stop();
    }
    dom.voiceCallBtn.classList.remove('listening');
}

/**
 * 通过 WebSocket 发送音频到服务器
 */
async function sendAudioToServer(audioBlob) {
    if (!state.voiceActive) return;
    if (!state.wsConnected) {
        console.warn('[WS] 未连接，无法发送音频');
        // 降级到 HTTP
        await processVoiceInputHttp(audioBlob);
        return;
    }

    updateCallStatus('processing', '识别中...');

    const reader = new FileReader();
    reader.onload = () => {
        const base64 = reader.result.split(',')[1];
        sendWsMessage({
            type: 'audio',
            data: base64,
            language: 'zh',
        });
    };
    reader.readAsDataURL(audioBlob);
}

/**
 * HTTP 降级（WebSocket 不可用时）
 */
async function processVoiceInputHttp(audioBlob) {
    if (!state.voiceActive) return;

    updateCallStatus('processing', '识别中...');

    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.wav');
    formData.append('language', 'zh');

    let aiBubble = null;
    let aiFullText = '';

    try {
        const resp = await fetch('/api/voice/chat-stream', { method: 'POST', body: formData });
        if (!resp.ok) {
            let errMsg = '服务器错误';
            try { const errData = await resp.json(); errMsg = errData.error || errMsg; } catch (_) { }
            updateCallStatus('listening', '出错：' + errMsg);
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
                try { data = JSON.parse(line.slice(6)); } catch (_) { continue; }

                if (data.type === 'user' && data.text) {
                    addMessage('user', data.text);
                    dom.callUserText.textContent = data.text;
                    updateCallStatus('processing', '思考中...');
                }
                if (data.type === 'sentence') {
                    if (data.text) {
                        aiFullText += data.text;
                        if (!aiBubble) { aiBubble = createMessageBubble('ai', ''); dom.chatMessages.appendChild(aiBubble); }
                        aiBubble.querySelector('.message-bubble').textContent = aiFullText;
                        scrollToBottom();
                    }
                    if (data.audio) {
                        const ab = base64ToBlob(data.audio, 'audio/wav');
                        state.audioQueue.push({ blob: ab });
                        if (!state.isPlayingAudio) playNextInQueue();
                        updateCallStatus('speaking', '正在说...');
                    }
                }
                if (data.type === 'done') {
                    if (!state.isPlayingAudio && state.audioQueue.length === 0) finishVoiceTurn();
                }
            }
        }
    } catch (e) {
        console.error('[Voice HTTP] 错误:', e);
        updateCallStatus('listening', '连接中断');
        setTimeout(() => { if (state.voiceActive) startListening(); }, 2000);
    }
}

// ============================================================
// 静音检测 (VAD)
// ============================================================
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
        const SILENCE_THRESHOLD = 25;
        const SILENCE_DURATION = 2000;

        _analyserInterval = setInterval(() => {
            if (!state.voiceListening) return;
            _audioAnalyser.getByteFrequencyData(dataArray);
            let sum = 0;
            for (let i = 0; i < bufferLength; i++) sum += dataArray[i];
            const avgVolume = sum / bufferLength;

            if (avgVolume < SILENCE_THRESHOLD) {
                if (!_silenceTimer) {
                    _silenceTimer = setTimeout(() => {
                        if (state.voiceListening && state.mediaRecorder && state.mediaRecorder.state === 'recording') {
                            console.log('[Voice] 静音检测，自动停止录音');
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
        console.log('[Voice] VAD 不可用:', e.message);
        _silenceTimer = setTimeout(() => {
            if (state.voiceListening && state.mediaRecorder && state.mediaRecorder.state === 'recording') {
                stopListening();
            }
        }, 6000);
    }
}

function stopSilenceDetection() {
    if (_silenceTimer) { clearTimeout(_silenceTimer); _silenceTimer = null; }
    if (_analyserInterval) { clearInterval(_analyserInterval); _analyserInterval = null; }
    if (state.audioContext && state.audioContext.state !== 'closed') {
        state.audioContext.close().catch(() => {});
        state.audioContext = null;
    }
    _audioAnalyser = null;
}

// ============================================================
// 音频编码工具
// ============================================================
async function convertToWav(audioBlob) {
    const arrayBuffer = await audioBlob.arrayBuffer();
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
    const targetSampleRate = 16000;
    const offlineCtx = new OfflineAudioContext(
        1, Math.ceil(audioBuffer.duration * targetSampleRate), targetSampleRate
    );
    const source = offlineCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(offlineCtx.destination);
    source.start(0);
    const renderedBuffer = await offlineCtx.startRendering();
    const pcmData = renderedBuffer.getChannelData(0);
    const wavBuffer = encodeWav(pcmData, targetSampleRate);
    audioCtx.close();
    return new Blob([wavBuffer], { type: 'audio/wav' });
}

function encodeWav(samples, sampleRate) {
    const numChannels = 1, bitsPerSample = 16;
    const byteRate = sampleRate * numChannels * bitsPerSample / 8;
    const blockAlign = numChannels * bitsPerSample / 8;
    const dataSize = samples.length * blockAlign;
    const bufferSize = 44 + dataSize;
    const buffer = new ArrayBuffer(bufferSize);
    const view = new DataView(buffer);

    writeString(view, 0, 'RIFF');
    view.setUint32(4, bufferSize - 8, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);
    writeString(view, 36, 'data');
    view.setUint32(40, dataSize, true);

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

function onAudioPlaybackEnded() {
    state.voiceSpeaking = false;
    dom.voiceWaveBar.classList.remove('speaking');
    dom.voiceStatusText.classList.remove('speaking');

    if (dom.voiceAudio.src) {
        URL.revokeObjectURL(dom.voiceAudio.src);
        dom.voiceAudio.src = '';
    }

    if (state.voiceActive && !state.isPlayingAudio && state.audioQueue.length === 0) {
        updateVoiceStatus('listening', '正在听...');
        startListening();
    }
}

function updateVoiceStatus(statusType, text) {
    dom.voiceStatusText.textContent = text;
    dom.voiceStatusText.className = 'voice-text';
    if (statusType === 'speaking') {
        dom.voiceStatusText.classList.add('speaking');
        dom.voiceWaveBar.classList.add('speaking');
    } else {
        dom.voiceWaveBar.classList.remove('speaking');
    }
}

// ============================================================
// Startup
// ============================================================
document.addEventListener('DOMContentLoaded', init);

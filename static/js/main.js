
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
// Startup
// ============================================================
document.addEventListener('DOMContentLoaded', init);

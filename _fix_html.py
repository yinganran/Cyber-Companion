# -*- coding: utf-8 -*-
with open('templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Restore header bar after '<div class="call-screen">'
for i, line in enumerate(lines):
    if '<div class="call-screen">' in line and 'call-body' not in line:
        header = [
            '        <div class="call-header-bar">\n',
            '            <button class="call-minimize-btn" id="callMinimizeBtn" title="切回聊天">\n',
            '                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"></polyline></svg>\n',
            '            </button>\n',
            '            <span class="call-title">语音通话中</span>\n',
            '            <span class="call-timer" id="callTimer">00:00</span>\n',
            '        </div>\n',
            '\n',
        ]
        lines[i+1:i+1] = header
        break

# Restore float badge before learning modal
for i, line in enumerate(lines):
    if '学习结果弹窗' in line:
        float_badge = [
            '\n',
            '    <!-- 通话最小化后的浮动按钮 -->\n',
            '    <div class="call-float-badge" id="callFloatBadge" style="display:none;">\n',
            '        <div class="call-float-avatar" id="callFloatAvatar">\n',
            '            <img id="callFloatAvatarImg" src="/static/uploads/avatars/default_ai.png" alt="AI">\n',
            '        </div>\n',
            '        <div class="call-float-wave"><span></span><span></span><span></span></div>\n',
            '        <span class="call-float-time" id="callFloatTimer">00:00</span>\n',
            '        <button class="call-float-end" id="callFloatEndBtn">✕</button>\n',
            '    </div>\n',
            '\n',
        ]
        lines[i:i] = float_badge
        break

with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Done')

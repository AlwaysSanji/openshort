/**
 * OpenShort LiveClipper Frontend Engine
 * Real-time WebSocket Telemetry, Clip Gallery, Studio & Social Converter
 */

// State
let ws = null;
let currentConfig = {};
let clipsList = [];
let activeFilter = 'all';
let currentModalClip = null;
let activeFormat = '16x9'; // '16x9' or '9x16'

// DOM Elements
const streamStatusPill = document.getElementById('streamStatusPill');
const streamStatusText = document.getElementById('streamStatusText');
const bufferStatusText = document.getElementById('bufferStatusText');
const btnHeaderClipNow = document.getElementById('btnHeaderClipNow');
const btnEmptyClipNow = document.getElementById('btnEmptyClipNow');
const btnStartCapture = document.getElementById('btnStartCapture');
const btnStopCapture = document.getElementById('btnStopCapture');
const sourceTargetInput = document.getElementById('sourceTargetInput');
const sourceInputWrap = document.getElementById('sourceInputWrap');
const sourceInputLabel = document.getElementById('sourceInputLabel');

// Excitement Gauge Elements
const gaugeBar = document.getElementById('gaugeBar');
const compositeScoreVal = document.getElementById('compositeScoreVal');
const audioScoreVal = document.getElementById('audioScoreVal');
const motionScoreVal = document.getElementById('motionScoreVal');
const chatScoreVal = document.getElementById('chatScoreVal');
const audioProgressFill = document.getElementById('audioProgressFill');
const motionProgressFill = document.getElementById('motionProgressFill');
const chatProgressFill = document.getElementById('chatProgressFill');
const quickThresholdSlider = document.getElementById('quickThresholdSlider');
const thresholdValDisplay = document.getElementById('thresholdValDisplay');

// Activity Log & Gallery
const activityLog = document.getElementById('activityLog');
const btnClearLog = document.getElementById('btnClearLog');
const clipsCountBadge = document.getElementById('clipsCountBadge');
const emptyClipsState = document.getElementById('emptyClipsState');
const clipsGrid = document.getElementById('clipsGrid');
const btnRefreshClips = document.getElementById('btnRefreshClips');

// Studio Modal Elements
const playerModal = document.getElementById('playerModal');
const btnCloseModal = document.getElementById('btnCloseModal');
const modalVideoPlayer = document.getElementById('modalVideoPlayer');
const modalClipTitle = document.getElementById('modalClipTitle');
const modalClipScore = document.getElementById('modalClipScore');
const modalClipReason = document.getElementById('modalClipReason');
const modalClipDuration = document.getElementById('modalClipDuration');
const modalClipTime = document.getElementById('modalClipTime');
const btnView16x9 = document.getElementById('btnView16x9');
const btnView9x16 = document.getElementById('btnView9x16');
const btnGenerateShort = document.getElementById('btnGenerateShort');
const btnTranscribeClip = document.getElementById('btnTranscribeClip');
const btnOpenInExplorer = document.getElementById('btnOpenInExplorer');
const btnDownloadClip = document.getElementById('btnDownloadClip');
const trimStartInput = document.getElementById('trimStartInput');
const trimEndInput = document.getElementById('trimEndInput');
const btnApplyTrim = document.getElementById('btnApplyTrim');

// Settings Modal
const settingsModal = document.getElementById('settingsModal');
const btnOpenSettings = document.getElementById('btnOpenSettings');
const btnCloseSettings = document.getElementById('btnCloseSettings');
const btnSaveSettings = document.getElementById('btnSaveSettings');

// Radial Gauge Constants (r=68 -> Circumference = 2 * PI * 68 = 427.25)
const GAUGE_CIRCUMFERENCE = 427.25;

// Initialize WebSocket
function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log('[WebSocket] Connected to OpenShort LiveClipper');
    addLogEntry('Connected to live engine', 'info');
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleWsMessage(msg);
    } catch (e) {
      console.error('[WebSocket] Parse error:', e);
    }
  };

  ws.onclose = () => {
    console.log('[WebSocket] Closed. Reconnecting in 2s...');
    setTimeout(initWebSocket, 2000);
  };
}

function handleWsMessage(msg) {
  const { type, data } = msg;

  if (type === 'init') {
    currentConfig = data.config || {};
    clipsList = data.clips || [];
    syncConfigInputs(currentConfig);
    updateStreamingState(data.is_active, data.source_type);
    renderClipsGrid();
  }
  else if (type === 'telemetry') {
    updateTelemetry(data);
  }
  else if (type === 'new_clip') {
    handleNewClip(data);
  }
  else if (type === 'delete_clip') {
    clipsList = clipsList.filter(c => c.id !== data.id);
    renderClipsGrid();
  }
  else if (type === 'status_change') {
    updateStreamingState(data.is_active, data.source_type);
  }
  else if (type === 'config_updated') {
    currentConfig = data;
    syncConfigInputs(currentConfig);
  }
}

// Telemetry visual updates
function updateTelemetry(data) {
  const { is_active, buffer, metrics } = data;
  updateStreamingState(is_active);

  // Buffer stats
  if (buffer) {
    bufferStatusText.textContent = `${buffer.buffered_seconds}s / ${buffer.max_seconds}s Buffer`;
  }

  if (!metrics) return;

  const score = metrics.composite_score || 0;
  compositeScoreVal.textContent = `${Math.round(score)}%`;

  // Update radial gauge
  const offset = GAUGE_CIRCUMFERENCE - (score / 100) * GAUGE_CIRCUMFERENCE;
  gaugeBar.style.strokeDashoffset = offset;

  // Change gauge color based on intensity
  if (score >= (currentConfig.excitement_threshold || 70)) {
    gaugeBar.style.stroke = '#f43f5e'; // Red surge
  } else if (score >= 50) {
    gaugeBar.style.stroke = '#f59e0b'; // Amber warming up
  } else {
    gaugeBar.style.stroke = '#06b6d4'; // Cyan normal
  }

  // Audio row
  const audioScore = metrics.audio_score || 0;
  const audioDb = metrics.audio_db || -60;
  audioScoreVal.textContent = `${Math.round(audioScore)}% (${audioDb} dB)`;
  audioProgressFill.style.width = `${audioScore}%`;

  // Motion row
  const motionScore = metrics.motion_score || 0;
  motionScoreVal.textContent = `${Math.round(motionScore)}%`;
  motionProgressFill.style.width = `${motionScore}%`;

  // Chat row
  const chatScore = metrics.chat_score || 0;
  const chatRate = metrics.chat_msg_rate || 0;
  chatScoreVal.textContent = `${Math.round(chatScore)}% (${chatRate} msg/s)`;
  chatProgressFill.style.width = `${chatScore}%`;

  // Log triggers
  if (metrics.is_triggered && metrics.trigger_reason) {
    addLogEntry(`🔥 ${metrics.trigger_reason} (Score: ${Math.round(score)}%) - Queuing clip...`, 'trigger');
    showToast(`🔥 Highlight Triggered: ${metrics.trigger_reason}!`, 'trigger');
  }
}

function handleNewClip(clip) {
  // Add to beginning of list
  const exists = clipsList.some(c => c.id === clip.id);
  if (!exists) {
    clipsList.unshift(clip);
  } else {
    clipsList = clipsList.map(c => c.id === clip.id ? clip : c);
  }

  renderClipsGrid();
  addLogEntry(`✅ Saved Clip: ${clip.filename} (${clip.duration}s)`, 'saved');
  showToast(`✅ Saved Highlight: ${clip.title}!`, 'success');
}

function updateStreamingState(isActive, sourceType) {
  if (isActive) {
    streamStatusPill.className = 'stream-status-pill active';
    streamStatusText.textContent = '● WATCHING LIVE';
    btnStartCapture.style.display = 'none';
    btnStopCapture.style.display = 'inline-flex';
  } else {
    streamStatusPill.className = 'stream-status-pill';
    streamStatusText.textContent = '○ SYSTEM IDLE';
    btnStartCapture.style.display = 'inline-flex';
    btnStopCapture.style.display = 'none';
  }
}

// Activity Log Helper
function addLogEntry(text, type = 'info') {
  const now = new Date();
  const timeStr = now.toTimeString().split(' ')[0];
  const div = document.createElement('div');
  div.className = `log-entry ${type}`;
  div.innerHTML = `<span class="log-time">${timeStr}</span><span class="log-msg">${text}</span>`;
  activityLog.prepend(div);

  // Keep max 50 log items
  while (activityLog.children.length > 50) {
    activityLog.removeChild(activityLog.lastChild);
  }
}

btnClearLog.addEventListener('click', () => {
  activityLog.innerHTML = '';
});

// Render Clips Grid
function renderClipsGrid() {
  const filtered = clipsList.filter(c => {
    if (activeFilter === 'manual') return (c.trigger_reason || '').toLowerCase().includes('manual') || (c.trigger_reason || '').includes('F9');
    if (activeFilter === 'auto') return !(c.trigger_reason || '').toLowerCase().includes('manual') && !(c.trigger_reason || '').includes('F9');
    return true;
  });

  clipsCountBadge.textContent = `${clipsList.length} clips`;

  if (filtered.length === 0) {
    emptyClipsState.style.display = 'flex';
    clipsGrid.style.display = 'none';
    return;
  }

  emptyClipsState.style.display = 'none';
  clipsGrid.style.display = 'grid';
  clipsGrid.innerHTML = '';

  filtered.forEach(clip => {
    const card = document.createElement('div');
    card.className = 'clip-card';

    const thumbUrl = `/clips_media/${clip.thumb_filename}?t=${Date.now()}`;
    const scoreVal = Math.round(clip.excitement_score || 80);

    card.innerHTML = `
      <div class="clip-thumb-wrap" onclick="openStudioModal('${clip.id}')">
        <img src="${thumbUrl}" alt="Thumbnail" onerror="this.src='/static/thumb_fallback.png'">
        <span class="clip-badge-score">🔥 ${scoreVal}%</span>
        <span class="clip-badge-duration">${clip.duration}s</span>
        ${clip.has_short ? '<span class="clip-badge-short">9:16 SHORT</span>' : ''}
      </div>
      <div class="clip-info-box">
        <div class="clip-title" title="${clip.title}">${clip.title}</div>
        <div class="clip-meta-row">
          <span>${clip.trigger_reason || 'Highlight'}</span>
          <span>${clip.file_size_mb || 0} MB</span>
        </div>
        <div class="clip-meta-row">
          <span>${clip.created_at || ''}</span>
        </div>
        <div class="clip-action-buttons">
          <button class="btn btn-secondary btn-sm" onclick="openStudioModal('${clip.id}')">▶ Play</button>
          <button class="btn btn-secondary btn-sm" onclick="quickMakeShort('${clip.id}', event)">📱 Short</button>
          <button class="btn btn-secondary btn-sm" onclick="revealInExplorer('${clip.id}', event)" title="Open in Windows Explorer">📁</button>
          <button class="btn btn-secondary btn-sm" onclick="deleteClip('${clip.id}', event)" title="Delete Clip">🗑️</button>
        </div>
      </div>
    `;
    clipsGrid.appendChild(card);
  });
}

// Source Radio Toggle
document.querySelectorAll('input[name="source_type"]').forEach(r => {
  r.addEventListener('change', (e) => {
    document.querySelectorAll('.source-opt').forEach(opt => opt.classList.remove('active'));
    e.target.closest('.source-opt').classList.add('active');

    const val = e.target.value;
    if (val === 'url') {
      sourceInputWrap.style.display = 'block';
      sourceInputLabel.textContent = 'Twitch or YouTube Live URL:';
      sourceTargetInput.placeholder = 'https://www.twitch.tv/shroud or YouTube Live URL';
    } else if (val === 'file') {
      sourceInputWrap.style.display = 'block';
      sourceInputLabel.textContent = 'Local Video File Path:';
      sourceTargetInput.placeholder = 'C:\\path\\to\\recording.mp4';
    } else {
      sourceInputWrap.style.display = 'none';
    }
  });
});

// Start & Stop Monitoring
btnStartCapture.addEventListener('click', async () => {
  const selectedRadio = document.querySelector('input[name="source_type"]:checked');
  const sourceType = selectedRadio ? selectedRadio.value : 'simulator';
  const sourceTarget = sourceTargetInput.value.trim();

  if ((sourceType === 'url' || sourceType === 'file') && !sourceTarget) {
    showToast('Please provide a valid URL or file path.', 'trigger');
    return;
  }

  try {
    btnStartCapture.disabled = true;
    btnStartCapture.textContent = 'Connecting...';
    const res = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_type: sourceType, source_target: sourceTarget })
    });
    if (!res.ok) {
      const err = await res.json();
      showToast(`Failed: ${err.detail || 'Could not connect'}`, 'trigger');
    } else {
      showToast(`Started monitoring [${sourceType.toUpperCase()}]`, 'success');
      addLogEntry(`Started live stream ingestion: ${sourceType}`, 'info');
    }
  } catch (err) {
    showToast(`Error starting: ${err}`, 'trigger');
  } finally {
    btnStartCapture.disabled = false;
    btnStartCapture.innerHTML = '<span class="btn-icon">▶</span> START WATCHING LIVE';
  }
});

btnStopCapture.addEventListener('click', async () => {
  try {
    await fetch('/api/stop', { method: 'POST' });
    showToast('Monitoring stopped.', 'info');
    addLogEntry('Monitoring stopped by user', 'info');
  } catch (err) {
    console.error(err);
  }
});

// Instant Clip Trigger (Header button & F9)
async function triggerInstantClip() {
  try {
    showToast('⚡ Slicing highlight from buffer...', 'trigger');
    addLogEntry('⚡ Instant clip triggered manually (F9)', 'trigger');
    const res = await fetch('/api/clip_now', { method: 'POST' });
    if (!res.ok) {
      showToast('Buffer may be empty or warming up. Wait a few seconds.', 'trigger');
    } else {
      const clip = await res.json();
      handleNewClip(clip);
    }
  } catch (e) {
    showToast('Error triggering clip.', 'trigger');
  }
}

btnHeaderClipNow.addEventListener('click', triggerInstantClip);
btnEmptyClipNow.addEventListener('click', triggerInstantClip);

// Browser hotkey listener for F9
window.addEventListener('keydown', (e) => {
  if (e.key === 'F9') {
    e.preventDefault();
    triggerInstantClip();
  }
});

// Quick Threshold Slider
quickThresholdSlider.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  thresholdValDisplay.textContent = `${val}%`;
});

quickThresholdSlider.addEventListener('change', async (e) => {
  const val = parseInt(e.target.value);
  currentConfig.excitement_threshold = val;
  await saveConfigToServer();
});

// Filter Chips
document.querySelectorAll('.filter-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    activeFilter = chip.dataset.filter;
    renderClipsGrid();
  });
});

btnRefreshClips.addEventListener('click', async () => {
  try {
    const res = await fetch('/api/clips');
    clipsList = await res.json();
    renderClipsGrid();
    showToast('Clips refreshed', 'info');
  } catch (e) {
    console.error(e);
  }
});

// Studio Modal Logic
window.openStudioModal = function(clipId) {
  const clip = clipsList.find(c => c.id === clipId);
  if (!clip) return;

  currentModalClip = clip;
  activeFormat = '16x9';

  modalClipTitle.textContent = clip.title;
  modalClipScore.textContent = `${Math.round(clip.excitement_score)}%`;
  modalClipReason.textContent = clip.trigger_reason;
  modalClipDuration.textContent = `${clip.duration}s`;
  modalClipTime.textContent = clip.created_at;

  trimStartInput.value = 0;
  trimEndInput.value = Math.max(1, clip.duration);

  btnView16x9.classList.add('active');
  btnView9x16.classList.remove('active');

  modalVideoPlayer.src = `/clips_media/${clip.filename}`;
  modalVideoPlayer.play().catch(() => {});

  btnDownloadClip.href = `/clips_media/${clip.filename}`;
  btnDownloadClip.download = clip.filename;

  playerModal.style.display = 'flex';
};

btnCloseModal.addEventListener('click', () => {
  modalVideoPlayer.pause();
  modalVideoPlayer.src = '';
  playerModal.style.display = 'none';
});

// Switch format inside modal
btnView16x9.addEventListener('click', () => {
  if (!currentModalClip) return;
  activeFormat = '16x9';
  btnView16x9.classList.add('active');
  btnView9x16.classList.remove('active');
  modalVideoPlayer.src = `/clips_media/${currentModalClip.filename}`;
  btnDownloadClip.href = `/clips_media/${currentModalClip.filename}`;
  btnDownloadClip.download = currentModalClip.filename;
});

btnView9x16.addEventListener('click', () => {
  if (!currentModalClip) return;
  if (!currentModalClip.has_short) {
    showToast('Generate 9:16 Short first by clicking the button below!', 'trigger');
    return;
  }
  activeFormat = '9x16';
  btnView9x16.classList.add('active');
  btnView16x9.classList.remove('active');
  modalVideoPlayer.src = `/clips_media/${currentModalClip.short_filename}`;
  btnDownloadClip.href = `/clips_media/${currentModalClip.short_filename}`;
  btnDownloadClip.download = currentModalClip.short_filename;
});

// Generate 9:16 Short
btnGenerateShort.addEventListener('click', async () => {
  if (!currentModalClip) return;
  const style = document.getElementById('shortStyleSelect').value;
  const burnCaptions = document.getElementById('chkBurnCaptions').checked;
  const colorPop = document.getElementById('chkColorPop').checked;
  const audioEnhance = document.getElementById('chkAudioLoudnorm').checked;

  btnGenerateShort.disabled = true;
  btnGenerateShort.textContent = '⏳ Rendering Pro 9:16 Short...';

  try {
    const res = await fetch(`/api/clips/${currentModalClip.id}/short`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        style: style,
        burn_captions: burnCaptions,
        color_pop: colorPop,
        audio_enhance: audioEnhance
      })
    });
    if (res.ok) {
      const data = await res.json();
      currentModalClip.has_short = true;
      currentModalClip.short_filename = data.short_filename;
      showToast('📱 Studio 9:16 Short ready for TikTok / Reels!', 'success');
      btnView9x16.click(); // switch to short view
      renderClipsGrid();
    } else {
      showToast('Failed to generate short.', 'trigger');
    }
  } catch (e) {
    showToast('Error converting short.', 'trigger');
  } finally {
    btnGenerateShort.disabled = false;
    btnGenerateShort.textContent = '📱 Render Studio 9:16 Short';
  }
});

// Remaster 16:9 Clip
const btnRemasterClip = document.getElementById('btnRemasterClip');
if (btnRemasterClip) {
  btnRemasterClip.addEventListener('click', async () => {
    if (!currentModalClip) return;
    const colorPop = document.getElementById('chkColorPop').checked;
    const audioEnhance = document.getElementById('chkAudioLoudnorm').checked;
    const burnCaptions = document.getElementById('chkBurnCaptions').checked;

    btnRemasterClip.disabled = true;
    btnRemasterClip.textContent = '⏳ Remastering Video & Audio...';

    try {
      const res = await fetch(`/api/clips/${currentModalClip.id}/enhance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          color_pop: colorPop,
          audio_loudnorm: audioEnhance,
          burn_captions: burnCaptions
        })
      });
      if (res.ok) {
        const enhancedClip = await res.json();
        handleNewClip(enhancedClip);
        showToast('✨ Remastered clip created!', 'success');
        openStudioModal(enhancedClip.id);
      } else {
        showToast('Remaster failed.', 'trigger');
      }
    } catch (e) {
      showToast('Error remastering.', 'trigger');
    } finally {
      btnRemasterClip.disabled = false;
      btnRemasterClip.textContent = '✨ Remaster 16:9 Clip (HDR Color & Audio Polish)';
    }
  });
}

// Transcribe with Whisper
btnTranscribeClip.addEventListener('click', async () => {
  if (!currentModalClip) return;
  btnTranscribeClip.disabled = true;
  btnTranscribeClip.textContent = '🎙️ Transcribing with Whisper AI...';

  try {
    const res = await fetch(`/api/clips/${currentModalClip.id}/transcribe`, { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      showToast(`🎙️ Subtitles created: ${data.srt_file}`, 'success');
    } else {
      showToast('Whisper transcription failed.', 'trigger');
    }
  } catch (e) {
    showToast('Transcription error.', 'trigger');
  } finally {
    btnTranscribeClip.disabled = false;
    btnTranscribeClip.textContent = '🎙️ Auto-Generate Subtitles (Whisper AI)';
  }
});

// Open in Explorer
window.revealInExplorer = async function(clipId, e) {
  if (e) e.stopPropagation();
  try {
    await fetch(`/api/clips/${clipId}/open`, { method: 'POST' });
    showToast('📁 Opened in Windows File Explorer', 'info');
  } catch (err) {
    console.error(err);
  }
};

btnOpenInExplorer.addEventListener('click', () => {
  if (currentModalClip) revealInExplorer(currentModalClip.id);
});

// Quick Short from card
window.quickMakeShort = async function(clipId, e) {
  if (e) e.stopPropagation();
  showToast('📱 Rendering 9:16 Vertical Short in background...', 'info');
  try {
    const res = await fetch(`/api/clips/${clipId}/short`, { method: 'POST' });
    if (res.ok) {
      showToast('✅ 9:16 Short generated!', 'success');
      const clip = clipsList.find(c => c.id === clipId);
      if (clip) clip.has_short = true;
      renderClipsGrid();
    }
  } catch (err) {
    console.error(err);
  }
};

// Delete Clip
window.deleteClip = async function(clipId, e) {
  if (e) e.stopPropagation();
  if (!confirm('Are you sure you want to delete this highlight?')) return;

  try {
    const res = await fetch(`/api/clips/${clipId}`, { method: 'DELETE' });
    if (res.ok) {
      clipsList = clipsList.filter(c => c.id !== clipId);
      renderClipsGrid();
      showToast('Clip deleted.', 'info');
      if (currentModalClip && currentModalClip.id === clipId) {
        playerModal.style.display = 'none';
      }
    }
  } catch (err) {
    console.error(err);
  }
};

// Apply Trim
btnApplyTrim.addEventListener('click', async () => {
  if (!currentModalClip) return;
  const start = parseFloat(trimStartInput.value);
  const end = parseFloat(trimEndInput.value);

  if (end <= start) {
    showToast('End time must be greater than start time.', 'trigger');
    return;
  }

  btnApplyTrim.disabled = true;
  btnApplyTrim.textContent = '⏳ Saving Trim...';

  try {
    const res = await fetch(`/api/clips/${currentModalClip.id}/trim`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ start_time: start, end_time: end })
    });
    if (res.ok) {
      const trimmedClip = await res.json();
      handleNewClip(trimmedClip);
      showToast('✂️ Trimmed clip saved!', 'success');
      openStudioModal(trimmedClip.id);
    } else {
      showToast('Trim failed.', 'trigger');
    }
  } catch (e) {
    showToast('Trim error.', 'trigger');
  } finally {
    btnApplyTrim.disabled = false;
    btnApplyTrim.textContent = '✂️ Save Trimmed Version';
  }
});

// Settings Modal Logic
btnOpenSettings.addEventListener('click', () => {
  syncConfigInputs(currentConfig);
  settingsModal.style.display = 'flex';
});

btnCloseSettings.addEventListener('click', () => {
  settingsModal.style.display = 'none';
});

function syncConfigInputs(cfg) {
  if (!cfg) return;
  document.getElementById('cfgThreshold').value = cfg.excitement_threshold || 70;
  document.getElementById('cfgThresholdVal').textContent = `${cfg.excitement_threshold || 70}%`;
  quickThresholdSlider.value = cfg.excitement_threshold || 70;
  thresholdValDisplay.textContent = `${cfg.excitement_threshold || 70}%`;

  document.getElementById('cfgPreRoll').value = cfg.pre_roll || 15;
  document.getElementById('cfgPostRoll').value = cfg.post_roll || 10;

  document.getElementById('cfgAudioSens').value = cfg.audio_sensitivity || 1.0;
  document.getElementById('cfgAudioSensVal').textContent = `${cfg.audio_sensitivity || 1.0}x`;

  document.getElementById('cfgMotionSens').value = cfg.motion_sensitivity || 1.0;
  document.getElementById('cfgMotionSensVal').textContent = `${cfg.motion_sensitivity || 1.0}x`;

  document.getElementById('cfgAudioWeight').value = cfg.audio_weight || 0.50;
  document.getElementById('cfgMotionWeight').value = cfg.motion_weight || 0.30;
  document.getElementById('cfgChatWeight').value = cfg.chat_weight || 0.20;

  document.getElementById('cfgAutoShorts').checked = !!cfg.auto_generate_shorts;
  document.getElementById('cfgShortsStyle').value = cfg.shorts_style || 'blurred_bg';
}

document.getElementById('cfgThreshold').addEventListener('input', (e) => {
  document.getElementById('cfgThresholdVal').textContent = `${e.target.value}%`;
});
document.getElementById('cfgAudioSens').addEventListener('input', (e) => {
  document.getElementById('cfgAudioSensVal').textContent = `${e.target.value}x`;
});
document.getElementById('cfgMotionSens').addEventListener('input', (e) => {
  document.getElementById('cfgMotionSensVal').textContent = `${e.target.value}x`;
});

async function saveConfigToServer() {
  const payload = {
    pre_roll: parseInt(document.getElementById('cfgPreRoll').value),
    post_roll: parseInt(document.getElementById('cfgPostRoll').value),
    excitement_threshold: parseInt(document.getElementById('cfgThreshold').value),
    audio_sensitivity: parseFloat(document.getElementById('cfgAudioSens').value),
    motion_sensitivity: parseFloat(document.getElementById('cfgMotionSens').value),
    audio_weight: parseFloat(document.getElementById('cfgAudioWeight').value),
    motion_weight: parseFloat(document.getElementById('cfgMotionWeight').value),
    chat_weight: parseFloat(document.getElementById('cfgChatWeight').value),
    auto_generate_shorts: document.getElementById('cfgAutoShorts').checked,
    shorts_style: document.getElementById('cfgShortsStyle').value
  };

  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast('Settings saved successfully!', 'success');
      currentConfig = payload;
      syncConfigInputs(currentConfig);
    }
  } catch (err) {
    console.error(err);
  }
}

btnSaveSettings.addEventListener('click', async () => {
  await saveConfigToServer();
  settingsModal.style.display = 'none';
});

// Toast notification helper
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.4s ease';
    setTimeout(() => toast.remove(), 400);
  }, 4000);
}

// Start WebSocket on page load
window.addEventListener('DOMContentLoaded', () => {
  initWebSocket();
  initLinkClipperUI();
});

// Dedicated Link Clipper Controller
function initLinkClipperUI() {
  const tabBtnLive = document.getElementById('tabBtnLive');
  const tabBtnLink = document.getElementById('tabBtnLink');
  const liveSourceCard = document.getElementById('liveSourceCard');
  const linkClipperCard = document.getElementById('linkClipperCard');

  const directLinkInput = document.getElementById('directLinkInput');
  const linkTimeInputs = document.getElementById('linkTimeInputs');
  const linkStartTime = document.getElementById('linkStartTime');
  const linkDuration = document.getElementById('linkDuration');
  const linkAutoShort = document.getElementById('linkAutoShort');
  const btnClipFromLink = document.getElementById('btnClipFromLink');
  const linkStatusBox = document.getElementById('linkStatusBox');
  const linkStatusText = document.getElementById('linkStatusText');

  // Tab switching
  tabBtnLive.addEventListener('click', () => {
    tabBtnLive.classList.add('active');
    tabBtnLink.classList.remove('active');
    liveSourceCard.style.display = 'block';
    linkClipperCard.style.display = 'none';
  });

  tabBtnLink.addEventListener('click', () => {
    tabBtnLink.classList.add('active');
    tabBtnLive.classList.remove('active');
    liveSourceCard.style.display = 'none';
    linkClipperCard.style.display = 'block';
  });

  // Mode radio toggle
  document.querySelectorAll('input[name="link_clip_mode"]').forEach(r => {
    r.addEventListener('change', (e) => {
      if (e.target.value === 'manual') {
        linkTimeInputs.style.display = 'grid';
      } else {
        linkTimeInputs.style.display = 'none';
      }
    });
  });

  // Time string parser helper (e.g. "01:30" -> 90, "45" -> 45)
  function parseTimeToSeconds(val) {
    if (!val) return 0;
    const str = String(val).trim();
    if (str.includes(':')) {
      const parts = str.split(':').map(Number);
      if (parts.length === 2) return parts[0] * 60 + parts[1];
      if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    }
    const num = parseFloat(str);
    return isNaN(num) ? 0 : num;
  }

  // Clip from Link Button Action
  btnClipFromLink.addEventListener('click', async () => {
    const url = directLinkInput.value.trim();
    if (!url) {
      showToast('Please paste a valid video or live stream link.', 'trigger');
      directLinkInput.focus();
      return;
    }

    const selectedMode = document.querySelector('input[name="link_clip_mode"]:checked').value;
    const startSec = selectedMode === 'manual' ? parseTimeToSeconds(linkStartTime.value) : null;
    const durSec = parseFloat(linkDuration.value) || 20;
    const autoShort = linkAutoShort.checked;

    btnClipFromLink.disabled = true;
    btnClipFromLink.innerHTML = '<span class="btn-icon">⏳</span> EXTRACTING CLIP...';
    linkStatusBox.style.display = 'flex';
    linkStatusText.textContent = selectedMode === 'auto' 
      ? 'Analyzing video content & extracting peak excitement moment...'
      : `Extracting section from ${linkStartTime.value} (${durSec}s)...`;

    addLogEntry(`🔗 Starting link extraction for: ${url.slice(0, 40)}...`, 'info');

    try {
      const res = await fetch('/api/clip_from_link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: url,
          start_time: startSec,
          duration: durSec,
          mode: selectedMode,
          auto_short: autoShort
        })
      });

      if (!res.ok) {
        const err = await res.json();
        showToast(`Extraction failed: ${err.detail || 'Could not process URL'}`, 'trigger');
        addLogEntry(`Link clip failed: ${err.detail || 'Error'}`, 'info');
      } else {
        const newClip = await res.json();
        handleNewClip(newClip);
        showToast(`✅ Created clip: ${newClip.title}!`, 'success');
        addLogEntry(`✅ Clip created from link: ${newClip.filename}`, 'saved');
        
        // Automatically open the new clip in the studio player
        setTimeout(() => {
          openStudioModal(newClip.id);
        }, 500);
      }
    } catch (e) {
      showToast(`Network error: ${e}`, 'trigger');
    } finally {
      btnClipFromLink.disabled = false;
      btnClipFromLink.innerHTML = '<span class="btn-icon">✂️</span> CLIP VIDEO FROM LINK';
      linkStatusBox.style.display = 'none';
    }
  });
}

// ========================================================
// TRIGGERABLE RADIO — Frontend Client Script
// ========================================================

let isPlaying = false;
let isBluetoothConnected = false;
let visualizerAnimId = null;

// DOM Elements
const radioStatusPill = document.getElementById('radioStatusPill');
const radioStatusText = document.getElementById('radioStatusText');
const headerPulseDot = document.getElementById('headerPulseDot');
const mainToggleBtn = document.getElementById('mainToggleBtn');
const mainBtnText = document.getElementById('mainBtnText');
const playIcon = document.getElementById('playIcon');
const stopIcon = document.getElementById('stopIcon');
const visualizerCanvas = document.getElementById('visualizerCanvas');
const visualizerOverlay = document.getElementById('visualizerOverlay');
const volumeSlider = document.getElementById('volumeSlider');
const volumeValue = document.getElementById('volumeValue');

const btStatusTag = document.getElementById('btStatusTag');
const btStatusText = document.getElementById('btStatusText');
const btDeviceName = document.getElementById('btDeviceName');

const logsContainer = document.getElementById('logsContainer');
const toastNotification = document.getElementById('toastNotification');
const toastMessage = document.getElementById('toastMessage');

// ==========================================
// AUDIO SPECTRUM VISUALIZER (CANVAS)
// ==========================================
const ctx = visualizerCanvas.getContext('2d');
const numBars = 42;
let barHeights = new Array(numBars).fill(2);
let targetHeights = new Array(numBars).fill(2);

function initVisualizer() {
  function resize() {
    visualizerCanvas.width = visualizerCanvas.parentElement.clientWidth - 32;
    visualizerCanvas.height = 70;
  }
  window.addEventListener('resize', resize);
  resize();
  drawVisualizer();
}

function drawVisualizer() {
  ctx.clearRect(0, 0, visualizerCanvas.width, visualizerCanvas.height);
  
  const w = visualizerCanvas.width;
  const h = visualizerCanvas.height;
  const barWidth = (w / numBars) - 3;

  for (let i = 0; i < numBars; i++) {
    if (isPlaying) {
      // Dynamic simulated audio spectrum
      if (Math.random() > 0.45) {
        // Higher energy in lower/mid frequencies
        const factor = Math.sin((i / numBars) * Math.PI);
        targetHeights[i] = Math.max(4, Math.random() * h * (0.35 + factor * 0.65));
      }
      barHeights[i] += (targetHeights[i] - barHeights[i]) * 0.22;
    } else {
      barHeights[i] += (2 - barHeights[i]) * 0.15;
    }

    const bh = Math.max(2, barHeights[i]);
    const x = i * (barWidth + 3);
    const y = h - bh;

    // Gradient bar
    const grad = ctx.createLinearGradient(0, y, 0, h);
    if (isPlaying) {
      grad.addColorStop(0, '#06b6d4');
      grad.addColorStop(0.5, '#3b82f6');
      grad.addColorStop(1, '#8b5cf6');
    } else {
      grad.addColorStop(0, 'rgba(100, 116, 139, 0.4)');
      grad.addColorStop(1, 'rgba(51, 65, 85, 0.2)');
    }

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.roundRect(x, y, barWidth, bh, [3, 3, 0, 0]);
    ctx.fill();
  }

  visualizerAnimId = requestAnimationFrame(drawVisualizer);
}

// ==========================================
// STATE UPDATE & POLLING
// ==========================================
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();
    updateUI(data);
  } catch (err) {
    console.debug('Durum kontrolü hatası:', err);
  }
}

function updateUI(data) {
  const radio = data.radio;
  const bt = data.bluetooth;

  isPlaying = radio.is_playing;
  isBluetoothConnected = bt.is_connected;

  // Radio Status Pill
  if (isPlaying) {
    radioStatusPill.className = 'status-indicator-pill active';
    radioStatusText.textContent = 'CANLI YAYINDA';
    headerPulseDot.className = 'live-pulse-dot';
    visualizerOverlay.classList.add('hidden');

    // Main button state
    mainToggleBtn.className = 'play-btn playing';
    mainBtnText.textContent = 'Radyoyu Durdur';
    playIcon.classList.add('hidden');
    stopIcon.classList.remove('hidden');
  } else {
    radioStatusPill.className = 'status-indicator-pill closed';
    radioStatusText.textContent = 'KAPALI (CLOSED)';
    headerPulseDot.className = 'live-pulse-dot inactive';
    visualizerOverlay.classList.remove('hidden');

    // Main button state
    mainToggleBtn.className = 'play-btn';
    mainBtnText.textContent = 'Radyoyu Başlat';
    playIcon.classList.remove('hidden');
    stopIcon.classList.add('hidden');
  }

  // Bluetooth status
  if (isBluetoothConnected) {
    btStatusTag.className = 'bt-status-tag connected';
    btStatusText.textContent = 'Bağlı (Connected)';
  } else {
    btStatusTag.className = 'bt-status-tag disconnected';
    btStatusText.textContent = bt.last_status_message || 'Bağlantı Aranıyor...';
  }

  if (bt.device_name && bt.device_name !== 'Bilinmeyen Cihaz') {
    btDeviceName.textContent = bt.device_name;
  }

  // Volume slider sync
  if (document.activeElement !== volumeSlider && radio.volume !== undefined) {
    volumeSlider.value = radio.volume;
    volumeValue.textContent = radio.volume + '%';
  }
}

// ==========================================
// USER ACTIONS
// ==========================================
async function toggleRadio() {
  const targetEndpoint = isPlaying ? '/radio/stop' : '/radio/start';
  try {
    const res = await fetch(targetEndpoint);
    const body = await res.text();
    showToast(isPlaying ? 'Radyo durduruldu.' : 'Radyo başlatıldı!');
    fetchStatus();
  } catch (err) {
    showToast('İstek başarısız oldu: ' + err.message);
  }
}

async function updateVolume(val) {
  volumeValue.textContent = val + '%';
  try {
    await fetch(`/radio/volume?level=${val}`);
  } catch (err) {
    console.debug('Ses seviyesi değiştirilemedi:', err);
  }
}

async function reconnectBluetooth() {
  showToast('Bluetooth bağlantısı başlatılıyor...');
  try {
    const res = await fetch('/radio/bluetooth/reconnect');
    const data = await res.json();
    if (data.is_connected) {
      showToast('Bluetooth başarıyla bağlandı!');
    } else {
      showToast('Bağlantı denendi: ' + data.message);
    }
    fetchStatus();
  } catch (err) {
    showToast('Bağlantı isteği hatası: ' + err.message);
  }
}

// ==========================================
// TEST ENDPOINT IN UI
// ==========================================
async function testEndpoint(endpoint) {
  const resultBox = document.getElementById('endpointResultBox');
  const resultTitle = document.getElementById('resultEndpointTitle');
  const resultBadge = document.getElementById('resultStatusBadge');
  const resultBody = document.getElementById('resultBodyCode');

  resultTitle.textContent = `İstek: GET ${endpoint}`;
  try {
    const res = await fetch(endpoint);
    const text = await res.text();

    resultBadge.textContent = `${res.status} ${res.statusText || ''}`;
    if (res.status === 200) {
      resultBadge.className = 'badge';
    } else {
      resultBadge.className = 'badge err';
    }
    resultBody.textContent = text;
    resultBox.classList.remove('hidden');

    fetchStatus();
  } catch (err) {
    resultBadge.textContent = 'HATA';
    resultBadge.className = 'badge err';
    resultBody.textContent = err.message;
    resultBox.classList.remove('hidden');
  }
}

function closeResultBox() {
  document.getElementById('endpointResultBox').classList.add('hidden');
}

// ==========================================
// COPY HELPERS
// ==========================================
function copyEndpointCurl(endpoint) {
  const host = window.location.host;
  let curlCmd = `curl -i http://${host}${endpoint}`;
  copyToClipboard(curlCmd, `cURL komutu kopyalandı!`);
}

function copyToClipboard(text, successMsg) {
  navigator.clipboard.writeText(text).then(() => {
    showToast(successMsg);
  }).catch(() => {
    showToast('Kopyalama başarısız oldu.');
  });
}

function showToast(msg) {
  toastMessage.textContent = msg;
  toastNotification.classList.remove('hidden');
  setTimeout(() => {
    toastNotification.classList.add('hidden');
  }, 2600);
}

// ==========================================
// LOGS POLLING
// ==========================================
async function fetchLogs() {
  try {
    const res = await fetch('/api/logs');
    if (!res.ok) return;
    const logs = await res.json();
    if (!logs || logs.length === 0) return;

    logsContainer.innerHTML = '';
    logs.slice(-30).forEach(entry => {
      const row = document.createElement('div');
      row.className = `log-entry ${entry.level}`;
      row.innerHTML = `
        <span class="log-time">[${entry.time}]</span>
        <span class="log-msg">${escapeHtml(entry.message)}</span>
      `;
      logsContainer.appendChild(row);
    });
    logsContainer.scrollTop = logsContainer.scrollHeight;
  } catch (err) {
    console.debug('Log çekme hatası:', err);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/[&<>"']/g, function(m) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m];
  });
}

// ==========================================
// INITIALIZATION
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
  initVisualizer();
  fetchStatus();
  fetchLogs();

  // Polling intervals
  setInterval(fetchStatus, 2500);
  setInterval(fetchLogs, 3500);
});

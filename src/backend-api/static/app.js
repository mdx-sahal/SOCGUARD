const API_BASE = 'http://localhost:8000/api';
const WS_URL = 'ws://localhost:8000/ws/live-threats';

const alertList = document.getElementById('alert-list');
const wsStatus = document.getElementById('ws-status');
const totalAlertsEl = document.getElementById('total-alerts');
const highSeverityEl = document.getElementById('high-severity');


// Modal Elements
const modal = document.getElementById('detail-modal');
const closeModal = document.querySelector('.close-modal');
const modalTitle = document.getElementById('modal-title');
const modalId = document.getElementById('modal-id');
const modalTimestamp = document.getElementById('modal-timestamp');
const modalPlatform = document.getElementById('modal-platform');
const modalAuthor = document.getElementById('modal-author');
const modalSeverity = document.getElementById('modal-severity');
const modalReasoning = document.getElementById('modal-reasoning');
const modalContent = document.getElementById('modal-content-preview');

// State
let alertsData = [];
let currentView = 'global';


// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Auth Check
    const token = localStorage.getItem('socguard_token');
    if (!token && !window.location.pathname.includes('login')) {
        window.location.href = '/login';
        return;
    }

    // Logout Functionality
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            localStorage.removeItem('socguard_token');
            window.location.href = '/login';
        });
    }

    // Clear Logs Functionality
    const clearBtn = document.getElementById('clear-logs-btn');
    if (clearBtn) {
        clearBtn.addEventListener('click', async () => {
            if (confirm('Are you sure you want to clear ALL logs? This cannot be undone.')) {
                try {
                    const response = await fetch(`${API_BASE}/alerts`, { method: 'DELETE' });
                    const result = await response.json();
                    if (result.status === 'success') {
                        // Reset UI
                        alertsData = [];
                        renderAlerts([]);
                        updateBadges([]);
                        totalAlertsEl.textContent = '0';
                        highSeverityEl.textContent = '0';
                        alert('Logs cleared successfully.');
                    } else {
                        alert('Error clearing logs: ' + result.message);
                    }
                } catch (error) {
                    console.error('Error clearing logs:', error);
                    alert('Failed to connect to backend.');
                }
            }
        });
    }

    fetchAlerts();
    fetchStats();
    connectWebSocket();
});

// Fetch Initial Alerts
async function fetchAlerts() {
    try {
        const response = await fetch(`${API_BASE}/alerts?limit=50`);
        const data = await response.json();
        alertsData = data;
        updateBadges(data);
        renderAlerts(data);
    } catch (error) {
        console.error('Error fetching alerts:', error);
    }
}

// Fetch Stats
async function fetchStats() {
    try {
        const response = await fetch(`${API_BASE}/stats`);
        const data = await response.json();

        totalAlertsEl.textContent = data.total_alerts;

        if (data.high_severity_alerts !== undefined) {
            highSeverityEl.textContent = data.high_severity_alerts;
        } else {
            // Fallback if backend not updated yet
            const highSevCount = alertsData.filter(a => a.severity_score > 80).length;
            highSeverityEl.textContent = highSevCount;
        }





    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

// Update Badges
function updateBadges(alerts) {
    const counts = {
        telegram: 0,
        bluesky: 0,
        email: 0
    };

    alerts.forEach(a => {
        const p = (a.platform || '').toLowerCase().trim();
        if (p.includes('telegram')) counts.telegram++;
        else if (p.includes('bluesky')) counts.bluesky++;
        else if (p.includes('email')) counts.email++;
    });

    // Debugging
    console.log('Updated Badges:', counts);

    const telegramBadge = document.getElementById('badge-telegram');
    const blueskyBadge = document.getElementById('badge-bluesky');
    const emailBadge = document.getElementById('badge-email');

    if (telegramBadge) telegramBadge.textContent = counts.telegram;
    if (blueskyBadge) blueskyBadge.textContent = counts.bluesky;
    if (emailBadge) emailBadge.textContent = counts.email;
}


// Switch View
window.switchView = (view) => {
    currentView = view;

    // Update Sidebar Active State
    document.querySelectorAll('.sidebar nav li').forEach(li => li.classList.remove('active'));
    document.getElementById(`nav-${view}`).classList.add('active');

    // Update Feed Title
    const titles = {
        'global': '<i class="fa-solid fa-earth-americas"></i> Global Feed',
        'telegram': '<i class="fa-brands fa-telegram"></i> Telegram Feed',
        'bluesky': '<i class="fa-solid fa-cloud"></i> Bluesky Feed',
        'email': '<i class="fa-solid fa-envelope"></i> Email Feed'
    };
    document.getElementById('feed-title').innerHTML = titles[view] || 'Feed';


    renderAlerts(alertsData);
};


// WebSocket Connection
function connectWebSocket() {
    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        wsStatus.textContent = 'ACTIVE';
        wsStatus.className = 'status-value active';
        console.log('WebSocket Connected');
    };

    ws.onmessage = (event) => {
        const alert = JSON.parse(event.data);
        addAlertToFeed(alert);
        updateStatsUI(alert);
        updateBadges(alertsData); // Recalculate badges with new alert

    };

    ws.onclose = () => {
        wsStatus.textContent = 'INACTIVE';
        wsStatus.className = 'status-value inactive';
        console.log('WebSocket Disconnected. Reconnecting in 5s...');
        setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = (error) => {
        console.error('WebSocket Error:', error);
        ws.close();
    };
}

// Render Alerts based on current view
function renderAlerts(alerts) {
    alertList.innerHTML = '';

    const filtered = alerts.filter(a => {
        if (currentView === 'global') return true;
        const p = (a.platform || '').toLowerCase();
        if (currentView === 'twitter') return p.includes('twitter') || p.includes('x');
        return p.includes(currentView);
    });

    filtered.forEach(alert => {
        const row = createAlertRow(alert);
        alertList.appendChild(row);
    });
}

// Add Single Alert to Feed
function addAlertToFeed(alert) {
    // Add to local data
    alertsData.unshift(alert);

    // Only add to DOM if it matches current view
    let shouldShow = false;
    if (currentView === 'global') shouldShow = true;
    else {
        const p = (alert.platform || '').toLowerCase();
        if (currentView === 'twitter' && (p.includes('twitter') || p.includes('x'))) shouldShow = true;
        else if (p.includes(currentView)) shouldShow = true;
    }

    if (shouldShow) {
        const row = createAlertRow(alert);
        row.classList.add('new-alert');
        alertList.insertBefore(row, alertList.firstChild);

        // Keep list size manageable
        if (alertList.children.length > 50) {
            alertList.removeChild(alertList.lastChild);
        }
    }
}

// Create HTML Row
function createAlertRow(alert) {
    const tr = document.createElement('tr');

    const date = new Date(alert.timestamp).toLocaleString();
    const severityClass = getSeverityClass(alert.severity_score, alert.threat_category);
    const platformIcon = getPlatformIcon(alert.platform);

    tr.innerHTML = `
        <td>${date}</td>
        <td><i class="fa-brands fa-${platformIcon}"></i> ${alert.platform}</td>
        <td>${alert.threat_category}</td>
        <td><span class="score-badge ${severityClass}">${alert.severity_score.toFixed(1)}</span></td>
        <td>${alert.is_resolved ? '<span style="color:var(--accent-green)">Resolved</span>' : '<span style="color:var(--accent-red)">Active</span>'}</td>
        <td><button class="view-btn"><i class="fa-solid fa-eye"></i> View</button></td>
    `;

    // Add click event for the whole row for better UX
    tr.addEventListener('click', (e) => {
        e.stopPropagation();
        openModal(alert);
    });

    const btn = tr.querySelector('.view-btn');
    if (btn) {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            openModal(alert);
        });
    }

    return tr;
}

// Helpers
function getSeverityClass(score, category) {
    if (category && category === 'Suspected Deepfake Image') return 'warning';
    if (score > 80) return 'critical';
    if (score > 50) return 'warning';
    return 'info';
}

function getPlatformIcon(platform) {
    if (!platform) return 'globe';
    platform = platform.toLowerCase();
    if (platform.includes('twitter') || platform.includes('x')) return 'twitter';
    if (platform.includes('facebook')) return 'facebook';
    if (platform.includes('instagram')) return 'instagram';
    if (platform.includes('reddit')) return 'reddit';
    if (platform.includes('telegram')) return 'telegram';
    if (platform.includes('youtube')) return 'youtube';
    if (platform.includes('bluesky')) return 'bluesky';
    if (platform.includes('email')) return 'envelope';
    return 'globe'; // default
}


function updateStatsUI(newAlert) {
    // Increment total alerts
    let currentTotal = parseInt(totalAlertsEl.textContent) || 0;
    totalAlertsEl.textContent = currentTotal + 1;

    // Update high severity if needed
    if (newAlert.severity_score > 80) {
        let currentHigh = parseInt(highSeverityEl.textContent) || 0;
        highSeverityEl.textContent = currentHigh + 1;
    }
}

// Sidebar Navigation Logic is handled by inline onclicks calling switchView()


// Modal Logic
window.openModal = (alert) => {
    if (!alert) return;

    // Truncate long IDs for display
    const rawId = alert.id || alert.content_id || 'N/A';
    modalId.textContent = rawId.length > 50 ? rawId.substring(0, 20) + '...' + rawId.substring(rawId.length - 10) : rawId;
    modalId.title = rawId; // Show full ID on hover

    modalTimestamp.textContent = new Date(alert.timestamp).toLocaleString();
    modalPlatform.textContent = alert.platform;
    modalAuthor.textContent = alert.author || 'Anonymous';
    modalSeverity.textContent = alert.severity_score.toFixed(1);
    modalSeverity.className = `score-badge ${getSeverityClass(alert.severity_score, alert.threat_category)}`;

    modalReasoning.textContent = alert.reasoning || 'No analysis provided.';

    // Content Preview
    let contentHtml = '';

    // Removed Source Link button as requested

    // Add Text/Image content
    // Check both potential fields for image/audio URL
    const urlToShow = alert.image_url || alert.original_url;

    const isAudio = urlToShow && (urlToShow.match(/\.(mp3|wav|ogg|oga|m4a)$/i) || urlToShow.includes('voice') || urlToShow.includes('audio'));
    const isImage = alert.content_type === 'image' || (urlToShow && (urlToShow.match(/\.(jpg|jpeg|png|gif|webp)$/i) || (urlToShow.includes('api.telegram.org/file') && !isAudio)));

    if (isAudio) {
        contentHtml += `<div class="audio-preview"><audio controls src="${urlToShow}" style="width: 100%; margin-top: 10px;"></audio></div>`;
        if (alert.original_text) {
            contentHtml += `<p class="media-label" style="margin-top:10px; color:var(--text-primary); border-top:1px solid var(--border-color); padding-top:10px;">${alert.original_text}</p>`;
        }
    } else if (isImage) {
        contentHtml += `<img src="${urlToShow}" class="preview-img" alt="Content">`;
        if (alert.original_text) {
            contentHtml += `<p class="media-label" style="margin-top:10px; color:var(--text-primary); border-top:1px solid var(--border-color); padding-top:10px;">${alert.original_text}</p>`;
        }
    } else {
        // Text Content
        contentHtml += `<div class="content-text" style="white-space: pre-wrap; font-family: 'Inter', sans-serif;">${alert.original_text || 'No content text.'}</div>`;
        if (urlToShow) {
            contentHtml += `<p style="margin-top:10px;"><a href="${urlToShow}" target="_blank" style="color:var(--accent-blue)"><i class="fa-solid fa-arrow-up-right-from-square"></i> External Link</a></p>`;
        }
    }

    modalContent.innerHTML = contentHtml;



    // XAI Logic
    const xaiSection = document.getElementById('xai-section');
    const xaiPreview = document.getElementById('modal-xai-preview');

    if (alert.explanation_image) {
        xaiSection.style.display = 'block';
        xaiPreview.innerHTML = `
            <img src="${alert.explanation_image}" class="xai-img" alt="AI Explanation">
            <p class="xai-caption">Highlighted areas indicating threat regions.</p>
        `;
    } else {
        xaiSection.style.display = 'none';
        xaiPreview.innerHTML = '';
    }

    modal.classList.remove('hidden');
};

closeModal.addEventListener('click', () => {
    modal.classList.add('hidden');
});

window.addEventListener('click', (e) => {
    if (e.target === modal) {
        modal.classList.add('hidden');
    }
});

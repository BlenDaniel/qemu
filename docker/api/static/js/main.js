// Main Dashboard JavaScript
const API_BASE = window.location.origin;

// Auto-refresh emulators every 30 seconds
let autoRefreshInterval;

function logMessage(containerId, message, type = 'info') {
    const container = document.getElementById(containerId);
    container.classList.remove('hidden');

    const logLine = document.createElement('div');
    logLine.className = `log-line log-${type}`;

    const timestamp = new Date().toLocaleTimeString();
    const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : type === 'warning' ? '⚠️' : 'ℹ️';

    logLine.innerHTML = `<span style="color: #888">[${timestamp}]</span> ${icon} ${message}`;
    container.appendChild(logLine);
    container.scrollTop = container.scrollHeight;
}

function clearLog(containerId) {
    const container = document.getElementById(containerId);
    container.innerHTML = '';
    container.classList.add('hidden');
}

// Create Emulator Form Handler
function initializeCreateEmulatorForm() {
    document.getElementById('createEmulatorForm').addEventListener('submit', async function (e) {
        e.preventDefault();

        const createBtn = document.getElementById('createBtn');
        const originalText = createBtn.textContent;

        createBtn.disabled = true;
        createBtn.innerHTML = '<div class="loading-spinner"></div>Creating...';

        clearLog('creationLog');
        logMessage('creationLog', 'Starting emulator creation process...', 'info');

        const formData = new FormData(e.target);
        const data = {
            android_version: formData.get('androidVersion'),
            map_adb_server: formData.get('mapAdbServer') === 'true'
        };

        logMessage('creationLog', `Selected Android ${data.android_version} with ADB server mapping: ${data.map_adb_server}`, 'info');

        try {
            logMessage('creationLog', 'Sending request to API...', 'info');

            const response = await fetch(`${API_BASE}/api/emulators`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                const result = await response.json();

                logMessage('creationLog', `✅ Emulator created successfully!`, 'success');
                logMessage('creationLog', `📱 Device ID: ${result.device_id}`, 'success');
                logMessage('creationLog', `🤖 Android Version: ${result.android_version}`, 'success');
                logMessage('creationLog', `🔌 ADB Port: ${result.ports.adb}`, 'success');
                logMessage('creationLog', `🖥️ ADB Server Port: ${result.ports.adb_server}`, 'success');
                logMessage('creationLog', `📟 Console Port: ${result.ports.console}`, 'success');

                if (result.adb_setup) {
                    logMessage('creationLog', '🔧 ADB Setup Commands:', 'info');
                    logMessage('creationLog', `Windows: $env:ANDROID_ADB_SERVER_PORT = "${result.ports.adb_server}"`, 'info');
                    logMessage('creationLog', `Unix/Mac: export ANDROID_ADB_SERVER_PORT=${result.ports.adb_server}`, 'info');
                    logMessage('creationLog', `Connect: adb connect localhost:${result.ports.adb}`, 'info');

                    if (result.adb_setup.final_device_status === 'device') {
                        logMessage('creationLog', '🎉 Emulator is ready and connected!', 'success');
                    } else {
                        logMessage('creationLog', '⚠️ Emulator created but may still be starting up...', 'warning');
                    }
                }

                // Auto-refresh the emulators list
                setTimeout(refreshEmulators, 2000);
            } else {
                const error = await response.text();
                logMessage('creationLog', `Failed to create emulator: ${error}`, 'error');
            }
        } catch (error) {
            logMessage('creationLog', `Error: ${error.message}`, 'error');
        } finally {
            createBtn.disabled = false;
            createBtn.textContent = originalText;
        }
    });
}

// ADB Functions
async function listAdbDevices() {
    const port = document.getElementById('adbServerPort').value || '5037';

    clearLog('adbOutput');
    logMessage('adbOutput', `Listing devices on ADB server port ${port}...`, 'info');

    try {
        const response = await fetch(`${API_BASE}/api/adb/devices?port=${port}`);
        const result = await response.json();

        if (result.success) {
            logMessage('adbOutput', 'Device list retrieved successfully:', 'success');
            const lines = result.output.split('\n');
            lines.forEach(line => {
                if (line.trim()) {
                    logMessage('adbOutput', line, 'info');
                }
            });
        } else {
            logMessage('adbOutput', `Error: ${result.output}`, 'error');
        }
    } catch (error) {
        logMessage('adbOutput', `Error: ${error.message}`, 'error');
    }
}

async function connectAdbDevice() {
    const adbPort = document.getElementById('adbDevicePort').value;
    const serverPort = document.getElementById('adbServerPort').value || '5037';

    if (!adbPort) {
        logMessage('adbOutput', 'Please enter a device port', 'error');
        return;
    }

    clearLog('adbOutput');
    logMessage('adbOutput', `Connecting to device on port ${adbPort} via ADB server ${serverPort}...`, 'info');

    try {
        const response = await fetch(`${API_BASE}/api/adb/connect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                adb_port: adbPort,
                adb_server_port: serverPort
            })
        });

        const result = await response.json();

        if (result.success) {
            logMessage('adbOutput', 'Device connected successfully!', 'success');
            logMessage('adbOutput', result.output, 'info');
        } else {
            logMessage('adbOutput', `Connection failed: ${result.output}`, 'error');
        }
    } catch (error) {
        logMessage('adbOutput', `Error: ${error.message}`, 'error');
    }
}

// Emulator Management
async function refreshEmulators() {
    const emulatorsList = document.getElementById('emulatorsList');
    emulatorsList.innerHTML = '<p>🔄 Loading emulators...</p>';

    try {
        const response = await fetch(`${API_BASE}/api/emulators`);
        const emulators = await response.json();

        if (Object.keys(emulators).length === 0) {
            emulatorsList.innerHTML = '<p>No emulators are currently running.</p>';
            return;
        }

        emulatorsList.innerHTML = '';

        for (const [id, emulator] of Object.entries(emulators)) {
            const card = createEmulatorCard(id, emulator);
            emulatorsList.appendChild(card);
        }
    } catch (error) {
        emulatorsList.innerHTML = `<p>Error loading emulators: ${error.message}</p>`;
    }
}

function createEmulatorCard(id, emulator) {
    const card = document.createElement('div');
    card.className = 'emulator-card';

    const statusClass = emulator.status === 'running' ? 'status-running' : 'status-stopped';

    card.innerHTML = `
        <div class="emulator-header">
            <div class="emulator-id">📱 ${emulator.device_id}</div>
            <div class="status-badge ${statusClass}">${emulator.status}</div>
        </div>
        
        <div class="emulator-details">
            <div class="detail-item">
                <span class="detail-label">Android Version:</span>
                <span class="detail-value">Android ${emulator.android_version}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">ADB Port:</span>
                <span class="detail-value">${emulator.ports.adb}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">ADB Server:</span>
                <span class="detail-value">${emulator.ports.adb_server}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Console:</span>
                <span class="detail-value">${emulator.ports.console}</span>
            </div>
        </div>
        
        <div style="display: flex; gap: 10px; margin-top: 15px;">
            <button onclick="deleteEmulator('${id}')" class="btn-danger" style="flex: 1;">🗑️ Delete</button>
            <button onclick="openLiveView('${id}')" class="btn-info" style="flex: 1;">📺 Live View</button>
            <button onclick="connectToEmulator('${emulator.ports.adb}', '${emulator.ports.adb_server}')" class="btn-info" style="flex: 1;">🔌 Connect ADB</button>
        </div>
        
        ${emulator.adb_commands ? `
        <div class="adb-commands">
            <div class="command-section">
                <span class="command-label">Windows:</span>
                <span class="command-value">$env:ANDROID_ADB_SERVER_PORT = "${emulator.ports.adb_server}"</span>
            </div>
            <div class="command-section">
                <span class="command-label">Unix/Mac:</span>
                <span class="command-value">export ANDROID_ADB_SERVER_PORT=${emulator.ports.adb_server}</span>
            </div>
            <div class="command-section">
                <span class="command-label">Connect:</span>
                <span class="command-value">adb connect localhost:${emulator.ports.adb}</span>
            </div>
            <div class="command-section">
                <span class="command-label">Console:</span>
                <span class="command-value">telnet localhost ${emulator.ports.console}</span>
            </div>
        </div>
        ` : ''}
    `;

    return card;
}

async function deleteEmulator(id) {
    if (!confirm('Are you sure you want to delete this emulator?')) return;

    try {
        const response = await fetch(`${API_BASE}/api/emulators/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            refreshEmulators();
        } else {
            alert('Failed to delete emulator');
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

async function connectToEmulator(adbPort, serverPort) {
    document.getElementById('adbDevicePort').value = adbPort;
    document.getElementById('adbServerPort').value = serverPort;
    await connectAdbDevice();
}

function openLiveView(emulatorId) {
    // Open noVNC live view in a new window/tab
    window.open(`${API_BASE}/api/emulators/${emulatorId}/live_view`, '_blank');
}

// Initialize
document.addEventListener('DOMContentLoaded', function () {
    initializeCreateEmulatorForm();
    refreshEmulators();

    // Set up auto-refresh
    autoRefreshInterval = setInterval(refreshEmulators, 30000);
});

// Cleanup on page unload
window.addEventListener('beforeunload', function () {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
}); 
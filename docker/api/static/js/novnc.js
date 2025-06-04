// noVNC Viewer JavaScript
function initNoVNCViewer(emulatorId, wsPort) {
    const statusIndicator = document.getElementById('statusIndicator');
    const statusText = document.getElementById('statusText');
    const vncContainer = document.getElementById('vncContainer');
    const loadingMessage = document.getElementById('loadingMessage');
    const connectionInfo = document.getElementById('connectionInfo');

    let vncIframe = null;
    let connectionAttempts = 0;
    const maxRetries = 5;

    function updateStatus(status, message) {
        statusText.textContent = message;

        if (status === 'connected') {
            statusIndicator.classList.add('connected');
        } else {
            statusIndicator.classList.remove('connected');
        }
    }

    function connectVNC() {
        connectionAttempts++;
        updateStatus('connecting', `Connecting... (${connectionAttempts}/${maxRetries})`);

        // Remove existing iframe if any
        if (vncIframe) {
            vncIframe.remove();
            vncIframe = null;
        }

        // Create new iframe for noVNC
        vncIframe = document.createElement('iframe');
        vncIframe.className = 'vnc-iframe';
        vncIframe.id = 'vncFrame';

        // Construct noVNC URL - use the host-accessible websockify port
        // The container's websockify is already running and mapped to the host
        const novncUrl = `http://${window.location.hostname}:${wsPort}/vnc.html?host=${window.location.hostname}&port=${wsPort}&autoconnect=true&resize=scale&quality=6`;

        vncIframe.onload = function () {
            loadingMessage.style.display = 'none';
            connectionInfo.style.display = 'block';
            updateStatus('connected', 'Connected to emulator');
        };

        vncIframe.onerror = function () {
            handleConnectionError();
        };

        // Set the source to start loading
        vncIframe.src = novncUrl;

        // Add iframe to container
        vncContainer.appendChild(vncIframe);

        // Wait for timeout before giving up completely
        setTimeout(() => {
            if (connectionAttempts < maxRetries) {
                updateStatus('retrying', `Retrying... (${connectionAttempts}/${maxRetries})`);
                connectVNC();
            } else {
                updateStatus('failed', 'Connection failed. Try refreshing or waking the emulator.');
                loadingMessage.style.display = 'block';
                loadingMessage.innerHTML = `
                    <div class="error-message">
                        <h3>Connection Failed</h3>
                        <p>Unable to connect to the Android emulator screen.</p>
                        <p><strong>Try this:</strong></p>
                        <ol>
                            <li>Click the "⚡ Wake Screen" button above</li>
                            <li>Wait a few seconds and click "🔄 Reconnect"</li>
                            <li>Make sure the emulator container is running</li>
                        </ol>
                        <button onclick="wakeEmulator()" class="btn btn-warning">⚡ Wake Emulator</button>
                        <button onclick="window.location.reload()" class="btn btn-primary">🔄 Refresh Page</button>
                    </div>
                `;
            }
        }, 2000);
    }

    function handleConnectionError() {
        loadingMessage.innerHTML = `
            <div class="error-message">
                <h3>❌ Connection Failed</h3>
                <p>Unable to connect to the Android emulator screen.</p>
                <p>Attempts: ${connectionAttempts}/${maxRetries}</p>
                <button class="btn btn-primary" onclick="reconnectVNC()">🔄 Try Again</button>
                <button class="btn btn-danger" onclick="window.close()">❌ Close</button>
            </div>
        `;
        loadingMessage.style.display = 'block';
        connectionInfo.style.display = 'none';
        updateStatus('error', 'Connection failed');
    }

    window.reconnectVNC = function() {
        connectionAttempts = 0;
        loadingMessage.innerHTML = `
            <div class="loading-spinner"></div>
            <p>Reconnecting to Android emulator...</p>
            <p>Starting noVNC session...</p>
        `;
        loadingMessage.style.display = 'block';
        connectionInfo.style.display = 'none';
        connectVNC();
    };

    window.toggleFullscreen = function() {
        const vncContainer = document.getElementById('vncContainer');
        
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else {
            vncContainer.requestFullscreen();
        }
    };

    // Handle fullscreen changes
    document.addEventListener('fullscreenchange', function () {
        const header = document.querySelector('.header');
        if (document.fullscreenElement) {
            header.style.display = 'none';
            vncContainer.style.top = '0';
        } else {
            header.style.display = 'flex';
            vncContainer.style.top = '60px';
        }
    });

    // Handle page visibility changes
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible' && statusText.textContent.includes('failed')) {
            // Page became visible and we had a connection failure, try to reconnect
            setTimeout(window.reconnectVNC, 1000);
        }
    });

    // Start initial connection
    connectVNC();
}

// Add wake emulator function
function wakeEmulator() {
    // Get emulator ID from global variable set in the HTML template
    const emulatorId = window.currentEmulatorId;
    
    if (!emulatorId) {
        alert('Emulator ID not found');
        return;
    }
    
    fetch(`/api/emulators/${emulatorId}/wake`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('Emulator wake commands sent:', data);
            alert('Wake commands sent to emulator! Wait a few seconds then click Reconnect.');
        } else {
            console.error('Wake emulator failed:', data);
            alert('Failed to wake emulator: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error waking emulator:', error);
        alert('Error sending wake commands: ' + error.message);
    });
} 
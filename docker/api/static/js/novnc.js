// noVNC Viewer JavaScript
function initNoVNCViewer(emulatorId, wsPort) {
    const statusIndicator = document.getElementById('statusIndicator');
    const statusText = document.getElementById('statusText');
    const vncContainer = document.getElementById('vncContainer');
    const loadingMessage = document.getElementById('loadingMessage');
    const connectionInfo = document.getElementById('connectionInfo');
    const debugInfo = document.getElementById('debugInfo');

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

    function updateDebugInfo(info) {
        if (debugInfo) {
            debugInfo.innerHTML = `<strong>Debug:</strong> ${info}`;
        }
    }

    // Test if websockify is accessible
    function testWebsockifyConnection() {
        return fetch(`http://localhost:${wsPort}/vnc.html`, {
            method: 'HEAD',
            mode: 'no-cors'
        }).then(() => true).catch(() => false);
    }

    // Alternative connection method using proxy
    function connectViaProxy() {
        updateStatus('connecting', 'Trying proxy connection...');
        updateDebugInfo('Using API proxy method');

        // Remove existing iframe if any
        if (vncIframe) {
            vncIframe.remove();
            vncIframe = null;
        }

        // Create new iframe for proxied noVNC
        vncIframe = document.createElement('iframe');
        vncIframe.className = 'vnc-iframe';
        vncIframe.id = 'vncFrame';

        // Use the proxy endpoint to avoid CORS issues
        const proxyUrl = `/api/emulators/${emulatorId}/vnc/proxy`;

        vncIframe.onload = function () {
            loadingMessage.style.display = 'none';
            connectionInfo.style.display = 'block';
            updateStatus('connected', 'Connected via proxy');
            updateDebugInfo('Proxy connection successful');
        };

        vncIframe.onerror = function () {
            updateDebugInfo('Proxy connection failed');
            handleConnectionError();
        };

        // Set the source to start loading
        vncIframe.src = proxyUrl;

        // Add iframe to container
        vncContainer.appendChild(vncIframe);
    }

    // Direct connection method
    function connectDirect() {
        updateStatus('connecting', `Direct connection attempt ${connectionAttempts + 1}/${maxRetries}...`);
        updateDebugInfo(`Trying direct connection to localhost:${wsPort}`);

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
        const novncUrl = `http://localhost:${wsPort}/vnc.html?host=localhost&port=${wsPort}&autoconnect=true&resize=scale&quality=6&compress=2`;

        let frameLoaded = false;
        vncIframe.onload = function () {
            frameLoaded = true;
            setTimeout(() => {
                if (frameLoaded) {
                    loadingMessage.style.display = 'none';
                    connectionInfo.style.display = 'block';
                    updateStatus('connected', 'Connected directly');
                    updateDebugInfo('Direct connection successful');
                }
            }, 2000); // Give noVNC time to establish WebSocket connection
        };

        vncIframe.onerror = function () {
            frameLoaded = false;
            updateDebugInfo('Direct connection iframe failed');
            setTimeout(tryAlternativeConnection, 1000);
        };

        // Set the source to start loading
        vncIframe.src = novncUrl;

        // Add iframe to container
        vncContainer.appendChild(vncIframe);

        // Timeout for this attempt
        setTimeout(() => {
            if (!frameLoaded) {
                updateDebugInfo('Direct connection timeout');
                tryAlternativeConnection();
            }
        }, 5000);
    }

    function tryAlternativeConnection() {
        connectionAttempts++;
        
        if (connectionAttempts >= maxRetries) {
            handleConnectionError();
            return;
        }

        // Try proxy method after direct methods fail
        if (connectionAttempts === 2) {
            connectViaProxy();
        } else {
            // Keep trying direct connection
            setTimeout(connectDirect, 2000);
        }
    }

    function connectVNC() {
        connectionAttempts = 0;
        updateStatus('connecting', 'Initializing connection...');
        updateDebugInfo('Starting connection process');
        
        // Test if websockify is accessible first
        testWebsockifyConnection().then(accessible => {
            if (accessible) {
                updateDebugInfo('Websockify accessible, trying direct connection');
                connectDirect();
            } else {
                updateDebugInfo('Websockify not accessible, trying proxy');
                connectViaProxy();
            }
        }).catch(() => {
            updateDebugInfo('Connection test failed, trying direct anyway');
            connectDirect();
        });
    }

    function handleConnectionError() {
        loadingMessage.innerHTML = `
            <div class="error-message">
                <h3>❌ Connection Failed</h3>
                <p>Unable to connect to the Android emulator screen after ${connectionAttempts} attempts.</p>
                <p><strong>Troubleshooting steps:</strong></p>
                <ol>
                    <li>Click "🔧 Test Connection" to check the status</li>
                    <li>Click "⚡ Wake Screen" to wake up the emulator</li>
                    <li>Try "📺 Direct noVNC" for a direct connection</li>
                    <li>Wait a few seconds and click "🔄 Reconnect"</li>
                </ol>
                <div style="margin-top: 15px;">
                    <button class="btn btn-primary" onclick="reconnectVNC()">🔄 Try Again</button>
                    <button class="btn btn-warning" onclick="wakeEmulator()">⚡ Wake Emulator</button>
                    <button class="btn btn-info" onclick="testConnection()">🔧 Test Connection</button>
                    <button class="btn btn-secondary" onclick="openDirectNoVNC()">📺 Direct noVNC</button>
                </div>
                <div style="margin-top: 10px; font-size: 12px; color: #666;">
                    WebSocket Port: ${wsPort} | Attempts: ${connectionAttempts}/${maxRetries}
                </div>
            </div>
        `;
        loadingMessage.style.display = 'block';
        connectionInfo.style.display = 'none';
        updateStatus('error', 'Connection failed');
        updateDebugInfo(`All connection methods failed after ${connectionAttempts} attempts`);
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
        updateDebugInfo('User initiated reconnection');
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
            updateDebugInfo('Page became visible, attempting reconnection');
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
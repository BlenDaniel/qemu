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

        // Construct noVNC URL - websockify serves noVNC on the same port
        const novncUrl = `http://localhost:${wsPort}/vnc.html?host=localhost&port=${wsPort}&autoconnect=true&resize=scale&quality=6`;

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

        // Set a timeout to check connection
        setTimeout(() => {
            if (statusText.textContent.includes('Connecting')) {
                // Still connecting after timeout, might be an issue
                if (connectionAttempts < maxRetries) {
                    console.log('Connection timeout, retrying...');
                    setTimeout(connectVNC, 2000);
                } else {
                    handleConnectionError();
                }
            }
        }, 10000); // 10 second timeout
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
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(err => {
                console.log('Error attempting to enable fullscreen:', err);
            });
        } else {
            document.exitFullscreen();
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

    // Start connection when initialized
    setTimeout(connectVNC, 1000);
} 
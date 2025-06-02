import { API_ENDPOINTS } from './config.js';
import { showAlert } from './ui.js';

// Switch to a specific ADB server port
export function switchToAdbServer(port, callback) {
    // Kill existing ADB server first
    fetch(API_ENDPOINTS.killServer, {
        method: 'POST'
    })
        .then(response => response.json())
        .then(() => {
            // Start new ADB server with specific port
            fetch(API_ENDPOINTS.startServer, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    port: port
                }),
            })
                .then(response => response.json())
                .then(() => {
                    console.log(`Switched to ADB server port: ${port}`);
                    if (callback) {
                        callback();
                    }
                })
                .catch(error => {
                    console.error('Error starting ADB server:', error);
                    if (callback) {
                        callback();
                    }
                });
        })
        .catch(error => {
            console.error('Error killing ADB server:', error);
            if (callback) {
                callback();
            }
        });
}

// Promise-based version of switchToAdbServer
export function switchToAdbServerPromise(port) {
    return new Promise((resolve, reject) => {
        // Kill existing ADB server first
        fetch(API_ENDPOINTS.killServer, {
            method: 'POST'
        })
            .then(response => response.json())
            .then(() => {
                // Start new ADB server with specific port
                fetch(API_ENDPOINTS.startServer, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        port: port
                    }),
                })
                    .then(response => response.json())
                    .then(data => {
                        console.log(`Switched to ADB server port: ${port}`);
                        resolve(data);
                    })
                    .catch(error => {
                        console.error('Error starting ADB server:', error);
                        reject(error);
                    });
            })
            .catch(error => {
                console.error('Error killing ADB server:', error);
                reject(error);
            });
    });
}

// Connect to a specific port
export function connectToPort(port, adbServerPort) {
    return fetch(API_ENDPOINTS.connect, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            adb_port: port,
            adb_server_port: adbServerPort
        }),
    })
        .then(response => response.json());
}

// Connect to an emulator with its specific ADB server
export function connectToEmulator(port, buttonElement, adbServerPort) {
    if (buttonElement) {
        buttonElement.disabled = true;
        buttonElement.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Connecting...';
    }
    
    // If no ADB server port provided, we can't properly set up environment
    if (!adbServerPort) {
        console.error('No ADB server port provided for connection');
        if (buttonElement) {
            buttonElement.disabled = false;
            buttonElement.innerHTML = 'Connect';
        }
        showAlert('danger', 'Connection failed: No ADB server port specified');
        return;
    }
    
    // Step 1: Kill existing ADB server
    fetch(API_ENDPOINTS.killServer, {
        method: 'POST'
    })
        .then(response => response.json())
        .then(() => {
            console.log('Killed existing ADB server');
            
            // Step 2: Start new server with the specified port
            return fetch(API_ENDPOINTS.startServer, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    port: adbServerPort
                }),
            });
        })
        .then(response => response.json())
        .then(serverResult => {
            console.log(`Started ADB server with port ${adbServerPort}:`, serverResult);
            
            // Step 3: Now connect to the device
            return fetch(API_ENDPOINTS.connect, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    adb_port: port,
                    adb_server_port: adbServerPort
                }),
            });
        })
        .then(response => response.json())
        .then(data => {
            if (buttonElement) {
                buttonElement.disabled = false;
                buttonElement.innerHTML = 'Connect';
            }
            
            if (data.success) {
                showAlert('success', `Connected to emulator: ${data.output}`);
                
                // Call the global loadDevices and checkAllDeviceStatuses
                // These will be properly bound in the main app
                if (window.loadDevices) window.loadDevices(adbServerPort);
                if (window.checkAllDeviceStatuses) {
                    setTimeout(() => {
                        window.checkAllDeviceStatuses();
                    }, 1000);
                }
            } else {
                showAlert('danger', `Failed to connect: ${data.error}`);
            }
        })
        .catch(error => {
            if (buttonElement) {
                buttonElement.disabled = false;
                buttonElement.innerHTML = 'Connect';
            }
            showAlert('danger', `Error: ${error.message}`);
        });
}

// Function to disconnect device
export function disconnectDevice(deviceId, buttonElement, adbServerPort) {
    if (buttonElement) {
        buttonElement.disabled = true;
        buttonElement.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Disconnecting...';
    }
    
    fetch(API_ENDPOINTS.disconnect, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            device: deviceId,
            adb_server_port: adbServerPort
        }),
    })
        .then(response => response.json())
        .then(data => {
            if (buttonElement) {
                buttonElement.disabled = false;
                buttonElement.innerHTML = 'Disconnect';
            }
            
            if (data.success) {
                showAlert('success', `Disconnected device: ${deviceId}`);
                
                // Call the global functions for updating UI
                if (window.loadDevices) window.loadDevices(adbServerPort);
                if (window.loadDevicesForSelect) window.loadDevicesForSelect(adbServerPort);
                
                // Update all device statuses
                if (window.checkAllDeviceStatuses) {
                    setTimeout(() => {
                        window.checkAllDeviceStatuses();
                    }, 1000);
                }
            } else {
                showAlert('danger', `Failed to disconnect: ${data.error}`);
            }
        })
        .catch(error => {
            if (buttonElement) {
                buttonElement.disabled = false;
                buttonElement.innerHTML = 'Disconnect';
            }
            showAlert('danger', `Error: ${error.message}`);
        });
}

// Function to check emulator status similar to the script's show_current_config
export function checkEmulatorStatus(adbServerPort, deviceId) {
    return new Promise((resolve, reject) => {
        // First check if the ADB server is running
        const url = adbServerPort ? `${API_ENDPOINTS.devices}?port=${adbServerPort}` : API_ENDPOINTS.devices;
        
        fetch(url)
            .then(response => response.json())
            .then(data => {
                // Initialize status object
                const status = {
                    serverRunning: false,
                    deviceConnected: false,
                    deviceStatus: null
                };
                
                // Check server status
                if (data.success && 
                    (data.output.includes('daemon started successfully') || 
                     data.output.includes('List of devices attached'))) {
                    status.serverRunning = true;
                    
                    // Check for connected devices
                    const lines = data.output.split('\n');
                    for (let i = 1; i < lines.length; i++) {
                        const line = lines[i].trim();
                        if (line && !line.startsWith('*')) {
                            const parts = line.split('\t');
                            const foundDeviceId = parts[0];
                            
                            if (foundDeviceId === deviceId) {
                                status.deviceConnected = true;
                                status.deviceStatus = parts[1] || 'unknown';
                                break;
                            }
                        }
                    }
                }
                
                resolve(status);
            })
            .catch(error => {
                console.error('Error checking emulator status:', error);
                reject(error);
            });
    });
} 
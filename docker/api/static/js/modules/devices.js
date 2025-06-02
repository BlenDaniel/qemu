import { API_ENDPOINTS } from './config.js';
import { getStatusClass, showAlert } from './ui.js';
import { switchToAdbServerPromise, checkEmulatorStatus } from './adb.js';

// Load connected devices
export function loadDevices(adbServerPort) {
    const url = adbServerPort ? `${API_ENDPOINTS.devices}?port=${adbServerPort}` : API_ENDPOINTS.devices;
    
    fetch(url)
        .then(response => response.json())
        .then(data => {
            const tableBody = document.getElementById('devices-table');
            tableBody.innerHTML = '';
            
            if (!data.success) {
                tableBody.innerHTML = `<tr><td colspan="3" class="text-center">Error: ${data.error || 'Failed to load devices'}</td></tr>`;
                return;
            }
            
            // Parse devices output
            const lines = data.output.split('\n');
            let deviceFound = false;
            
            for (let i = 1; i < lines.length; i++) {
                const line = lines[i].trim();
                if (line && !line.startsWith('*')) {
                    deviceFound = true;
                    const [deviceId, status] = line.split('\t');
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${deviceId}</td>
                        <td><span class="status-badge ${getStatusClass(status)}">${status}</span></td>
                        <td>
                            <button class="btn btn-sm btn-warning btn-action" onclick="window.disconnectDevice('${deviceId}', this, '${adbServerPort}')">Disconnect</button>
                        </td>
                    `;
                    tableBody.appendChild(row);
                }
            }
            
            if (!deviceFound) {
                tableBody.innerHTML = '<tr><td colspan="3" class="text-center">No devices connected</td></tr>';
            }
        })
        .catch(error => {
            showAlert('danger', `Error loading devices: ${error.message}`);
        });
}

// Load devices for select dropdown
export function loadDevicesForSelect(adbServerPort) {
    const url = adbServerPort ? `${API_ENDPOINTS.devices}?port=${adbServerPort}` : API_ENDPOINTS.devices;
    
    fetch(url)
        .then(response => response.json())
        .then(data => {
            const select = document.getElementById('device-select');
            select.innerHTML = '';
            
            if (!data.success) {
                select.innerHTML = '<option value="" disabled selected>Error loading devices</option>';
                return;
            }
            
            // Parse devices output
            const lines = data.output.split('\n');
            let deviceFound = false;
            
            for (let i = 1; i < lines.length; i++) {
                const line = lines[i].trim();
                if (line && !line.startsWith('*')) {
                    deviceFound = true;
                    const [deviceId, status] = line.split('\t');
                    const option = document.createElement('option');
                    option.value = deviceId;
                    option.textContent = `${deviceId} (${status})`;
                    select.appendChild(option);
                }
            }
            
            if (!deviceFound) {
                select.innerHTML = '<option value="" disabled selected>No devices connected</option>';
            }
        })
        .catch(error => {
            console.error('Error loading devices for select:', error);
            const select = document.getElementById('device-select');
            select.innerHTML = '<option value="" disabled selected>Error loading devices</option>';
        });
}

// Install an APK
export function installApk() {
    const deviceSelect = document.getElementById('device-select');
    const device = deviceSelect.value;
    const apkPath = document.getElementById('apk-path').value;
    const statusDiv = document.getElementById('installation-status');
    
    // Get the ADB server port associated with this device from the emulator data
    let adbServerPort = null;
    if (device && device.startsWith('localhost:')) {
        const devicePort = device.split(':')[1];
        
        // Try to find the emulator with this device port
        fetch(API_ENDPOINTS.emulators)
            .then(response => response.json())
            .then(data => {
                // Find matching emulator
                for (const [id, emulator] of Object.entries(data)) {
                    if (emulator.ports.adb === devicePort) {
                        adbServerPort = emulator.ports.adb_server;
                        break;
                    }
                }
                
                // Now proceed with install
                performInstall(device, apkPath, adbServerPort, statusDiv);
            })
            .catch(error => {
                console.error('Error getting emulator data for APK install:', error);
                // Fall back to install without specific ADB server port
                performInstall(device, apkPath, null, statusDiv);
            });
    } else {
        // No specific emulator, just install directly
        performInstall(device, apkPath, null, statusDiv);
    }
}

// Helper function to perform the actual APK installation
function performInstall(device, apkPath, adbServerPort, statusDiv) {
    if (!apkPath) {
        statusDiv.innerHTML = '<p class="card-text text-danger">Please enter an APK path</p>';
        return;
    }
    
    statusDiv.innerHTML = `
        <p class="card-text">Installing APK... Please wait.</p>
        <div class="progress mb-3">
            <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 50%"></div>
        </div>
    `;
    
    fetch(API_ENDPOINTS.install, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            device: device,
            apk_path: apkPath,
            adb_server_port: adbServerPort
        }),
    })
        .then(response => response.json())
        .then(data => {
            const progressBar = statusDiv.querySelector('.progress-bar');
            progressBar.style.width = '100%';
            progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
            
            if (data.success) {
                progressBar.classList.add('bg-success');
                statusDiv.innerHTML = `
                    <p class="card-text text-success">APK installed successfully!</p>
                    <div class="progress mb-3">
                        <div class="progress-bar bg-success" role="progressbar" style="width: 100%"></div>
                    </div>
                    <pre>${data.output}</pre>
                `;
                
                // Refresh device list
                if (window.loadDevices) window.loadDevices(adbServerPort);
                if (window.checkAllDeviceStatuses) window.checkAllDeviceStatuses();
            } else {
                progressBar.classList.add('bg-danger');
                statusDiv.innerHTML = `
                    <p class="card-text text-danger">Installation failed:</p>
                    <div class="progress mb-3">
                        <div class="progress-bar bg-danger" role="progressbar" style="width: 100%"></div>
                    </div>
                    <pre>${data.error}</pre>
                `;
            }
        })
        .catch(error => {
            statusDiv.innerHTML = `
                <p class="card-text text-danger">Error: ${error.message}</p>
                <div class="progress mb-3">
                    <div class="progress-bar bg-danger" role="progressbar" style="width: 100%"></div>
                </div>
            `;
        });
}

// Check status of all devices
export function checkAllDeviceStatuses() {
    console.log('Checking status of all emulators...');
    
    fetch(API_ENDPOINTS.emulators)
        .then(response => response.json())
        .then(data => {
            // Process each emulator one by one
            const emulators = Object.entries(data);
            
            // Use a Promise to chain checks so we handle one emulator at a time
            // This is critical because we need to set up a different ADB server for each emulator
            let checkPromise = Promise.resolve();
            
            emulators.forEach(([id, emulator]) => {
                checkPromise = checkPromise.then(() => {
                    console.log(`Checking emulator ${emulator.device_id}...`);
                    return checkSingleEmulatorStatus(id, emulator);
                });
            });
            
            // After checking all emulators, also update the device list
            checkPromise.then(() => {
                // Use the ADB server port from the first emulator if available
                const firstEmulator = emulators.length > 0 ? emulators[0][1] : null;
                if (firstEmulator && firstEmulator.ports && firstEmulator.ports.adb_server) {
                    loadDevices(firstEmulator.ports.adb_server);
                } else {
                    loadDevices();
                }
            });
            
            return checkPromise;
        })
        .catch(error => {
            console.error('Error checking all device statuses:', error);
        });
}

// Check the status of a single emulator by connecting to its ADB server first
function checkSingleEmulatorStatus(id, emulator) {
    const row = document.getElementById(`emulator-row-${id}`);
    if (!row) return Promise.resolve(); // Skip if row not found
    
    const statusBadge = row.querySelector('td:nth-child(3) .status-badge');
    if (!statusBadge) return Promise.resolve(); // Skip if status badge not found
    
    // First kill any existing ADB server
    return fetch(API_ENDPOINTS.killServer, {
        method: 'POST'
    })
        .then(response => response.json())
        .then(() => {
            console.log(`Killed ADB server before checking emulator ${emulator.device_id}`);
            
            // Then start a new ADB server with the emulator's port
            return fetch(API_ENDPOINTS.startServer, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    port: emulator.ports.adb_server
                }),
            });
        })
        .then(response => response.json())
        .then(() => {
            console.log(`Started ADB server with port ${emulator.ports.adb_server} for emulator ${emulator.device_id}`);
            
            // Then check current configuration like the PowerShell script
            return checkEmulatorStatus(emulator.ports.adb_server, `localhost:${emulator.ports.adb}`);
        })
        .then(status => {
            console.log(`Status for emulator ${emulator.device_id}:`, status);
            
            // Update UI with status
            let statusText = 'not connected';
            let statusClass = 'status-offline';
            
            if (status.serverRunning) {
                if (status.deviceConnected) {
                    statusText = status.deviceStatus || 'connected';
                    statusClass = getStatusClass(status.deviceStatus);
                    
                    // If device is connected but offline, try to connect again
                    if (status.deviceStatus === 'offline') {
                        console.log(`Emulator ${emulator.device_id} is offline, trying to reconnect...`);
                        if (window.connectToPort) {
                            window.connectToPort(emulator.ports.adb, emulator.ports.adb_server)
                                .then(() => console.log(`Reconnected to emulator ${emulator.device_id}`))
                                .catch(error => console.error(`Failed to reconnect to emulator ${emulator.device_id}:`, error));
                        }
                    }
                } else {
                    // If server is running but device not connected, try to connect
                    console.log(`Emulator ${emulator.device_id} is not connected, trying to connect...`);
                    if (window.connectToPort) {
                        window.connectToPort(emulator.ports.adb, emulator.ports.adb_server)
                            .then(() => console.log(`Connected to emulator ${emulator.device_id}`))
                            .catch(error => console.error(`Failed to connect to emulator ${emulator.device_id}:`, error));
                    }
                    
                    statusText = 'not connected';
                    statusClass = 'status-offline';
                }
            } else {
                statusText = 'server offline';
                statusClass = 'status-error';
            }
            
            statusBadge.className = `ms-2 status-badge ${statusClass}`;
            statusBadge.textContent = statusText;
        })
        .catch(error => {
            console.error(`Error checking emulator ${emulator.device_id} status:`, error);
            // Update UI to show error
            if (statusBadge) {
                statusBadge.className = 'ms-2 status-badge status-error';
                statusBadge.textContent = 'error';
            }
        });
}

// Setup automatic status checking
export function setupStatusChecking() {
    // Check statuses every 15 seconds
    setInterval(() => {
        if (window.checkAllDeviceStatuses) window.checkAllDeviceStatuses();
    }, 15000);
    
    // Initial check
    setTimeout(() => {
        if (window.checkAllDeviceStatuses) window.checkAllDeviceStatuses();
    }, 1000);
} 
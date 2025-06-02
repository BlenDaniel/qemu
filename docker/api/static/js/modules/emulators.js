import { API_ENDPOINTS } from './config.js';
import { getStatusClass, showAlert } from './ui.js';
import { switchToAdbServerPromise, connectToPort, checkEmulatorStatus } from './adb.js';

// Load emulators from API
export function loadEmulators(updateCallback) {
    fetch(API_ENDPOINTS.emulators)
        .then(response => response.json())
        .then(data => {
            const tableBody = document.getElementById('emulators-table');
            tableBody.innerHTML = '';
            
            // Check if there are any emulators
            if (Object.keys(data).length === 0) {
                tableBody.innerHTML = '<tr><td colspan="6" class="text-center">No emulators running</td></tr>';
                return;
            }
            
            // Populate table with emulators - creating initial rows without status
            for (const [id, emulator] of Object.entries(data)) {
                const row = document.createElement('tr');
                row.id = `emulator-row-${id}`;
                
                // Add basic info without status initially - we'll update status after proper ADB server setup
                row.innerHTML = `
                    <td>${emulator.device_id}</td>
                    <td>Android ${emulator.android_version || '11'}</td>
                    <td><span class="status-badge ${emulator.status === 'running' ? 'status-running' : 'status-stopped'}">${emulator.status}</span></td>
                    <td>
                        ${emulator.ports.adb}
                        <span class="ms-2 status-badge status-unknown">checking...</span>
                    </td>
                    <td>${emulator.ports.console}</td>
                    <td>
                        <button class="btn btn-sm btn-primary btn-action" onclick="window.connectToEmulator('${emulator.ports.adb}', this, '${emulator.ports.adb_server}')">Connect</button>
                        <button class="btn btn-sm btn-info btn-action" onclick="window.openConsole('${emulator.ports.console}', '${emulator.device_id}', '${emulator.ports.adb_server}')">Console</button>
                        <button class="btn btn-sm btn-danger btn-action" onclick="window.deleteEmulator('${id}', this)">Delete</button>
                    </td>
                `;
                
                tableBody.appendChild(row);
            }
            
            // Now check each emulator's status (no need to kill server each time)
            let statusPromise = Promise.resolve();
            
            Object.entries(data).forEach(([id, emulator]) => {
                statusPromise = statusPromise.then(() => {
                    // Ensure ADB server on correct port is running
                    return fetch(API_ENDPOINTS.startServer, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            port: emulator.ports.adb_server
                        }),
                    })
                        .then(response => response.json())
                        .then(() => {
                            return checkEmulatorStatus(emulator.ports.adb_server, `localhost:${emulator.ports.adb}`);
                        })
                        .then(status => {
                            // Update the status badge in the UI
                            const row = document.getElementById(`emulator-row-${id}`);
                            if (row) {
                                const statusBadge = row.querySelector('td:nth-child(4) .status-badge');
                                if (statusBadge) {
                                    const statusClass = getStatusClass(status.deviceStatus);
                                    const statusText = status.deviceStatus || 'Not connected';
                                    
                                    statusBadge.className = `ms-2 status-badge ${statusClass}`;
                                    statusBadge.textContent = statusText;
                                }
                            }
                        })
                        .catch(error => {
                            console.error(`Error checking status for emulator ${emulator.device_id}:`, error);
                            // Update status to error state
                            const row = document.getElementById(`emulator-row-${id}`);
                            if (row) {
                                const statusBadge = row.querySelector('td:nth-child(4) .status-badge');
                                if (statusBadge) {
                                    statusBadge.className = 'ms-2 status-badge status-error';
                                    statusBadge.textContent = 'error';
                                }
                            }
                        });
                });
            });
            
            // Notify main app that emulators are loaded
            if (updateCallback) updateCallback(data);
        })
        .catch(error => {
            showAlert('danger', `Error loading emulators: ${error.message}`);
        });
}

// Create a new emulator
export function createEmulator() {
    const deviceType = document.getElementById('device-type').value;
    // Always use external ADB server 
    const mapAdbServer = true; // Always map external ADB server
    document.getElementById('map-adb-server').checked = true; // Keep checkbox checked
    
    const statusDiv = document.getElementById('creation-status');
    
    statusDiv.innerHTML = '<p class="card-text">Creating emulator... Please wait.</p>';
    
    fetch(API_ENDPOINTS.emulators, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            android_version: deviceType,
            map_adb_server: mapAdbServer
        }),
    })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                statusDiv.innerHTML = `<p class="card-text text-danger">Error: ${data.error}</p>`;
                return;
            }
            
            // Show initial success message
            statusDiv.innerHTML = `
                <p class="card-text text-success">Emulator created! Waiting for it to start...</p>
                <div class="progress mb-3">
                    <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 25%"></div>
                </div>
                <div class="mt-3">
                    <h6>Emulator Details:</h6>
                    <ul>
                        <li>Device ID: ${data.device_id}</li>
                        <li>Android Version: ${data.android_version}</li>
                        <li>ADB Port: ${data.ports.adb}</li>
                        <li>Console Port: ${data.ports.console}</li>
                        <li>ADB Server Port: ${data.ports.adb_server}</li>
                    </ul>
                </div>
            `;
            
            // Refresh the dashboard to show the new emulator
            setTimeout(() => {
                if (window.loadEmulators) window.loadEmulators();
            }, 2000);
        })
        .catch(error => {
            statusDiv.innerHTML = `<p class="card-text text-danger">Error: ${error.message}</p>`;
        });
}


// Open emulator console
export function openConsole(port, deviceId, adbServerPort) {
    // If ADB server port is provided, switch to it first
    fetch(API_ENDPOINTS.emulators)
        .then(response => response.json())
        .then(data => {
            // Find the emulator with matching console port
            let emulatorData = null;
            for (const [id, emulator] of Object.entries(data)) {
                if (emulator.ports.console === port) {
                    emulatorData = emulator;
                    break;
                }
            }
            
            if (emulatorData) {
                // Use the emulator's ADB server port
                const serverPort = emulatorData.ports.adb_server;
                
                // Switch to the emulator's ADB server and connect
                switchToAdbServerPromise(serverPort)
                    .then(() => connectToPort(emulatorData.ports.adb, serverPort))
                    .then(() => {
                        // Now show the console modal
                        const modal = new bootstrap.Modal(document.getElementById('console-modal'));
                        document.getElementById('console-command').textContent = `telnet localhost ${port}`;
                        document.getElementById('console-device-id').textContent = deviceId;
                        modal.show();
                        
                        // Update statuses
                        setTimeout(() => {
                            if (window.checkAllDeviceStatuses) window.checkAllDeviceStatuses();
                        }, 1000);
                    })
                    .catch(error => {
                        console.error('Error in console connection sequence:', error);
                        // Still show console even if connection fails
                        const modal = new bootstrap.Modal(document.getElementById('console-modal'));
                        document.getElementById('console-command').textContent = `telnet localhost ${port}`;
                        document.getElementById('console-device-id').textContent = deviceId;
                        modal.show();
                    });
            } else {
                // Fallback if emulator data not found
                const modal = new bootstrap.Modal(document.getElementById('console-modal'));
                document.getElementById('console-command').textContent = `telnet localhost ${port}`;
                document.getElementById('console-device-id').textContent = deviceId;
                modal.show();
            }
        })
        .catch(error => {
            console.error('Error getting emulator data for console:', error);
            // Fallback to simple console display
            const modal = new bootstrap.Modal(document.getElementById('console-modal'));
            document.getElementById('console-command').textContent = `telnet localhost ${port}`;
            document.getElementById('console-device-id').textContent = deviceId;
            modal.show();
        });
}

// Also restore the delete function which was accidentally removed
export function deleteEmulator(id, buttonElement) {
    if (!confirm('Are you sure you want to delete this emulator? This will stop the container and remove it.')) {
        return;
    }
    
    // Show progress indicator
    if (buttonElement) {
        buttonElement.disabled = true;
        buttonElement.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Deleting...';
        
        // Disable all buttons in this row
        const row = document.getElementById(`emulator-row-${id}`);
        if (row) {
            const buttons = row.querySelectorAll('button');
            buttons.forEach(button => {
                button.disabled = true;
            });
        }
    }
    
    fetch(`${API_ENDPOINTS.emulators}/${id}`, {
        method: 'DELETE',
    })
        .then(response => {
            if (response.ok) {
                showAlert('success', 'Emulator deleted successfully');
                
                // Add deletion animation before removing
                const row = document.getElementById(`emulator-row-${id}`);
                if (row) {
                    row.style.transition = 'opacity 0.5s';
                    row.style.opacity = '0';
                    setTimeout(() => {
                        if (window.loadEmulators) window.loadEmulators();
                        if (window.loadDevices) window.loadDevices();
                        if (window.loadDevicesForSelect) window.loadDevicesForSelect();
                    }, 500);
                } else {
                    if (window.loadEmulators) window.loadEmulators();
                    if (window.loadDevices) window.loadDevices();
                    if (window.loadDevicesForSelect) window.loadDevicesForSelect();
                }
            } else {
                if (buttonElement) {
                    buttonElement.disabled = false;
                    buttonElement.innerHTML = 'Delete';
                }
                
                // Re-enable all buttons
                const row = document.getElementById(`emulator-row-${id}`);
                if (row) {
                    const buttons = row.querySelectorAll('button');
                    buttons.forEach(button => {
                        button.disabled = false;
                    });
                }
                
                showAlert('danger', 'Failed to delete emulator');
            }
        })
        .catch(error => {
            if (buttonElement) {
                buttonElement.disabled = false;
                buttonElement.innerHTML = 'Delete';
            }
            
            // Re-enable all buttons
            const row = document.getElementById(`emulator-row-${id}`);
            if (row) {
                const buttons = row.querySelectorAll('button');
                buttons.forEach(button => {
                    button.disabled = false;
                });
            }
            
            showAlert('danger', `Error: ${error.message}`);
        });
} 
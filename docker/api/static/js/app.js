// Import modules
import { API_ENDPOINTS, DEVICE_STATUS } from './modules/config.js';
import { showView, setActiveTab, showAlert } from './modules/ui.js';
import { 
    switchToAdbServer, 
    switchToAdbServerPromise,
    connectToPort, 
    connectToEmulator, 
    disconnectDevice,
    checkEmulatorStatus
} from './modules/adb.js';
import { 
    loadEmulators, 
    createEmulator, 
    openConsole, 
    deleteEmulator 
} from './modules/emulators.js';
import { 
    loadDevices, 
    loadDevicesForSelect, 
    installApk, 
    checkAllDeviceStatuses, 
    setupStatusChecking 
} from './modules/devices.js';

// Initialize environment
function initializeEnv() {
    // Fetch running emulators to get their ports
    fetch(API_ENDPOINTS.emulators)
        .then(response => response.json())
        .then(data => {
            // If there are running emulators, grab the first active one's ports
            const emulators = Object.entries(data);
            if (emulators.length > 0) {
                const [id, emulator] = emulators[0];
                if (emulator.status === 'running') {
                    console.log('Found running emulator, initializing environment variables with its ports');
                    
                    // Set ADB server port environment - this will make sure any initial checks use the right port
                    if (emulator.ports && emulator.ports.adb_server) {
                        // Make an initial call to set the ADB server port environment variable
                        fetch(API_ENDPOINTS.startServer, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                port: emulator.ports.adb_server
                            }),
                        })
                            .then(response => response.json())
                            .then(data => {
                                console.log(`Initialized ADB server port to: ${emulator.ports.adb_server}`);
                                
                                // After initializing server port, connect to the emulator
                                connectToPort(emulator.ports.adb, emulator.ports.adb_server)
                                    .then(() => {
                                        console.log(`Connected to emulator: ${emulator.device_id}`);
                                        
                                        // Check emulator status
                                        return checkEmulatorStatus(emulator.ports.adb_server, `localhost:${emulator.ports.adb}`);
                                    })
                                    .then(status => {
                                        console.log(`Emulator status:`, status);
                                        
                                        if (!status.deviceConnected || (status.deviceStatus === 'offline')) {
                                            console.log('Device is not properly connected, retrying connection...');
                                            
                                            // If device is not properly connected, retry
                                            setTimeout(() => {
                                                connectToPort(emulator.ports.adb, emulator.ports.adb_server)
                                                    .then(() => {
                                                        console.log('Retried connection to emulator');
                                                        loadDevices(emulator.ports.adb_server);
                                                    })
                                                    .catch(error => {
                                                        console.error('Error retrying connection:', error);
                                                    });
                                            }, 2000);
                                        } else {
                                            // Force refresh device list
                                            loadDevices(emulator.ports.adb_server);
                                        }
                                    })
                                    .catch(error => {
                                        console.error('Error connecting to emulator during initialization:', error);
                                    });
                            })
                            .catch(error => {
                                console.error('Error initializing ADB server port:', error);
                            });
                    }
                }
            } else {
                console.log('No running emulators found, using default environment');
            }
        })
        .catch(error => {
            console.error('Error initializing environment variables:', error);
        });
}

// Expose functions to window object for event handlers
window.showView = showView;
window.setActiveTab = setActiveTab;
window.showAlert = showAlert;
window.switchToAdbServer = switchToAdbServer;
window.switchToAdbServerPromise = switchToAdbServerPromise;
window.connectToPort = connectToPort;
window.connectToEmulator = connectToEmulator;
window.disconnectDevice = disconnectDevice;
window.checkEmulatorStatus = checkEmulatorStatus;
window.loadEmulators = loadEmulators;
window.createEmulator = createEmulator;
window.openConsole = openConsole;
window.deleteEmulator = deleteEmulator;
window.loadDevices = loadDevices;
window.loadDevicesForSelect = loadDevicesForSelect;
window.installApk = installApk;
window.checkAllDeviceStatuses = checkAllDeviceStatuses;

// Event listeners and initialization
document.addEventListener('DOMContentLoaded', function() {
    // Always check the map external ADB server checkbox
    const mapAdbServerCheckbox = document.getElementById('map-adb-server');
    if (mapAdbServerCheckbox) {
        mapAdbServerCheckbox.checked = true;
        mapAdbServerCheckbox.disabled = true; // Make it non-changeable
    }
    
    // Initialize environment
    initializeEnv();
    
    // Initialize UI
    loadEmulators();
    loadDevices();
    
    // Set up periodic status checking
    setupStatusChecking();
    
    // Set up tab navigation
    document.getElementById('dashboard-tab').addEventListener('click', function(e) {
        e.preventDefault();
        showView('dashboard-view');
        setActiveTab('dashboard-tab');
    });
    
    document.getElementById('create-tab').addEventListener('click', function(e) {
        e.preventDefault();
        showView('create-view');
        setActiveTab('create-tab');
    });
    
    document.getElementById('install-tab').addEventListener('click', function(e) {
        e.preventDefault();
        showView('install-view');
        setActiveTab('install-tab');
        loadDevicesForSelect();
    });
    
    // Set up refresh button
    document.getElementById('refresh-btn').addEventListener('click', function() {
        // Show loading indicator in the button
        const refreshBtn = this;
        const originalContent = refreshBtn.innerHTML;
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Refreshing...';
        
        // First get the emulators to find ADB server ports
        fetch(API_ENDPOINTS.emulators)
            .then(response => response.json())
            .then(data => {
                // Refresh emulators UI
                loadEmulators();
                
                // Start the emulator status check sequence
                checkAllDeviceStatuses();
                
                // Reset button after a short delay
                setTimeout(() => {
                    refreshBtn.disabled = false;
                    refreshBtn.innerHTML = originalContent;
                }, 1500);
            })
            .catch(error => {
                console.error('Error refreshing dashboard:', error);
                // Reset button
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = originalContent;
                showAlert('danger', `Error refreshing: ${error.message}`);
            });
    });
    
    // Set up create emulator form
    document.getElementById('create-emulator-form').addEventListener('submit', function(e) {
        e.preventDefault();
        createEmulator();
    });
    
    // Set up install APK form
    document.getElementById('install-apk-form').addEventListener('submit', function(e) {
        e.preventDefault();
        installApk();
    });
}); 
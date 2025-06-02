// API configuration for unified service
// Build a fully-qualified base that matches the unified API port (5001)
const API_HOST = `${window.location.protocol}//${window.location.hostname}:5001`;

export const API_ENDPOINTS = {
    emulators: `${API_HOST}/api/emulators`,
    devices:  `${API_HOST}/api/adb/devices`,
    connect:  `${API_HOST}/api/adb/connect`,
    disconnect:`${API_HOST}/api/adb/disconnect`,
    install:  `${API_HOST}/api/adb/install`,
    killServer:`${API_HOST}/api/adb/kill-server`,
    startServer:`${API_HOST}/api/adb/start-server`
};

// Device status constants
export const DEVICE_STATUS = {
    ONLINE: 'device',
    OFFLINE: 'offline',
    UNAUTHORIZED: 'unauthorized',
    CONNECTING: 'connecting'
}; 
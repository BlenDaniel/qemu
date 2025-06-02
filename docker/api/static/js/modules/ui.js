import { DEVICE_STATUS } from './config.js';

// Utility function to show a specific view
export function showView(viewId) {
    // Hide all views
    document.getElementById('dashboard-view').style.display = 'none';
    document.getElementById('create-view').style.display = 'none';
    document.getElementById('install-view').style.display = 'none';
    
    // Show the requested view
    document.getElementById(viewId).style.display = 'block';
}

// Utility function to set active tab
export function setActiveTab(tabId) {
    // Remove active class from all tabs
    document.querySelectorAll('.nav-link').forEach(function(el) {
        el.classList.remove('active');
    });
    
    // Add active class to the selected tab
    document.getElementById(tabId).classList.add('active');
}

// Get status class for styling
export function getStatusClass(status) {
    switch (status) {
        case DEVICE_STATUS.ONLINE:
            return 'status-running';
        case DEVICE_STATUS.OFFLINE:
            return 'status-stopped';
        case DEVICE_STATUS.UNAUTHORIZED:
            return 'status-warning';
        case 'not connected':
            return 'status-offline';
        case 'absent':
            return 'status-error';
        default:
            return 'status-unknown';
    }
}

// Show alert message
export function showAlert(type, message) {
    const alertContainer = document.getElementById('alert-container');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.role = 'alert';
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    alertContainer.appendChild(alert);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        alert.classList.remove('show');
        setTimeout(() => {
            alertContainer.removeChild(alert);
        }, 150);
    }, 5000);
} 
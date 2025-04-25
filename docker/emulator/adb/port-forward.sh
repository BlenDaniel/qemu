#!/bin/bash
# This script ensures proper port forwarding for ADB connections

# Give the main script time to set up
sleep 10

echo "===== ADB PORT FORWARDING HELPER ====="
echo "Starting port forwarding to ensure external connections work correctly"

# Function to wait for the emulator to be available
wait_for_adb_device() {
    echo "Waiting for ADB device to be available..."
    local timeout=60
    local start_time=$(date +%s)
    
    while true; do
        if adb devices | grep -q "device$"; then
            echo "ADB device found and ready"
            return 0
        fi
        
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ $elapsed -gt $timeout ]; then
            echo "Timeout waiting for ADB device"
            return 1
        fi
        
        echo "Still waiting for ADB device... (${elapsed}s)"
        sleep 5
    done
}

# Function to forward ADB port using socat
forward_adb_port() {
    echo "Setting up port forwarding for ADB..."
    
    # Kill any existing socat processes
    pkill -f "socat" || true
    
    # Forward ADB port to 0.0.0.0 so it's accessible from outside the container
    socat TCP-LISTEN:5555,fork,bind=0.0.0.0,reuseaddr TCP:localhost:5555 &
    SOCAT_PID=$!
    
    if [ -n "$SOCAT_PID" ]; then
        echo "Port forwarding started with PID: $SOCAT_PID"
    else
        echo "Failed to start port forwarding"
    fi
}

# Main loop to ensure port forwarding stays active
ensure_port_forwarding() {
    echo "Starting port forwarding monitor..."
    
    while true; do
        # Check if socat is running
        if ! pgrep -f "socat.*5555" > /dev/null; then
            echo "Port forwarding not running, restarting..."
            forward_adb_port
        fi
        
        # Verify external connectivity
        if ! nc -z -v 0.0.0.0 5555 > /dev/null 2>&1; then
            echo "Port 5555 not accessible from outside, fixing..."
            # Kill any stale processes
            pkill -f "socat" || true
            sleep 1
            forward_adb_port
        fi
        
        # Wait before next check
        sleep 10
    done
}

# Main execution
wait_for_adb_device
forward_adb_port
ensure_port_forwarding 
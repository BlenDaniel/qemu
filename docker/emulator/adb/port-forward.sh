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

# Forward the ADB server port (5037) first to ensure client can connect
forward_adb_server() {
    echo "Setting up port forwarding for ADB server (5037)..."
    
    # Kill any existing socat processes for this port
    pkill -f "socat.*5037" || true
    
    # Forward ADB server port to 0.0.0.0 (must be done first)
    socat TCP-LISTEN:5037,fork,bind=0.0.0.0,reuseaddr TCP:127.0.0.1:5037 &
    SOCAT_ADB_PID=$!
    
    if [ -n "$SOCAT_ADB_PID" ]; then
        echo "ADB server port forwarding started with PID: $SOCAT_ADB_PID"
    else
        echo "Failed to start ADB server port forwarding"
    fi
}

# Function to forward the emulator console port
forward_console_port() {
    echo "Setting up port forwarding for emulator console (5554)..."
    
    # Kill any existing socat processes for this port
    pkill -f "socat.*5554" || true
    
    # Forward the emulator console port
    socat TCP-LISTEN:5554,fork,bind=0.0.0.0,reuseaddr TCP:127.0.0.1:5554 &
    SOCAT_CONSOLE_PID=$!
    
    if [ -n "$SOCAT_CONSOLE_PID" ]; then
        echo "Console port forwarding started with PID: $SOCAT_CONSOLE_PID"
    else
        echo "Failed to start console port forwarding"
    fi
}

# Function to forward ADB port using socat
forward_adb_port() {
    echo "Setting up port forwarding for ADB connection (5555)..."
    
    # Kill any existing socat processes for this port
    pkill -f "socat.*5555" || true
    
    # Forward ADB port to 0.0.0.0 so it's accessible from outside the container
    # Important: Use 127.0.0.1 (not localhost) as the target for more reliable connections
    socat TCP-LISTEN:5555,fork,bind=0.0.0.0,reuseaddr TCP:127.0.0.1:5555 &
    SOCAT_PID=$!
    
    if [ -n "$SOCAT_PID" ]; then
        echo "ADB port forwarding started with PID: $SOCAT_PID"
    else
        echo "Failed to start ADB port forwarding"
    fi
}

# Restart ADB in the specific mode we need
configure_adb() {
    echo "Configuring ADB for external access..."
    
    # First make sure ADB server is running
    adb start-server
    
    # Use ADB tcpip to make sure Android is listening on network
    # This is important - run after the device is connected but before port forwarding
    if adb devices | grep -q "device$"; then
        adb tcpip 5555
        echo "ADB configured for TCP mode"
    else
        echo "No device available, skipping ADB TCP configuration"
    fi
}

# Main loop to ensure port forwarding stays active
ensure_port_forwarding() {
    echo "Starting port forwarding monitor..."
    
    while true; do
        # Check if ADB server port forwarder is running
        if ! pgrep -f "socat.*5037" > /dev/null; then
            echo "ADB server port forwarding not running, restarting..."
            forward_adb_server
        fi
        
        # Check if console port forwarder is running
        if ! pgrep -f "socat.*5554" > /dev/null; then
            echo "Console port forwarding not running, restarting..."
            forward_console_port
        fi
        
        # Check if ADB connection port forwarder is running
        if ! pgrep -f "socat.*5555" > /dev/null; then
            echo "ADB connection port forwarding not running, restarting..."
            forward_adb_port
        fi
        
        # Verify external connectivity for each port
        for PORT in 5037 5554 5555; do
            if ! nc -z -v 0.0.0.0 $PORT > /dev/null 2>&1; then
                echo "Port $PORT not accessible from outside, fixing..."
                # Kill any stale processes
                pkill -f "socat.*$PORT" || true
                sleep 1
                
                # Restart the appropriate forwarder
                case $PORT in
                    5037)
                        forward_adb_server
                        ;;
                    5554)
                        forward_console_port
                        ;;
                    5555)
                        forward_adb_port
                        ;;
                esac
            fi
        done
        
        # Reconfigure ADB occasionally to ensure it stays in TCP mode
        if [ $((RANDOM % 10)) -eq 0 ]; then
            configure_adb
        fi
        
        # Wait before next check
        sleep 10
    done
}

# Main execution
wait_for_adb_device
configure_adb
forward_adb_server
forward_console_port
forward_adb_port
ensure_port_forwarding 
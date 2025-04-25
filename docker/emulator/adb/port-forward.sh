#!/bin/bash
# This script ensures proper port forwarding for ADB connections

# Check if another instance of this script is already running
if pgrep -f "port-forward.sh" | grep -v $$ > /dev/null; then
    echo "Another instance of port-forward.sh is already running. Exiting."
    exit 0
fi

# Give the main script time to set up
sleep 20

echo "===== ADB PORT FORWARDING HELPER ====="
echo "Starting port forwarding to ensure external connections work correctly"

# Create a heartbeat file to help detect if the script is still running
HEARTBEAT_FILE="/tmp/port_forward_heartbeat"
touch $HEARTBEAT_FILE

# Function to wait for the emulator to be fully booted
wait_for_emulator() {
    echo "Waiting for emulator to fully boot..."
    local timeout=120
    local start_time=$(date +%s)
    
    while true; do
        # Check if device is connected and bootcomplete property is set to 1
        if adb devices | grep -q "emulator" && [ "$(adb shell getprop sys.boot_completed 2>/dev/null)" = "1" ]; then
            echo "Emulator is fully booted and ready"
            return 0
        fi
        
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ $elapsed -gt $timeout ]; then
            echo "Timeout waiting for emulator to boot"
            return 1
        fi
        
        echo "Still waiting for emulator to boot... (${elapsed}s)"
        sleep 5
    done
}

# Function to check if a port is already bound
is_port_bound() {
    local port=$1
    local interface=${2:-"localhost"}
    nc -z $interface $port 2>/dev/null
    return $?
}

# Function to find an available port starting from a base port
find_available_port() {
    local base_port=$1
    local max_tries=${2:-10}
    
    for (( i=0; i<$max_tries; i++ )); do
        local check_port=$((base_port + i))
        if ! is_port_bound $check_port "0.0.0.0" && ! is_port_bound $check_port "localhost"; then
            echo $check_port
            return 0
        fi
    done
    
    echo "-1"  # No available port found
    return 1
}

# Function to configure ADB networking
configure_adb_networking() {
    echo "Configuring ADB networking..."
    
    # Check if emulator is already running properly
    if ! adb devices | grep -q "emulator"; then
        echo "No emulator detected. Waiting for the main script to start it."
        sleep 10
        return 1
    fi
    
    # Wait for device to be available
    wait_for_emulator
    
    # Set ADB to listen on TCP/IP if not already
    if ! adb shell getprop service.adb.tcp.port | grep -q "5555"; then
        echo "Setting up ADB in TCP/IP mode..."
        adb tcpip 5555
        sleep 2
    else
        echo "ADB already in TCP/IP mode"
    fi
    
    # Check if socat is already running for port 5555
    if pgrep -f "socat.*5555" > /dev/null; then
        echo "Port forwarding already active, skipping setup"
        return 0
    fi
    
    # Set up port forwarding with socat
    echo "Setting up port forwarding with socat..."
    
    # Kill any existing socat processes
    pkill -f "socat TCP-LISTEN:5555" || true
    sleep 2
    
    # Start socat for port 5555
    socat TCP-LISTEN:5555,fork,reuseaddr,bind=0.0.0.0 TCP:localhost:5555 &
    SOCAT_PID=$!
    
    if [ -n "$SOCAT_PID" ] && ps -p $SOCAT_PID > /dev/null; then
        echo "Successfully started socat with PID: $SOCAT_PID"
    else
        echo "Failed to start socat"
        return 1
    fi
    
    # Connect ADB to localhost to ensure connection
    adb connect localhost:5555
    sleep 2
    
    echo "ADB networking configured successfully"
    return 0
}

# Function to monitor ADB connection and recover if needed
monitor_connection() {
    echo "Monitoring ADB connection..."
    
    # Update heartbeat
    date +%s > $HEARTBEAT_FILE
    
    # Check if ADB server is running
    if ! pgrep -x "adb" > /dev/null; then
        echo "ADB server not running, skipping checks"
        return 1
    fi
    
    # Check if port forwarding is still active (socat process)
    if ! pgrep -f "socat.*5555" > /dev/null; then
        echo "Port forwarding not active, restarting..."
        socat TCP-LISTEN:5555,fork,reuseaddr,bind=0.0.0.0 TCP:localhost:5555 &
        sleep 2
    fi
    
    # Check if ADB is available over network
    if ! nc -z -w 2 localhost 5555 > /dev/null 2>&1; then
        echo "ADB port 5555 not responding, attempting to reconfigure..."
        configure_adb_networking
    fi
    
    return 0
}

# Main execution
# Wait for initial setup to complete
sleep 30

# Trap signals to ensure we handle termination properly
trap "echo 'Received termination signal. Cleaning up...'; pkill -f 'socat.*5555' || true; exit 130" SIGINT SIGTERM

# Try initial configuration but don't exit if it fails
configure_adb_networking || echo "Initial configuration failed, will retry"

# Keep monitoring container networking
echo "Starting network monitoring..."

while true; do
    # Monitor connection and recover if needed
    monitor_connection
    
    # Wait before next check (use short sleep intervals for better signal handling)
    for i in {1..20}; do
        sleep 1
    done
done 
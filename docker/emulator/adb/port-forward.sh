#!/bin/bash
# This script ensures proper port forwarding for ADB connections

# Give the main script time to set up
sleep 20

echo "===== ADB PORT FORWARDING HELPER ====="
echo "Starting port forwarding to ensure external connections work correctly"

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
    
    # Restart ADB server to ensure clean state
    adb kill-server
    sleep 2
    adb start-server
    sleep 2
    
    # Wait for device to be available
    wait_for_emulator
    
    # Set ADB to listen on TCP/IP
    echo "Setting up ADB in TCP/IP mode..."
    adb tcpip 5555
    sleep 2
    
    # Check if ADB is bound to localhost only or to all interfaces
    if netstat -ln | grep -q "127.0.0.1:5555"; then
        echo "ADB bound to localhost only, setting up port forwarding..."
        
        # Check if port 5555 is available on all interfaces
        if is_port_bound 5555 "0.0.0.0"; then
            echo "Port 5555 is already bound on external interface, finding alternative port..."
            local new_port=$(find_available_port 5555)
            
            if [ "$new_port" = "-1" ]; then
                echo "ERROR: Could not find available port for forwarding"
                return 1
            fi
            
            echo "Using alternative port $new_port for forwarding"
            
            # Set up iptables rules to forward from new_port to 5555
            iptables -t nat -A PREROUTING -p tcp --dport $new_port -j DNAT --to-destination 127.0.0.1:5555
            echo "Starting socat to handle port forwarding from 0.0.0.0:$new_port to localhost:5555"
            socat TCP-LISTEN:$new_port,fork,reuseaddr TCP:localhost:5555 &
        else
            # Enable IP forwarding
            echo 1 > /proc/sys/net/ipv4/ip_forward
            
            # Set up NAT redirection for standard ADB port
            iptables -t nat -A PREROUTING -p tcp --dport 5555 -j DNAT --to-destination 127.0.0.1:5555
            iptables -t nat -A POSTROUTING -j MASQUERADE
            
            # Also start socat to handle direct connections
            echo "Starting socat to handle port forwarding from 0.0.0.0:5555 to localhost:5555"
            socat TCP-LISTEN:5555,fork,reuseaddr TCP:localhost:5555 &
        fi
    else
        echo "ADB already bound to all interfaces, no additional forwarding needed"
    fi
    
    # Connect ADB to the localhost to ensure connection
    adb connect localhost:5555
    sleep 2
    
    echo "ADB networking configured successfully"
    return 0
}

# Function to monitor ADB connection and recover if needed
monitor_connection() {
    echo "Monitoring ADB connection..."
    
    # Check if ADB server is running
    if ! pgrep -x "adb" > /dev/null; then
        echo "ADB server not running, restarting..."
        adb start-server
        sleep 2
        configure_adb_networking
        return
    fi
    
    # Check if ADB is still connected to the emulator
    if ! adb devices | grep -q "emulator"; then
        echo "Emulator not connected to ADB, reconnecting..."
        adb connect localhost:5555
        sleep 2
    fi
    
    # Check if port forwarding is still active
    if ! iptables -t nat -L PREROUTING | grep -q "dpt:5555"; then
        echo "Port forwarding rules missing, re-establishing..."
        configure_adb_networking
    fi
}

# Main execution
configure_adb_networking

# Keep monitoring container networking
echo "Starting network monitoring..."

while true; do
    # Output status for debugging
    echo "[$(date)] ADB connection status:"
    adb devices
    
    # Monitor connection and recover if needed
    monitor_connection
    
    # Wait before next check
    sleep 20
done 
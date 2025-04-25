#!/usr/bin/env bash
set -e

# Check if script is executable and has correct line endings
echo "===== SCRIPT CHECK ====="
echo "Starting script at: $(date)"
echo "Script path: $0"
echo "Script permissions: $(ls -la $0)"

# Check if ADB is installed and in PATH
if ! command -v adb &> /dev/null; then
    echo "ERROR: 'adb' command not found. Please ensure Android SDK platform-tools are installed and in PATH."
    echo "PATH is currently: $PATH"
    echo "Searching for adb:"
    find / -name adb 2>/dev/null || echo "No adb found on system"
    exit 1
fi

# Start PulseAudio in the background
pulseaudio --start --log-target=syslog --system=false --exit-idle-time=-1 &
sleep 2

echo "===== ANDROID EMULATOR INITIALIZATION ====="
echo "Starting Android Emulator services..."

# Kill any existing ADB server and start a fresh one with all connections allowed
echo "Starting ADB server..."
adb kill-server || echo "Failed to kill existing ADB server, continuing..."
sleep 3
adb -a -P 5037 start-server || { echo "ERROR: Failed to start ADB server. Check if adb is in PATH: $PATH"; exit 1; }
sleep 3

# Launch emulator with appropriate flags
echo "Launching Android emulator AVD 'test'..."

# Check if emulator command exists
if ! command -v emulator &> /dev/null; then
    echo "ERROR: 'emulator' command not found. Please ensure Android emulator is installed and in PATH."
    echo "PATH is currently: $PATH"
    echo "Searching for emulator:"
    find / -name emulator 2>/dev/null || echo "No emulator found on system"
    exit 1
fi

# Important: Add more flags to make emulator more stable
# 1. Adding -no-cache to avoid filesystem issues
# 2. Adding -no-metrics to suppress metrics warning
# 3. Adding -no-snapshot-save to avoid issues with snapshot corruption
# 4. Adding -no-boot-anim to speed up boot
# 5. Adding explicit port configuration with -ports
emulator -avd test -no-window -gpu swiftshader_indirect -no-audio -no-boot-anim \
    -no-snapshot -no-snapshot-save -no-cache -no-metrics \
    -ports 5554,5555 -qemu -m 2048 &
EMU_PID=$!

# Verify emulator process started
if ! ps -p $EMU_PID > /dev/null; then
    echo "ERROR: Failed to start the emulator. Check logs for details."
    exit 1
fi

echo "Emulator process started with PID: $EMU_PID"
echo "Waiting for emulator device to become available..."

# Wait for the emulator device to appear in adb devices list with longer timeout
TIMEOUT=180
START_TIME=$(date +%s)
SERIAL=""

while true; do
    DEVICES=$(adb devices | grep -E "emulator-[0-9]+" || echo "")
    
    if [ -n "$DEVICES" ]; then
        echo "Emulator found in device list: $DEVICES"
        
        # Check if device is in 'device' state (not offline)
        if echo "$DEVICES" | grep -q "device"; then
            echo "✅ Emulator detected and ready!"
            SERIAL=$(echo "$DEVICES" | grep "device" | head -n 1 | awk '{print $1}')
            echo "Using device: $SERIAL"
            break
        else
            echo "Emulator found but not ready yet"
            SERIAL=$(echo "$DEVICES" | grep -E "emulator-[0-9]+" | head -n 1 | awk '{print $1}')
            echo "Device status: $(echo "$DEVICES" | grep "$SERIAL" | awk '{print $2}')"
        fi
    fi

    CURRENT_TIME=$(date +%s)
    ELAPSED_TIME=$((CURRENT_TIME - START_TIME))

    # Try restarting ADB server periodically as a remediation step
    if [ $((ELAPSED_TIME % 30)) -eq 0 ] && [ $ELAPSED_TIME -gt 0 ]; then
        echo "Trying to restart ADB server after $ELAPSED_TIME seconds of waiting..."
        adb kill-server || echo "Failed to kill ADB server"
        sleep 3
        adb -a -P 5037 start-server || echo "Failed to start ADB server"
        sleep 3
    fi

    if [ $ELAPSED_TIME -gt $TIMEOUT ]; then
        echo "WARNING: Timeout waiting for emulator"
        echo "Current ADB devices:"
        adb devices
        
        # Fallback to using default serial if we at least found a device
        if [ -z "$SERIAL" ]; then
            SERIAL=$(adb devices | grep -E "emulator-[0-9]+" | head -n 1 | awk '{print $1}')
            
            if [ -n "$SERIAL" ]; then
                echo "Found device using alternative method: $SERIAL"
            else
                echo "⚠️ No device found after exhaustive searching. Will use default emulator-5554."
                SERIAL="emulator-5554"
            fi
        fi
        
        # Continue despite timeout
        break
    fi

    echo "Still waiting for emulator device... (${ELAPSED_TIME}s)"
    sleep 5
done

# Try to restart ADB server if device is still offline
DEVICE_STATUS=$(adb devices | grep "$SERIAL" | awk '{print $2}')
if [ "$DEVICE_STATUS" = "offline" ]; then
    echo "Emulator device is offline. Attempting comprehensive reconnection..."
    
    # Kill server, remove ADB keys, and restart server
    adb kill-server
    rm -f ~/.android/adbkey ~/.android/adbkey.pub 2>/dev/null || true
    sleep 3
    adb -a -P 5037 start-server
    sleep 5
    
    # Try direct reconnection to the emulator
    adb disconnect "$SERIAL" 2>/dev/null || true
    sleep 2
    adb connect "$SERIAL" || echo "Failed to connect to device"
    sleep 3
    
    # Check status again
    DEVICE_STATUS=$(adb devices | grep "$SERIAL" | awk '{print $2}')
    echo "Device status after reconnection attempt: $DEVICE_STATUS"
fi

echo "Waiting for system boot to complete..."

# Wait for system boot completion with improved checking
START_TIME=$(date +%s)
BOOT_TIMEOUT=240  # Increased boot timeout to 240s for extra stability
BOOT_COMPLETED="0"

while true; do
    # First ensure device is responsive
    adb -s $SERIAL wait-for-device 2>/dev/null || true
    
    # Check if device is online
    DEVICE_STATE=$(adb -s $SERIAL get-state 2>/dev/null || echo "unknown")
    echo "Current device state: $DEVICE_STATE"
    
    if [ "$DEVICE_STATE" = "device" ]; then
        # Now check boot_completed prop
        BOOT_COMPLETED=$(adb -s $SERIAL shell getprop sys.boot_completed 2>/dev/null || echo "0")
        echo "Boot status: $BOOT_COMPLETED"
        
        # Also check for activity manager availability as a sign of boot completion
        SERVICE_CHECK=$(adb -s $SERIAL shell "ps | grep system_server" 2>/dev/null || echo "")
        
        if [ "$BOOT_COMPLETED" = "1" ] && [ -n "$SERVICE_CHECK" ]; then
            # Additional check to ensure we're really ready
            PKG_SERVICE=$(adb -s $SERIAL shell "pm list packages" 2>/dev/null || echo "")
            if [ -n "$PKG_SERVICE" ]; then
                echo "Package service is up and running"
                break
            else
                echo "Package service not yet available"
            fi
        fi
    fi

    CURRENT_TIME=$(date +%s)
    ELAPSED_TIME=$((CURRENT_TIME - START_TIME))

    if [ $ELAPSED_TIME -gt $BOOT_TIMEOUT ]; then
        echo "WARNING: Timeout waiting for system boot to complete. Will continue anyway."
        break
    fi

    echo "Waiting for system boot... (${ELAPSED_TIME}s)"
    sleep 5
done

BOOT_TIME=$ELAPSED_TIME
echo "===== SUCCESS: Emulator booted successfully in ${BOOT_TIME} seconds! ====="

# IMPORTANT: Wait additional time for system services stabilization
echo "Waiting additional time for system services stabilization..."
sleep 10

# Function to verify device is responsive
verify_device() {
    adb -s "$SERIAL" shell echo "test" > /dev/null 2>&1
    return $?
}

# Enable ADB over TCP/IP with progressive approach - FIXED VERSION
echo "===== CONFIGURING ADB REMOTE ACCESS ====="

# CRITICAL FIX: First make sure device is still responsive
if ! verify_device; then
    echo "⚠️ Warning: Device not responding. Trying to reconnect..."
    adb kill-server
    sleep 2
    adb -a start-server
    sleep 2
    
    if ! verify_device; then
        echo "⚠️ Device still not responding. Will attempt recovery..."
    fi
fi

# IMPORTANT: Use this more reliable method instead of setting root
# Set the TCP/IP port property without requiring root
echo "Setting TCP port property directly via setprop..."
adb -s "$SERIAL" shell "setprop service.adb.tcp.port 5555" || echo "⚠️ Failed to set port property, continuing..."
sleep 3

# Try both TCP/IP configuration methods - first the most reliable
echo "Enabling TCP/IP mode using direct tcpip command..."
adb -s "$SERIAL" tcpip 5555 || echo "⚠️ tcpip command failed, trying alternative method..."
sleep 5

# Verify ADB TCP mode is enabled
echo "Verifying TCP mode..."
if verify_device; then
    TCP_PORT=$(adb -s "$SERIAL" shell getprop service.adb.tcp.port 2>/dev/null || echo "")
    if [ "$TCP_PORT" = "5555" ]; then
        echo "✅ TCP port property set correctly to 5555"
    else
        echo "⚠️ TCP port property not set correctly, trying universal command..."
        adb tcpip 5555 || echo "⚠️ Universal tcpip command failed"
        sleep 5
    fi
else
    echo "⚠️ Device not responding, cannot verify TCP mode"
fi

# Get device IP for more reliable connection
DEVICE_IP=""
if verify_device; then
    # Try multiple methods to get device IP
    DEVICE_IP=$(adb -s "$SERIAL" shell "ip addr show | grep -E 'inet 10\\.' | cut -d/ -f1 | awk '{print \$2}'" 2>/dev/null || echo "")
    if [ -z "$DEVICE_IP" ]; then
        DEVICE_IP=$(adb -s "$SERIAL" shell "getprop dhcp.eth0.ipaddress" 2>/dev/null || echo "")
    fi
    if [ -z "$DEVICE_IP" ]; then
        DEVICE_IP="localhost"
    fi
else
    DEVICE_IP="localhost"
fi

# Try connecting to the device over TCP/IP with both localhost and specific IP
echo "Testing TCP/IP connection..."
# First disconnect existing connections
adb disconnect "$SERIAL" 2>/dev/null || true
sleep 2

# Try connection to local IP first
echo "Connecting to ADB over TCP using localhost:5555..."
adb connect localhost:5555 || echo "⚠️ Failed to connect to localhost:5555"
sleep 3

# Try device IP if available
if [ -n "$DEVICE_IP" ] && [ "$DEVICE_IP" != "localhost" ]; then
    echo "Connecting to ADB over TCP using device IP: $DEVICE_IP:5555..."
    adb connect "$DEVICE_IP:5555" || echo "⚠️ Failed to connect to $DEVICE_IP:5555"
    sleep 3
fi

# Check if either connection was successful
ADB_DEVICES=$(adb devices)
if echo "$ADB_DEVICES" | grep -E "localhost:5555|$DEVICE_IP:5555" | grep -q "device"; then
    echo "✅ Successfully connected to emulator via TCP/IP!"
else
    echo "⚠️ Failed to establish reliable TCP/IP connection, falling back to original connection"
fi

# Display connection information
echo ""
echo "===== EMULATOR INFORMATION ====="
echo "Listing connected devices:"
adb devices

echo ""
echo "System information:"
adb -s "$SERIAL" shell getprop ro.build.version.release 2>/dev/null || echo "Android version: Unable to retrieve"
adb -s "$SERIAL" shell getprop ro.build.version.sdk 2>/dev/null || echo "API Level: Unable to retrieve"
adb -s "$SERIAL" shell getprop ro.product.model 2>/dev/null || echo "Device model: Unable to retrieve"

echo ""
echo "===== ADB REMOTE CONNECTION INFO ====="
# Get container IP for external connection
CONTAINER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo "ADB server is running and accessible at:"
echo "Host: $CONTAINER_IP"
echo "Port: 5555"
echo "You can connect from your development machine using: adb connect $CONTAINER_IP:5555"
echo "====================================="

# Verify network connectivity
echo "Checking network connectivity to emulator..."
nc -z -v localhost 5555 || echo "WARNING: Cannot connect to emulator on port 5555"

# Function to check if emulator is responsive and reconnect if needed
check_and_fix_emulator() {
    # First check if the emulator process is still running
    if ! ps -p $EMU_PID > /dev/null; then
        echo "⚠️ Emulator process (PID $EMU_PID) died!"
        return 1
    fi
    
    # Then check device connectivity
    local device_status=$(adb devices | grep -E "emulator-[0-9]+|localhost:5555|$DEVICE_IP:5555" | awk '{print $2}')
    
    if [ -z "$device_status" ]; then
        echo "⚠️ No device found in ADB devices list, attempting reconnection..."
        adb kill-server
        sleep 2
        adb -a start-server
        sleep 3
        adb connect localhost:5555
        if [ -n "$DEVICE_IP" ] && [ "$DEVICE_IP" != "localhost" ]; then
            adb connect "$DEVICE_IP:5555"
        fi
        sleep 2
        return 1
    elif [ "$device_status" = "offline" ]; then
        echo "⚠️ Device is offline, attempting to reconnect..."
        
        # Try full reconnection sequence
        adb disconnect "$SERIAL" 2>/dev/null || true
        adb disconnect localhost:5555 2>/dev/null || true
        if [ -n "$DEVICE_IP" ] && [ "$DEVICE_IP" != "localhost" ]; then
            adb disconnect "$DEVICE_IP:5555" 2>/dev/null || true
        fi
        sleep 2
        
        # Restart ADB server
        adb kill-server
        sleep 2
        adb -a start-server
        sleep 3
        
        # Connect to all possible endpoints
        adb connect localhost:5555
        if [ -n "$DEVICE_IP" ] && [ "$DEVICE_IP" != "localhost" ]; then
            adb connect "$DEVICE_IP:5555"
        fi
        sleep 3
        
        # Verify if reconnection worked
        local new_status=$(adb devices | grep -E "localhost:5555|$DEVICE_IP:5555" | awk '{print $2}')
        if [ "$new_status" = "device" ]; then
            echo "✅ Successfully reconnected to emulator"
            # Re-enable TCP mode just to be sure
            adb tcpip 5555
            return 0
        else
            echo "⚠️ Failed to reconnect to emulator"
            return 1
        fi
    elif [ "$device_status" = "device" ]; then
        # Device is online, just verify TCP mode
        return 0
    else
        echo "⚠️ Unknown device status: $device_status"
        return 1
    fi
}

# CRITICAL: Keep the emulator process running and monitor its status
echo "Starting emulator monitoring to keep it alive..."

# Infinite loop to keep container running and monitor emulator status
while true; do
    # Check if emulator process is still running
    if ! ps -p $EMU_PID > /dev/null; then
        echo "⚠️ Emulator process (PID $EMU_PID) died! Will continue monitoring ADB connection."
    fi
    
    # Check and fix emulator connection if needed
    check_and_fix_emulator
    
    # Sleep for a while before next check (15 seconds instead of 30)
    for i in {1..15}; do
        sleep 1
    done
done
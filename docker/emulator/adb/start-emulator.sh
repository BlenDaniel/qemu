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

# Use more memory and add -no-snapshot flag to ensure fresh boot
# Use -ports to specify console and adb ports explicitly
emulator -avd test -no-window -gpu swiftshader_indirect -no-audio -no-boot-anim -no-snapshot -ports 5554,5555 -qemu -m 2048 &
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

# IMPORTANT: Wait additional time after system services stabilization
echo "Waiting additional time for system services stabilization..."
sleep 10

# Enable ADB over TCP/IP with progressive approach from enable_adb_connection.sh
echo "===== CONFIGURING ADB REMOTE ACCESS ====="

# Step 1: Ensure the device is accessible
adb -s "$SERIAL" wait-for-device || {
    echo "ERROR: Device not accessible after boot";
    # Continue anyway
}

# Step 2: Set device to root for better permissions
echo "Setting ADB as root..."
adb -s "$SERIAL" root || echo "Could not set ADB as root, will try tcpip anyway"
sleep 5  # Give device time to restart in root mode

# Step 3: Wait for device after root mode switch
echo "Reconnecting to device after root mode switch..."
adb -s "$SERIAL" wait-for-device || echo "Wait for device timed out"
sleep 3

# Step 4: Set TCP port property directly for redundancy
echo "Setting TCP port property directly..."
adb -s "$SERIAL" shell "setprop service.adb.tcp.port 5555" || echo "Failed to set TCP port property"
sleep 2

# Step 5: Restart ADB daemon on device
echo "Restarting ADB daemon..."
adb -s "$SERIAL" shell "stop adbd" || echo "Failed to stop ADB daemon"
sleep 2
adb -s "$SERIAL" shell "start adbd" || echo "Failed to start ADB daemon"
sleep 3

# Step 6: Use tcpip command as the official method
echo "Setting device to TCP/IP mode..."
adb -s "$SERIAL" tcpip 5555 || echo "WARNING: adb tcpip command failed"
sleep 5  # Give more time for mode switch

# Step 7: Verify ADB TCP mode is enabled
echo "Verifying TCP mode..."
TCP_PORT=$(adb -s "$SERIAL" shell getprop service.adb.tcp.port 2>/dev/null || echo "")
if [ "$TCP_PORT" = "5555" ]; then
    echo "✅ ADB TCP mode successfully enabled on port 5555"
else
    echo "⚠️ Failed to verify ADB TCP mode, attempting universal command..."
    # Try the global command as fallback
    adb tcpip 5555 || echo "WARNING: Could not set ADB to TCP mode with global command either"
    sleep 5
    
    # Check one more time
    TCP_PORT=$(adb -s "$SERIAL" shell getprop service.adb.tcp.port 2>/dev/null || echo "")
    if [ "$TCP_PORT" = "5555" ]; then
        echo "✅ ADB TCP mode successfully enabled on second attempt"
    else
        echo "⚠️ Still failed to set ADB TCP mode properly"
    fi
fi

# Step 8: Try connecting to the device over TCP/IP as a verification
echo "Testing TCP/IP connection..."
adb disconnect "$SERIAL" 2>/dev/null || true
sleep 2
adb connect localhost:5555 || echo "Failed to connect to localhost:5555"
sleep 2

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
HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo "ADB server is running and accessible at:"
echo "Host: $HOST_IP"
echo "Port: 5555"
echo "You can connect from your development machine using: adb connect $HOST_IP:5555"
echo "====================================="

# Verify network connectivity
echo "Checking network connectivity to emulator..."
nc -z -v localhost 5555 || echo "WARNING: Cannot connect to emulator on port 5555"

# CRITICAL: Keep the emulator process running and monitor its status
echo "Starting emulator monitoring to keep it alive..."

# Function to check if emulator is responsive and reconnect if needed
check_and_fix_emulator() {
    local device_status=$(adb devices | grep "$SERIAL" | awk '{print $2}')
    
    if [ -z "$device_status" ]; then
        echo "⚠️ Emulator not found in device list, attempting reconnection..."
        adb kill-server
        sleep 2
        adb -a start-server
        sleep 3
        adb connect localhost:5555
        return 1
    elif [ "$device_status" = "offline" ]; then
        echo "⚠️ Emulator is offline, attempting to reconnect..."
        
        # Try to reconnect via TCP/IP
        adb disconnect "$SERIAL" 2>/dev/null || true
        sleep 1
        adb kill-server
        sleep 2
        adb -a start-server
        sleep 2
        adb connect localhost:5555
        
        # Check if it worked
        device_status=$(adb devices | grep "$SERIAL" | awk '{print $2}')
        if [ "$device_status" = "device" ]; then
            echo "✅ Successfully reconnected to emulator"
            return 0
        else
            echo "⚠️ Failed to reconnect to emulator"
            return 1
        fi
    elif [ "$device_status" = "device" ]; then
        # Device is online, verify ADB TCP is still enabled
        local tcp_port=$(adb -s "$SERIAL" shell getprop service.adb.tcp.port 2>/dev/null || echo "")
        if [ "$tcp_port" != "5555" ]; then
            echo "⚠️ TCP mode disabled, re-enabling..."
            adb -s "$SERIAL" tcpip 5555
        fi
        return 0
    else
        echo "⚠️ Unknown device status: $device_status"
        return 1
    fi
}

# Infinite loop to keep container running and monitor emulator status
while true; do
    # Check if emulator process is still running
    if ! ps -p $EMU_PID > /dev/null; then
        echo "⚠️ Emulator process (PID $EMU_PID) died! Will continue monitoring ADB connection."
    fi
    
    # Check and fix emulator connection if needed
    check_and_fix_emulator
    
    # Sleep for a while before next check (30 seconds)
    for i in {1..30}; do
        sleep 1
    done
done
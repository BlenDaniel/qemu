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

# Kill any existing ADB server and start a fresh one - do this only once
echo "Starting ADB server..."
adb kill-server || echo "Failed to kill existing ADB server, continuing..."
sleep 2
adb -a start-server || { echo "ERROR: Failed to start ADB server. Check if adb is in PATH: $PATH"; exit 1; }
sleep 2

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
emulator -avd test -no-window -gpu swiftshader_indirect -no-audio -no-boot-anim -no-snapshot -qemu -m 2048 &
EMU_PID=$!

# Verify emulator process started
if ! ps -p $EMU_PID > /dev/null; then
    echo "ERROR: Failed to start the emulator. Check logs for details."
    exit 1
fi

echo "Emulator process started with PID: $EMU_PID"
echo "Waiting for emulator device to become available..."

# Wait for the emulator device to appear in adb devices list (timeout 180s)
TIMEOUT=180
START_TIME=$(date +%s)
while true; do
    LINES=$(adb devices)
    SERIAL=$(echo "$LINES" | awk '/^emulator-.*/{print $1; exit}')
    
    if [ -n "$SERIAL" ]; then
        STATUS=$(echo "$LINES" | grep "$SERIAL" | awk '{print $2}')
        echo "Found emulator serial: $SERIAL with status: $STATUS"
        
        # If status is device, break immediately
        if [ "$STATUS" = "device" ]; then
            echo "Emulator is online and ready!"
            break
        else
            echo "Emulator found but status is: $STATUS"
            # If just found but offline, wait a bit more
        fi
    fi

    CURRENT_TIME=$(date +%s)
    ELAPSED_TIME=$((CURRENT_TIME - START_TIME))

    if [ $ELAPSED_TIME -gt $TIMEOUT ]; then
        echo "ERROR: Timeout waiting for emulator to become available."
        exit 1
    fi

    echo "Still waiting for emulator device... (${ELAPSED_TIME}s)"
    sleep 5
done

echo "Emulator device detected! Serial: $SERIAL"

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

# IMPORTANT: Wait additional time after boot to ensure services stability
echo "Waiting additional time for system services stabilization..."
sleep 10

# Configure ADB root access - attempt up to 3 times with increasing delay
echo "Configuring ADB over TCP..."
for i in {1..3}; do
    echo "Attempt $i: Setting ADB as root..."
    if adb -s $SERIAL root; then
        echo "ADB set as root successfully"
        break
    else
        echo "Failed to set ADB as root, waiting before retry..."
        sleep $(( i * 3 ))  # Exponential backoff
    fi
    
    if [ $i -eq 3 ]; then
        echo "WARNING: Could not set ADB as root after 3 attempts, continuing..."
    fi
done

# Wait for device after root mode switch
echo "Waiting for device after root mode switch..."
adb -s $SERIAL wait-for-device
sleep 5

# Set TCP port property with retry
for i in {1..3}; do
    echo "Attempt $i: Setting TCP port property..."
    if adb -s $SERIAL shell setprop service.adb.tcp.port 5555; then
        echo "TCP port property set successfully"
        break
    else
        echo "Failed to set TCP port property, waiting before retry..."
        sleep $(( i * 2 ))
    fi
done

# Restart ADB daemon with retry and proper checking
for i in {1..3}; do
    echo "Attempt $i: Restarting ADB daemon..."
    # Stop ADB daemon
    adb -s $SERIAL shell stop adbd || { 
        echo "Could not stop ADB daemon, waiting before retry..."; 
        sleep $(( i * 2 ));
        continue;
    }
    
    sleep 3
    
    # Start ADB daemon
    adb -s $SERIAL shell start adbd || {
        echo "Could not start ADB daemon, waiting before retry...";
        sleep $(( i * 2 ));
        continue;
    }
    
    sleep 5
    
    # Verify ADB restart was successful
    TCP_PORT=$(adb -s $SERIAL shell getprop service.adb.tcp.port 2>/dev/null || echo "")
    if [ "$TCP_PORT" = "5555" ]; then
        echo "ADB daemon restarted successfully in TCP mode"
        break
    else
        echo "ADB TCP mode not verified, proceeding to next attempt..."
    fi
    
    if [ $i -eq 3 ]; then
        echo "WARNING: Could not properly restart ADB daemon after 3 attempts"
    fi
done

# Try explicitly setting tcpip mode
echo "Setting ADB to tcpip mode..."
adb -s $SERIAL tcpip 5555 || echo "WARNING: adb tcpip command failed, however TCP port was already set"

# Wait for ADB to switch modes
sleep 10

# Display device information
echo ""
echo "===== EMULATOR INFORMATION ====="
echo "Listing connected devices:"
adb devices

echo ""
echo "System information:"
# Add timeout command with better error handling
timeout 5 adb -s $SERIAL shell getprop ro.build.version.release > /dev/null 2>&1 && \
  echo "Android version: $(adb -s $SERIAL shell getprop ro.build.version.release)" || \
  echo "Android version: Unable to retrieve"

timeout 5 adb -s $SERIAL shell getprop ro.build.version.sdk > /dev/null 2>&1 && \
  echo "API Level: $(adb -s $SERIAL shell getprop ro.build.version.sdk)" || \
  echo "API Level: Unable to retrieve"

timeout 5 adb -s $SERIAL shell getprop ro.product.model > /dev/null 2>&1 && \
  echo "Device model: $(adb -s $SERIAL shell getprop ro.product.model)" || \
  echo "Device model: Unable to retrieve"

echo ""
echo "===== ADB REMOTE CONNECTION INFO ====="
echo "ADB server is running on port 5037"
echo "You can connect to it from your development environment"
echo "Container is ready to use for Android application testing"
echo "====================================="

# Check for network connectivity issues
echo "Checking network connectivity to emulator..."
nc -z -v localhost 5555 || echo "WARNING: Cannot connect to emulator on port 5555"

# Try to get the device's IP address
DEVICE_IP=$(adb -s $SERIAL shell "ip -4 addr show | grep inet | grep -v 127.0.0.1 | awk '{print \$2}' | cut -d/ -f1" 2>/dev/null)
echo "Device IP address: $DEVICE_IP"

# Keep container alive
echo "Emulator is now running. Use Ctrl+C to terminate."
tail -f /dev/null
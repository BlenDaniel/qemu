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

# Kill any existing ADB server and start a fresh one
echo "Starting ADB server..."
adb kill-server || echo "Failed to kill existing ADB server, continuing..."
adb start-server || { echo "ERROR: Failed to start ADB server. Check if adb is in PATH: $PATH"; exit 1; }

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

emulator -avd test -no-window -gpu swiftshader_indirect -no-audio -no-boot-anim -qemu -m 1536 &
EMU_PID=$!

# Verify emulator process started
if ! ps -p $EMU_PID > /dev/null; then
echo "ERROR: Failed to start the emulator. Check logs for details."
exit 1
fi

echo "Emulator process started with PID: $EMU_PID"
echo "Waiting for emulator device to become available..."

# Wait for the emulator device to appear in adb devices list (timeout 120s)
TIMEOUT=120
START_TIME=$(date +%s)
while true; do
LINES=$(adb devices)
SERIAL=$(echo "$LINES" | awk '/^emulator-.*\s*device$/{print $1; exit}')
if [ -n "$SERIAL" ]; then
break
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


# ---------------------------------------- FIND AND FIX PROBLEM FROM HERE ONWARDS,
echo "Emulator device detected! Enabling ADB over TCP/IP on port 5555..."
echo "Emulator serial detected: $SERIAL"

# Enable ADB over TCP inside the emulator
adb -s $SERIAL root || echo "WARNING: Could not set ADB as root, continuing..."
adb -s $SERIAL shell setprop service.adb.tcp.port 5555 || echo "WARNING: Could not set TCP port property, continuing..."

# Restart ADB daemon inside the emulator to apply the TCP port change
adb -s $SERIAL shell stop adbd || echo "WARNING: Could not stop ADB daemon, continuing..."
adb -s $SERIAL shell start adbd || echo "WARNING: Could not start ADB daemon, continuing..."

echo "Waiting for system boot to complete..."

# Wait for system boot completion (timeout 120s)
START_TIME=$(date +%s)
while true; do
BOOT_COMPLETED=$(adb -s $SERIAL shell getprop sys.boot_completed 2>/dev/null || echo "0")

if [ "$BOOT_COMPLETED" = "1" ]; then
break
fi

CURRENT_TIME=$(date +%s)
ELAPSED_TIME=$((CURRENT_TIME - START_TIME))

if [ $ELAPSED_TIME -gt $TIMEOUT ]; then
echo "ERROR: Timeout waiting for system boot to complete."
exit 1
fi

echo "Waiting for system boot... (${ELAPSED_TIME}s)"
sleep 5
done

BOOT_TIME=$ELAPSED_TIME
echo "===== SUCCESS: Emulator booted successfully in ${BOOT_TIME} seconds! ====="

# Display device information
echo ""
echo "===== EMULATOR INFORMATION ====="
echo "Listing connected devices:"
adb devices

echo ""
echo "System information:"
echo "Android version: $(adb -s $SERIAL shell getprop ro.build.version.release)"
echo "API Level: $(adb -s $SERIAL shell getprop ro.build.version.sdk)"
echo "Device model: $(adb -s $SERIAL shell getprop ro.product.model)"

echo ""
echo "===== ADB REMOTE CONNECTION INFO ====="
echo "ADB server is running on port 5037"
echo "You can connect to it from your development environment"
echo "Container is ready to use for Android application testing"
echo "====================================="

# Check multiple locations for the enable_adb_connection.sh script
for SCRIPT_PATH in "/usr/local/bin/enable_adb_connection.sh" "/enable_adb_connection.sh"; do
    if [ -f "$SCRIPT_PATH" ] && [ -x "$SCRIPT_PATH" ]; then
        echo "Found enable_adb_connection.sh at $SCRIPT_PATH"
        echo "Enabling ADB over TCP/IP for remote connections..."
        "$SCRIPT_PATH" || echo "WARNING: Failed to run enable_adb_connection.sh"
        break
    fi
done

# If script not found, do it manually
if [ ! -f "/usr/local/bin/enable_adb_connection.sh" ] && [ ! -f "/enable_adb_connection.sh" ]; then
    echo "WARNING: enable_adb_connection.sh not found or not executable"
    echo "Enabling TCP/IP manually..."
    adb tcpip 5555 || echo "WARNING: Could not set ADB to TCP mode, connections may not work"
fi

# Keep container alive
echo "Emulator is now running. Use Ctrl+C to terminate."
tail -f /dev/null
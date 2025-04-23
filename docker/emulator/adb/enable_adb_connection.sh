#!/bin/bash
set -e

# Script debugging information
echo "===== ENABLE ADB CONNECTION SCRIPT ====="
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

# Kill any existing ADB server
echo "Killing any existing ADB server..."
adb kill-server || echo "Failed to kill existing ADB server, continuing..."

# Start ADB server accepting all connections (-a flag)
echo "Starting ADB server with all connections allowed..."
adb -a -P 5037 start-server || { echo "ERROR: Failed to start ADB server. Check if adb is in PATH: $PATH"; exit 1; }

# Wait for the emulator to be fully started
TIMEOUT=30
echo "Waiting for emulator to be ready..."
for i in $(seq 1 $TIMEOUT); do
  # Check for any emulator
  if adb devices | grep -E "emulator-[0-9]+" | grep -q "device"; then
    echo "Emulator detected and ready!"
    break
  fi
  
  if [ $i -eq $TIMEOUT ]; then
    echo "WARNING: Timeout waiting for emulator"
    echo "Current ADB devices:"
    adb devices
    # Don't exit with error, just warn and continue
    echo "Will attempt to enable TCP/IP mode anyway..."
  fi
  
  echo "Waiting for emulator... ($i/$TIMEOUT)"
  sleep 1
done

# Get the emulator device serial
DEVICE=$(adb devices | grep -E "emulator-[0-9]+" | grep "device" | head -n 1 | awk '{print $1}')

# Enable ADB over TCP/IP
echo "Enabling ADB over TCP/IP on port 5555..."
if [ -n "$DEVICE" ]; then
  echo "Using device: $DEVICE"
  adb -s "$DEVICE" tcpip 5555 || {
    echo "WARNING: Failed with specific device, trying without device specification..."
    adb tcpip 5555 || echo "WARNING: Could not set ADB to TCP mode, connections may not work"
  }
else
  echo "No specific device found, trying generic command..."
  adb tcpip 5555 || echo "WARNING: Could not set ADB to TCP mode, connections may not work"
fi

# Give it time to switch modes
sleep 2

# Verify ADB TCP mode is enabled
TCP_PORT=$(adb shell getprop service.adb.tcp.port 2>/dev/null || echo "")
if [ "$TCP_PORT" = "5555" ]; then
  echo "✅ ADB TCP mode successfully enabled on port 5555"
else
  echo "⚠️ Failed to verify ADB TCP mode, attempting again..."
  adb tcpip 5555 || echo "WARNING: Could not set ADB to TCP mode, connections may not work"
  sleep 2
fi

echo "==============================================" 
echo "📱 ADB TCP mode enabled. This container's ADB service is"
echo "   running on container port 5555 which is mapped to"
echo "   a host port that you can find via the API."
echo "   Run: curl http://localhost:5001/emulators"
echo "==============================================" 

# Print connection info
CONTAINER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown")
echo "Container IP: $CONTAINER_IP"
echo "==============================================" 
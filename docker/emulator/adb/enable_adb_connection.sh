#!/bin/bash
set -e

# Check if ADB is installed and in PATH
if ! command -v adb &> /dev/null; then
    echo "ERROR: 'adb' command not found. Please ensure Android SDK platform-tools are installed and in PATH."
    echo "PATH is currently: $PATH"
    exit 1
fi

# Kill any existing ADB server
adb kill-server || echo "Failed to kill existing ADB server, continuing..."

# Start ADB server accepting all connections (-a flag)
adb -a -P 5037 start-server || { echo "ERROR: Failed to start ADB server. Check if adb is in PATH: $PATH"; exit 1; }

# Wait for the emulator to be fully started
TIMEOUT=30
echo "Waiting for emulator to be ready..."
for i in $(seq 1 $TIMEOUT); do
  if adb devices | grep "emulator-5554" | grep -q "device"; then
    echo "Emulator detected and ready!"
    break
  fi
  
  if [ $i -eq $TIMEOUT ]; then
    echo "ERROR: Timeout waiting for emulator"
    # Don't exit with error, just warn and continue
    echo "Will attempt to enable TCP/IP mode anyway..."
  fi
  
  echo "Waiting for emulator... ($i/$TIMEOUT)"
  sleep 1
done

# Enable ADB over TCP/IP
echo "Enabling ADB over TCP/IP on port 5555..."
adb -s emulator-5554 tcpip 5555 || {
  echo "WARNING: Failed with emulator-5554, trying without device specification..."
  adb tcpip 5555 || echo "WARNING: Could not set ADB to TCP mode, connections may not work"
}

# Give it time to switch modes
sleep 2

# Verify ADB TCP mode is enabled
if adb shell getprop service.adb.tcp.port 2>/dev/null | grep -q "5555"; then
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
echo "Container IP: $(hostname -I | awk '{print $1}')" 
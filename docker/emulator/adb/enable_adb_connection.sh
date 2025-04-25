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
sleep 3  # Increased sleep time to ensure server is fully stopped

# Start ADB server accepting all connections (-a flag)
echo "Starting ADB server with all connections allowed..."
adb -a -P 5037 start-server || { echo "ERROR: Failed to start ADB server. Check if adb is in PATH: $PATH"; exit 1; }
sleep 5  # Give ADB server time to fully initialize

# Wait for the emulator to be fully started with a longer timeout
TIMEOUT=120  # Increased timeout to 120 seconds
echo "Waiting for emulator to be ready..."
for i in $(seq 1 $TIMEOUT); do
  # First check if devices are listed at all
  DEVICES=$(adb devices | grep -E "emulator-[0-9]+" || echo "")
  
  if [ -n "$DEVICES" ]; then
    echo "Emulator found in device list."
    
    # Check if device is in 'device' state (not offline)
    if echo "$DEVICES" | grep -q "device"; then
      echo "✅ Emulator detected and ready!"
      DEVICE=$(echo "$DEVICES" | grep "device" | head -n 1 | awk '{print $1}')
      echo "Using device: $DEVICE"
      break
    else
      echo "Emulator found but not ready yet (status: $(echo "$DEVICES" | grep -E "emulator-[0-9]+" | awk '{print $2}'))"
    fi
  fi
  
  # If we're at i=30, 60, or 90, try restarting ADB server as a remediation step
  if [ $i -eq 30 ] || [ $i -eq 60 ] || [ $i -eq 90 ]; then
    echo "Trying to restart ADB server after $i seconds of waiting..."
    adb kill-server || echo "Failed to kill ADB server"
    sleep 3
    adb -a -P 5037 start-server || echo "Failed to start ADB server"
    sleep 3
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

# If still not found, try a different approach to detect devices
if [ -z "$DEVICE" ]; then
  echo "Trying alternative device detection..."
  DEVICE=$(adb devices | grep -E "emulator-[0-9]+" | head -n 1 | awk '{print $1}')
  
  if [ -n "$DEVICE" ]; then
    echo "Found device using alternative method: $DEVICE"
  else
    echo "⚠️ No device found after exhaustive searching. Will use default emulator-5554."
    DEVICE="emulator-5554"
  fi
fi

# Try to restart ADB server if device is still offline
DEVICE_STATUS=$(adb devices | grep "$DEVICE" | awk '{print $2}')
if [ "$DEVICE_STATUS" = "offline" ]; then
  echo "Emulator device is offline. Attempting comprehensive reconnection..."
  
  # Kill server, remove ADB keys, and restart server
  adb kill-server
  rm -f ~/.android/adbkey ~/.android/adbkey.pub 2>/dev/null || true
  sleep 3
  adb -a -P 5037 start-server
  sleep 5
  
  # Try direct reconnection to the emulator
  adb disconnect "$DEVICE" 2>/dev/null || true
  sleep 2
  adb connect "$DEVICE" || echo "Failed to connect to device"
  sleep 3
  
  # Check status again
  DEVICE_STATUS=$(adb devices | grep "$DEVICE" | awk '{print $2}')
  echo "Device status after reconnection attempt: $DEVICE_STATUS"
fi

# Enable ADB over TCP/IP with progressive approach
echo "Enabling ADB over TCP/IP on port 5555..."

# First try to set device to root for better permissions
adb -s "$DEVICE" wait-for-device
echo "Setting ADB as root..."
adb -s "$DEVICE" root || echo "Could not set ADB as root, will try tcpip anyway"
sleep 5  # Give device time to restart in root mode

# Reconnect to device after root mode switch
echo "Reconnecting to device after root mode switch..."
adb -s "$DEVICE" wait-for-device || echo "Wait for device timed out"
sleep 3

# Set TCP port property directly first for redundancy
echo "Setting TCP port property directly..."
adb -s "$DEVICE" shell "setprop service.adb.tcp.port 5555" || echo "Failed to set TCP port property"
sleep 2

# Restart ADB daemon on device
echo "Restarting ADB daemon..."
adb -s "$DEVICE" shell "stop adbd" || echo "Failed to stop ADB daemon"
sleep 2
adb -s "$DEVICE" shell "start adbd" || echo "Failed to start ADB daemon"
sleep 3

# Now try using the tcpip command
echo "Setting device to TCP/IP mode..."
adb -s "$DEVICE" tcpip 5555
sleep 5  # Give more time for mode switch

# Verify ADB TCP mode is enabled
echo "Verifying TCP mode..."
TCP_PORT=$(adb -s "$DEVICE" shell getprop service.adb.tcp.port 2>/dev/null || echo "")
if [ "$TCP_PORT" = "5555" ]; then
  echo "✅ ADB TCP mode successfully enabled on port 5555"
else
  echo "⚠️ Failed to verify ADB TCP mode, attempting universal command..."
  # Try the global command as fallback
  adb tcpip 5555 || echo "WARNING: Could not set ADB to TCP mode with global command either"
  sleep 5
  
  # Check one more time
  TCP_PORT=$(adb -s "$DEVICE" shell getprop service.adb.tcp.port 2>/dev/null || echo "")
  if [ "$TCP_PORT" = "5555" ]; then
    echo "✅ ADB TCP mode successfully enabled on second attempt"
  else
    echo "⚠️ Still failed to set ADB TCP mode properly"
  fi
fi

# Try connecting to the device over TCP/IP as a final verification
echo "Testing TCP/IP connection..."
HOST_IP=$(hostname -I | awk '{print $1}')
echo "Host IP: $HOST_IP"

adb disconnect "$DEVICE" 2>/dev/null || true
sleep 2
adb connect localhost:5555 || echo "Failed to connect to localhost:5555"
sleep 2

# Show final device list
echo "Final device list:"
adb devices

echo "=============================================="
echo "📱 ADB TCP mode setup completed. This container's ADB service is"
echo "   running on container port 5555. You can connect to it using:"
echo "   adb connect [CONTAINER_IP]:5555"
echo "=============================================="

# Print connection info
CONTAINER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown")
echo "Container IP: $CONTAINER_IP"
echo "=============================================="